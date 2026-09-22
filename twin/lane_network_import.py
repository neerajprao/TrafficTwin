"""
Imports a richer, per-lane traffic-junction JSON schema (nodes + individual
lane centerlines + explicit through-junction movement paths + real signal
phase groups) into this project's NetworkData, so a junction authored
externally with full lane-level and movement-level detail isn't flattened
down to this project's own coarser hand-editor format
(twin/persistence.py - one N-lane edge per road, with the specific turn a
vehicle takes inferred at simulation time from a generic lane-position rule
rather than given explicitly - see twin/engine.py's _lane_for).

Schema (see e.g. lampu_merah_vietnam_junction.json):
  - "nodes": {node_id: [lon, lat]} - shared by lanes and connections below.
  - "lanes": one entry per physical lane centerline. "kind" is "approach"
    (into the junction), "exit" (out of it), or "free_left_slip" (a left
    turn's own dedicated lane, physically bypassing the signal entirely -
    its own "nodes" already runs the full curve into the road it merges
    into, matching this project's left-hand-traffic convention that a left
    turn never crosses oncoming traffic and is never signal-gated, see
    engine.py's LEFT_TURN_MIN/MAX_DEG).
  - "connections": the explicit through-junction curve for every *signal
    -controlled* movement (straight/right/u_turn) - names its from_lane/
    to_lane and the exact path between them. Left turns don't get one
    here: a free_left_slip lane's own geometry already reaches its merge
    point, so adding its connection too would just duplicate a subset of
    the same path as a second overlapping edge.
  - "traffic_signals" + "signal_phases": which approach lanes each phase's
    green covers, and that phases are mutually exclusive (conflicts_with
    every other phase) - modeled here as one shared rotation, one slot per
    phase, all of that phase's lanes green together (twin/signals.py).

Each lane/connection becomes its own single-lane Edge - the source data
already gives one polyline per physical lane, so there's no need for this
project's usual per-edge lane count plus inferred turn-based lane
assignment: the graph's own topology (an approach lane's end node is
exactly a connection's start node, which is exactly an exit lane's start
node, and a lane only ever connects to the specific movements the source
data gives it a path for) already constrains routing to physically valid,
movement-correct paths, so the existing generic shortest-path routing
(twin/network.py's shortest_route) finds them with no special-casing.
"""
import json

import networkx as nx
from shapely.geometry import LineString

from .network import Edge, NetworkData, _haversine_m, rebuild_derived


def _line_length_m(coords: list[tuple[float, float]]) -> float:
    return sum(
        _haversine_m(lon1, lat1, lon2, lat2)
        for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:])
    )


def load_lane_network(path: str) -> NetworkData:
    with open(path) as f:
        data = json.load(f)

    all_nodes = {int(n): tuple(coords) for n, coords in data["nodes"].items()}

    def line_for(node_ids: list[str]) -> LineString:
        return LineString([all_nodes[int(n)] for n in node_ids])

    edges: list[Edge] = []
    edge_idx_by_lane_id: dict[str, int] = {}

    for lane in data["lanes"]:
        node_ids = lane["nodes"]
        geo_line = line_for(node_ids)
        edges.append(Edge(
            u=int(node_ids[0]), v=int(node_ids[-1]), key=0, lanes=1,
            highway=lane["kind"], name=lane["id"],
            length_m=_line_length_m(list(geo_line.coords)),
            geo_line=geo_line,
        ))
        edge_idx_by_lane_id[lane["id"]] = len(edges) - 1

    for conn in data["connections"]:
        if conn["movement"] == "left":
            continue  # its free_left_slip lane's own geometry already covers this path
        node_ids = conn["nodes"]
        geo_line = line_for(node_ids)
        edges.append(Edge(
            u=int(node_ids[0]), v=int(node_ids[-1]), key=0, lanes=1,
            highway="connection", name=conn["id"],
            length_m=_line_length_m(list(geo_line.coords)),
            geo_line=geo_line,
        ))

    # One shared rotation, one slot per phase - only one approach's lights
    # are ever green at a time, exactly matching the source file's own
    # signal_phases (each conflicts_with every other one, never two green
    # together). An earlier pass here tried merging opposing arms (N+S,
    # W+E) into shared slots after reading the video as showing paired
    # discharge behavior, but that read was inferred, not confirmed (the
    # nadir drone shot never shows the actual light color - see
    # data/video_observations.md), and was reverted on explicit correction:
    # only one arm's lights are green at a time, never two. Keyed by one of
    # the traffic_signals' own pole nodes - it's just a namespace for the
    # rotation, not itself part of the lane graph.
    lanes_by_phase: dict[str, list[str]] = {}
    for ts in data["traffic_signals"]:
        lanes_by_phase.setdefault(ts["phase"], []).extend(ts["controlled_lanes"])
    lanes_by_slot = [lanes_by_phase.get(phase["id"], []) for phase in data["signal_phases"]]
    junction_key = int(data["traffic_signals"][0]["node"])

    # Only nodes actually used as some edge's endpoint (plus the junction's
    # own namespace node above) are real topology - every other id in the
    # source file's "nodes" dict is purely a waypoint inside some lane's or
    # connection's own curve geometry (line_for already consumed those to
    # build geo_line) and must NOT be treated as a graph node: with in/out
    # degree 0, rebuild_derived's entry/exit-node rule would otherwise
    # wrongly turn every single curve waypoint into a spawn/despawn point.
    used = {e.u for e in edges} | {e.v for e in edges} | {junction_key}
    nodes = {n: all_nodes[n] for n in used}

    graph = nx.MultiDiGraph()
    for n, (lon, lat) in nodes.items():
        graph.add_node(n, x=lon, y=lat)
    for e in edges:
        graph.add_edge(e.u, e.v, key=e.key, length=e.length_m)

    lons = [lon for lon, _ in nodes.values()]
    lats = [lat for _, lat in nodes.values()]
    bounds = (min(lons), min(lats), max(lons), max(lats))

    net = NetworkData(
        nodes=nodes, edges=edges, out_edges={}, entry_nodes=[], exit_nodes=[],
        junction_nodes=[], signal_approaches={}, graph=graph, bounds=bounds,
    )
    rebuild_derived(net)  # fills out_edges/entry_nodes/exit_nodes from real graph degree

    # the junction-key node is a pure namespace marker with no edges of its
    # own (see above) - degree 0 both ways would otherwise also qualify it
    # as an entry AND exit node, which just wastes spawn attempts since no
    # route can ever start or end on a node with no edges at all
    net.entry_nodes = [n for n in net.entry_nodes if n != junction_key]
    net.exit_nodes = [n for n in net.exit_nodes if n != junction_key]

    net.junction_nodes = [junction_key]
    net.signal_approaches[junction_key] = [
        [(edges[edge_idx_by_lane_id[lane_id]].u, edges[edge_idx_by_lane_id[lane_id]].v) for lane_id in lane_ids]
        for lane_ids in lanes_by_slot
    ]

    # Demand isn't spread evenly across the 4 arms in the real video: two
    # arms consistently show much larger, denser queues than the other two
    # (data/video_observations.md). Applied here as a modest bias toward two
    # of the four arms - which real-world compass side that corresponds to
    # in the video was NOT confirmed (the drone footage's orientation
    # relative to true north was never established), so this is a
    # best-guess direction, not a measured one, and easy to flip: swap
    # HEAVY_ARM_WEIGHT and LIGHT_ARM_WEIGHT (or which arms land in
    # heavy_arms) if it turns out backwards.
    HEAVY_ARM_WEIGHT = 1.3
    LIGHT_ARM_WEIGHT = 0.85
    heavy_arms = {phase["green_for_approach"] for phase in data["signal_phases"][:2]}  # {"N", "S"}
    weighted_entries = []
    for lane in data["lanes"]:
        if lane["kind"] not in ("approach", "free_left_slip"):
            continue
        entry_node = int(lane["nodes"][0])
        if entry_node not in net.entry_nodes:
            continue
        weight = HEAVY_ARM_WEIGHT if lane["arm"] in heavy_arms else LIGHT_ARM_WEIGHT
        # net.entry_nodes is drawn from uniformly by twin/spawner.py, so
        # representing a node proportionally more often is a self-contained
        # way to bias its spawn share without changing Spawner itself
        weighted_entries.extend([entry_node] * round(weight * 10))
    net.entry_nodes = weighted_entries

    return net
