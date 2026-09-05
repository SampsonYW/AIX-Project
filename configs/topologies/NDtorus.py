# Copyright (c) 2010 Advanced Micro Devices, Inc.
#               2016 Georgia Institute of Technology
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from m5.params import *
from m5.objects import *

from common import FileSystemConfig

from topologies.BaseTopology import SimpleTopology

# Creates a generic Mesh assuming an equal number of cache
# and directory controllers.
# XY routing is enforced (using link weights)
# to guarantee deadlock freedom.


class NDtorus(SimpleTopology):
    description = "NDtorus"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes

        num_routers = options.num_cpus
        dims = options.torus_dims

        link_latency = options.link_latency
        router_latency = options.router_latency

        cntrls_per_router, remainder = divmod(len(nodes), num_routers)

        routers = [
            Router(router_id=i, latency=router_latency)
            for i in range(num_routers)
        ]
        network.routers = routers

        link_count = 0

        network_nodes = []
        remainder_nodes = []
        for node_index in range(len(nodes)):
            if node_index < (len(nodes) - remainder):
                network_nodes.append(nodes[node_index])
            else:
                remainder_nodes.append(nodes[node_index])

        # Connect each node to the appropriate router
        ext_links = []
        for (i, n) in enumerate(network_nodes):
            cntrl_level, router_id = divmod(i, num_routers)
            assert cntrl_level < cntrls_per_router
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=n,
                    int_node=routers[router_id],
                    latency=link_latency,
                )
            )
            link_count += 1

        # Connect the remainding nodes to router 0.  These should only be
        # DMA nodes.
        for (i, node) in enumerate(remainder_nodes):
            assert node.type == "DMA_Controller"
            assert i < remainder
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=node,
                    int_node=routers[0],
                    latency=link_latency,
                )
            )
            link_count += 1

        network.ext_links = ext_links

        # Create the mesh links.
        int_links = []

        def decode(id):
            coord = []
            for x in dims:
                coord.append(id % x)
                id //= x
            return coord
        def encode(coord):
            id = 0
            mult = 1
            for (i, x) in enumerate(coord):
                id += mult * x
                mult *= dims[i]
            return id
        for id in range(num_routers):
            coord = decode(id)
            # now_coord = decode(id)
            # print("connect ", coord)
            for i in range(len(dims)):
                plus_port = f"D{i}+"
                minus_port = f"D{i}-"
                coord[i] = (coord[i] + 1) % dims[i]
                plus_neighbor = encode(coord)
                # print(id, plus_neighbor)
                # print(i, dims[i], now_coord, coord)
                coord[i] = (coord[i] + dims[i] - 1) % dims[i]
                coord[i] = (coord[i] + dims[i] - 1) % dims[i]
                minus_neighbor = encode(coord)
                # print(now_coord, coord)
                coord[i] = (coord[i] + 1) % dims[i]
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[id],
                        dst_node=routers[plus_neighbor],
                        src_outport=plus_port,
                        dst_inport=minus_port,
                        latency=link_latency
                    )
                )
                link_count += 1
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[id],
                        dst_node=routers[minus_neighbor],
                        src_outport=minus_port,
                        dst_inport=plus_port,
                        latency=link_latency
                    )
                )
                link_count += 1
        network.int_links = int_links

    # Register nodes with filesystem
    def registerTopology(self, options):
        for i in range(options.num_cpus):
            FileSystemConfig.register_node(
                [i], MemorySize(options.mem_size) // options.num_cpus, i
            )
