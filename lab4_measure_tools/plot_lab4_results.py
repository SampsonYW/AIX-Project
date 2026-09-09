import argparse
import csv
import html
import math
from pathlib import Path


LABELS = {
    "torus3_dor_raw": "DOR",
    "torus3_adaptive_raw": "Adaptive",
    "torus3_dor": "DOR + escape",
    "torus3_dor_nosticky": "DOR + escape + no-sticky",
    "torus3_adaptive": "Adaptive + escape",
    "torus1_adaptive_balanced": "1D 256 (12 VC)",
    "torus2_adaptive_balanced": "2D 16x16 (6 VC)",
    "torus3_adaptive_balanced": "3D 8x8x4 (4 VC)",
    "torus4_adaptive_balanced": "4D 4x4x4x4 (3 VC)",
}

COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2"]


def svg_plot(path, title, metric, series):
    width, height = 960, 600
    left, right, top, bottom = 90, 250, 60, 75
    plot_width = width - left - right
    plot_height = height - top - bottom
    points = [point for values in series.values() for point in values]
    if not points:
        return False
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_min, x_max = min(x_values), max(x_values)
    if x_min == x_max:
        x_min, x_max = 0.0, max(0.1, x_max)
    y_min = 0.0
    y_max = max(y_values)
    if y_max <= 0 or not math.isfinite(y_max):
        return False
    y_max *= 1.08

    def sx(value):
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def sy(value):
        return top + plot_height - (value - y_min) / (y_max - y_min) * plot_height

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="32" text-anchor="middle" font-family="sans-serif" font-size="20">{html.escape(title)}</text>',
    ]
    for index in range(6):
        x = left + plot_width * index / 5
        value = x_min + (x_max - x_min) * index / 5
        elements.extend([
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+plot_height}" stroke="#e5e7eb"/>',
            f'<text x="{x:.1f}" y="{top+plot_height+24}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:.2f}</text>',
        ])
    for index in range(6):
        y = top + plot_height * index / 5
        value = y_max * (5 - index) / 5
        elements.extend([
            f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_width}" y2="{y:.1f}" stroke="#e5e7eb"/>',
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.3g}</text>',
        ])
    elements.extend([
        f'<line x1="{left}" y1="{top+plot_height}" x2="{left+plot_width}" y2="{top+plot_height}" stroke="black"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" stroke="black"/>',
        f'<text x="{left+plot_width/2}" y="{height-22}" text-anchor="middle" font-family="sans-serif" font-size="14">Injection rate (packet/node/cycle)</text>',
        f'<text transform="translate(22 {top+plot_height/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="14">{html.escape(metric)}</text>',
    ])
    for index, (name, values) in enumerate(sorted(series.items())):
        color = COLORS[index % len(COLORS)]
        values = sorted(values)
        polyline = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in values)
        elements.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for x, y in values:
            elements.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3.5" fill="{color}"/>')
        legend_y = top + 18 + index * 25
        elements.extend([
            f'<line x1="{left+plot_width+22}" y1="{legend_y}" x2="{left+plot_width+52}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{left+plot_width+60}" y="{legend_y+4}" font-family="sans-serif" font-size="12">{html.escape(LABELS.get(name, name))}</text>',
        ])
    elements.append('</svg>')
    path.write_text("\n".join(elements), encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["task1", "task2", "task3"])
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    source = args.results / "summary.csv"
    rows = list(csv.DictReader(source.open(newline="", encoding="utf-8")))
    valid = [row for row in rows if row["status"] == "ok"]
    valid.sort(key=lambda row: (row["pattern"], int(row["vcs_per_vnet"]), row["case"], float(row["offered_rate"])))
    plot_dir = args.results / "plots"
    plot_dir.mkdir(exist_ok=True)
    with (args.results / "plot_data.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(valid)

    if args.task == "task1":
        groups = [(pattern, [row for row in valid if row["pattern"] == pattern])
                  for pattern in sorted({row["pattern"] for row in valid})]
    elif args.task == "task2":
        groups = [(f"vc{vcs}", [row for row in valid if row["vcs_per_vnet"] == vcs])
                  for vcs in sorted({row["vcs_per_vnet"] for row in valid}, key=int)]
    else:
        groups = [(pattern, [row for row in valid if row["pattern"] == pattern])
                  for pattern in sorted({row["pattern"] for row in valid})]

    manifest = []
    metrics = [
        ("packet_latency_cycles", "Average packet latency (cycles)", "latency"),
        ("received_per_node_cycle", "Reception rate (packet/node/cycle)", "reception_rate"),
    ]
    for group, group_rows in groups:
        for column, axis_label, suffix in metrics:
            series = {}
            for row in group_rows:
                series.setdefault(row["case"], []).append(
                    (float(row["offered_rate"]), float(row[column])))
            filename = f"{args.task}_{group}_{suffix}.svg"
            title = f"{args.task}: {group} - {axis_label}"
            if svg_plot(plot_dir / filename, title, axis_label, series):
                manifest.append(dict(task=args.task, group=group, metric=column, file=f"plots/{filename}"))
    with (args.results / "plots_manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["task", "group", "metric", "file"])
        writer.writeheader()
        writer.writerows(manifest)
    links = "\n".join(f'<li><a href="{html.escape(item["file"])}">{html.escape(item["group"])} — {html.escape(item["metric"])}</a></li>' for item in manifest)
    failed = len(rows) - len(valid)
    (args.results / "plots.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>{args.task} plots</title><h1>{args.task}</h1><p>{len(valid)} valid points; {failed} failed points.</p><ul>{links}</ul>',
        encoding="utf-8")
    print(f"CSV: {source}")
    print(f"Plot-ready CSV: {args.results / 'plot_data.csv'}")
    print(f"Plots: {plot_dir}")
    print(f"Index: {args.results / 'plots.html'}")


if __name__ == "__main__":
    main()
