"""
Phase 2 (rebuilt) - saves/loads a NetworkData to/from a plain JSON snapshot,
so edits made in the road editor (twin/editor.py) persist across runs
instead of being lost when the window closes. Loading from a snapshot
completely bypasses OSM/osmnx - it's just nodes, edges, and which nodes are
signalized.
"""
import json
import os

import networkx as nx
from shapely.geometry import LineString

from .network import Edge, NetworkData, _haversine_m, rebuild_derived


def _line_length_m(coords: list[tuple[float, float]]) -> float:
    return sum(
        _haversine_m(lon1, lat1, lon2, lat2)
        for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:])
    )


def save_network(net: NetworkData, path: str):
    data = {
        "nodes": {str(n): list(coords) for n, coords in net.nodes.items()},
        "edges": [
            {
                "u": e.u, "v": e.v, "lanes": e.lanes, "highway": e.highway, "name": e.name,
                # the road's actual (possibly curved) geometry - without this,
                # reloading would rebuild every road as a straight line
                # between its two endpoint nodes, visibly shifting it off its
                # real path.
                "coords": [list(c) for c in e.geo_line.coords],
            }
            for e in net.edges
        ],
        "junction_nodes": net.junction_nodes,
        "signal_approaches": {
            str(node): [[list(uv) for uv in slot] for slot in slots]
            for node, slots in net.signal_approaches.items()
        },
        # only actually used when there are no nodes yet (a blank canvas) -
        # rebuild_derived recomputes it from real node positions the moment
        # any exist, same as before this field existed.
        "bounds": list(net.bounds),
    }
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_saved_network(path: str) -> NetworkData:
    with open(path) as f:
        data = json.load(f)

    nodes = {int(n): tuple(coords) for n, coords in data["nodes"].items()}

    edges = []
    for e in data["edges"]:
        coords = e.get("coords")
        if not coords or len(coords) < 2:
            # older save files (before geometry was persisted) only have
            # the two endpoints - fall back to a straight line for those.
            coords = [nodes[e["u"]], nodes[e["v"]]]
        coords = [tuple(c) for c in coords]
        edges.append(Edge(
            u=e["u"], v=e["v"], key=0, lanes=e["lanes"],
            highway=e.get("highway", "custom"), name=e.get("name"),
            length_m=_line_length_m(coords),
            geo_line=LineString(coords),
        ))

    def _normalize_slots(raw_slots):
        # tolerate an older save file where each entry was a single [u, v]
        # edge rather than a list of edges sharing one rotation slot
        return [
            [tuple(item)] if item and isinstance(item[0], int) else [tuple(uv) for uv in item]
            for item in raw_slots
        ]

    signal_approaches = {
        int(node): _normalize_slots(slots)
        for node, slots in data.get("signal_approaches", {}).items()
    }
    bounds = tuple(data["bounds"]) if "bounds" in data else (0.0, 0.0, 0.0, 0.0)

    net = NetworkData(
        nodes=nodes, edges=edges, out_edges={}, entry_nodes=[], exit_nodes=[],
        junction_nodes=list(data.get("junction_nodes", [])),
        signal_approaches=signal_approaches,
        graph=nx.MultiDiGraph(), bounds=bounds,
    )
    rebuild_derived(net)
    return net
