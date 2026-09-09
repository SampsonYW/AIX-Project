import argparse
import configparser
import csv
import math
from pathlib import Path


def prepare(root):
    source = root / "configs/example/garnet_synth_traffic.py"
    target = root / "configs/example/garnet_synth_measure.py"
    content = source.read_text(encoding="utf-8")
    replacements = {
        "args = parser.parse_args()": '''args = parser.parse_args()
warmup_ticks = int(os.environ.get("LAB4_WARMUP", "20000"))
measure_ticks = int(os.environ.get("LAB4_MEASURE", "100000"))
traffic_seed = int(os.environ.get("LAB4_SEED", "1"))
assert warmup_ticks > 0 and measure_ticks > 0
assert args.sys_clock == "2GHz" and args.ruby_clock == "2GHz"
args.sim_cycles = warmup_ticks + measure_ticks + 1
from _m5.core import seedRandom
seedRandom(traffic_seed)''',
        "exit_event = m5.simulate(args.abs_max_tick)": '''exit_event = m5.simulate(warmup_ticks)
if m5.curTick() != warmup_ticks:
    raise RuntimeError("Simulation exited during warmup: " + exit_event.getCause())
m5.stats.dump()
m5.stats.reset()
exit_event = m5.simulate(measure_ticks)
if m5.curTick() != warmup_ticks + measure_ticks:
    raise RuntimeError("Simulation exited during measurement: " + exit_event.getCause())''',
    }
    for old, new in replacements.items():
        if content.count(old) != 1:
            raise ValueError(f"Expected exactly one occurrence of {old!r}")
        content = content.replace(old, new)
    compile(content, str(target), "exec")
    legacy_content = content.replace(
        "from _m5.core import seedRandom\nseedRandom(traffic_seed)",
        "m5.core.seedRandom(traffic_seed)",
    )
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing not in (content, legacy_content):
            raise ValueError(f"Refusing to overwrite a different existing file: {target}")
    target.write_text(content, encoding="utf-8", newline="\n")
    print(target)


def collect(args):
    row = dict(case=args.case, pattern=args.pattern, requested_vcs=args.vcs,
               requested_nodes=args.nodes,
               offered_rate=args.rate, traffic_seed=args.seed,
               warmup_ticks=args.warmup, measurement_ticks=args.measure,
               exit_code=args.exit_code, status="run_failed", outdir=str(args.outdir))
    keys = ["actual_ticks", "routers", "routing_algorithm", "vcs_per_vnet",
            "escape", "no_sticky", "torus_dims", "directed_internal_links",
            "received_per_directed_link_cycle",
            "injected", "received", "injected_per_node_cycle",
            "received_per_node_cycle", "packet_latency_cycles",
            "network_latency_cycles", "queueing_latency_cycles", "average_hops"]
    row.update(dict.fromkeys(keys, ""))
    if args.exit_code == 0:
        try:
            config = configparser.ConfigParser(interpolation=None)
            config.read(args.outdir / "config.ini")
            network = config["system.ruby.network"]
            assert network["type"] == "GarnetNetwork"
            assert int(network["number_of_virtual_networks"]) == 3
            if args.vcs is not None:
                assert int(network["vcs_per_vnet"]) == args.vcs
            testers = [section for section in config.values()
                       if section.get("type") == "GarnetSyntheticTraffic"]
            if len(testers) != args.nodes:
                raise ValueError(f"Expected {args.nodes} traffic generators, found {len(testers)}")
            for tester in testers:
                if tester.get("traffic_type") != args.pattern:
                    raise ValueError(f"Traffic pattern mismatch in {tester.name}")
                if tester.get("inj_vnet") != "0":
                    raise ValueError(f"Expected inj_vnet=0 in {tester.name}")
            assert config["system.clk_domain"]["clock"] == "1"
            assert config["system.ruby.clk_domain"]["clock"] == "1"
            routers = len(network["routers"].split())
            assert routers == args.nodes
            internal_links = len(network["int_links"].split())
            assert internal_links > 0
            content = (args.outdir / "stats.txt").read_text(encoding="utf-8")
            blocks = content.split("---------- Begin Simulation Statistics ----------")
            if len(blocks) < 3:
                raise ValueError("Warmup and measurement statistics blocks required")
            stats = {}
            for line in blocks[-1].splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        stats[parts[0]] = float(parts[1])
                    except ValueError:
                        pass
            ticks = stats["simTicks"]
            assert ticks == args.measure
            prefix = "system.ruby.network."
            injected = int(stats[prefix + "packets_injected::total"])
            received = int(stats[prefix + "packets_received::total"])
            latency = stats[prefix + "average_packet_latency"]
            assert received > 0 and math.isfinite(latency)
            row.update(status="ok", actual_ticks=int(ticks), routers=routers,
                       routing_algorithm=network["routing_algorithm"],
                       vcs_per_vnet=network["vcs_per_vnet"],
                       escape=network["enable_escape"],
                       no_sticky=network["enable_no_sticky"],
                       torus_dims=network.get("torus_dims", ""),
                       directed_internal_links=internal_links,
                       received_per_directed_link_cycle=received / ticks / internal_links,
                       injected=injected,
                       received=received,
                       injected_per_node_cycle=injected / ticks / routers,
                       received_per_node_cycle=received / ticks / routers,
                       packet_latency_cycles=latency,
                       network_latency_cycles=stats[prefix + "average_packet_network_latency"],
                       queueing_latency_cycles=stats[prefix + "average_packet_queueing_latency"],
                       average_hops=stats[prefix + "average_hops"])
        except (OSError, KeyError, ValueError, AssertionError, configparser.Error) as error:
            row["status"] = "invalid_stats"
            print(f"Cannot validate {args.outdir}: {error}")
    exists = args.csv.exists() and args.csv.stat().st_size > 0
    with args.csv.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    print(f"{args.case} rate={args.rate} seed={args.seed}: {row['status']}")
    if row["status"] == "invalid_stats":
        raise SystemExit(2)


def merge(root):
    rows = []
    for result in sorted(root.glob("*/result.csv")):
        if not (result.parent / "complete").exists():
            continue
        with result.open(newline="", encoding="utf-8") as stream:
            rows.extend(csv.DictReader(stream))
    if not rows:
        return
    target = root / "summary.csv"
    temporary = root / "summary.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("root", type=Path)
    merge_parser = commands.add_parser("merge")
    merge_parser.add_argument("root", type=Path)
    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("outdir", type=Path)
    collect_parser.add_argument("csv", type=Path)
    collect_parser.add_argument("case")
    collect_parser.add_argument("rate", type=float)
    collect_parser.add_argument("seed", type=int)
    collect_parser.add_argument("warmup", type=int)
    collect_parser.add_argument("measure", type=int)
    collect_parser.add_argument("exit_code", type=int)
    collect_parser.add_argument("--pattern", default="uniform_random")
    collect_parser.add_argument("--vcs", type=int)
    collect_parser.add_argument("--nodes", type=int, default=256)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root)
    elif args.command == "merge":
        merge(args.root)
    else:
        collect(args)


if __name__ == "__main__":
    main()
