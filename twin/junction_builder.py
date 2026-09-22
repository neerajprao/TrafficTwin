"""
Builds a minimal, hand-authored NetworkData for a single signalized junction
from scratch: just the real-world junction position and each arm's real
compass direction (needed so it lines up with the satellite basemap and the
already-surveyed SIGNAL_LIGHT_COORDS), a chosen arm length, and a lane count
per arm set directly by eye from the source video
(data/video/astra_biz_center.mp4) - no OSM import, no OSM lane tags, no OSM
`highway=traffic_signals` tags anywhere in this path. Intentionally models
only the one junction, not the surrounding street network.

Run as a script to (re)generate data/edited/astra_biz_center.json, which
twin/app.py already prefers over an OSM fetch whenever it exists.
"""
import math
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString

from .network import Edge, NetworkData, _haversine_m, rebuild_derived

EARTH_R_M = 6371000.0
LANE_WIDTH_M = 3.2  # matches render.py's LANE_WIDTH_M
MEDIAN_HALF_GAP_M = 2.5  # extra gap beyond the lanes themselves, each side of centerline

JUNCTION_ID = 0


@dataclass
class Arm:
    name: str
    outward_bearing: float  # compass degrees, junction -> far end of this arm
    lanes: int
    length_m: float = 200.0


def _destination(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Real-world (lat, lon) a given bearing/distance from (lat, lon) - flat
    -earth approximation, fine at this ~200m scale (same assumption used
    elsewhere in this package, e.g. network.py's _haversine_m)."""
    brg = math.radians(bearing_deg)
    dlat = (dist_m * math.cos(brg)) / EARTH_R_M
    dlon = (dist_m * math.sin(brg)) / (EARTH_R_M * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def build_junction(center_lat: float, center_lon: float, arms: list[Arm]) -> NetworkData:
    """One junction node at (center_lat, center_lon), plus 2 boundary nodes
    per arm (inbound-only and outbound-only, each with a single edge to/from
    the junction) - modeled as two separate carriageways of a divided road,
    offset to either side of the arm's centerline, matching the median seen
    in the video and giving each boundary node the single-direction degree
    (in_degree==0 or out_degree==0) that marks it as a spawn/despawn point
    the same way network.py's OSM-derived entry/exit nodes are found."""
    nodes: dict[int, tuple[float, float]] = {JUNCTION_ID: (center_lon, center_lat)}
    edges: list[Edge] = []
    next_id = JUNCTION_ID + 1

    for arm in arms:
        # left-hand traffic keeps left: the outbound carriageway (leaving
        # the junction) sits to the left of the outward direction of
        # travel, the inbound one (arriving) to the right - see
        # engine.py/render.py's own "higher lane index = more left" and
        # "left-hand traffic" conventions for the same rule applied
        # elsewhere in this codebase.
        out_side_bearing = (arm.outward_bearing - 90) % 360
        in_side_bearing = (arm.outward_bearing + 90) % 360
        half_width = arm.lanes * LANE_WIDTH_M / 2 + MEDIAN_HALF_GAP_M

        far_lat, far_lon = _destination(center_lat, center_lon, arm.outward_bearing, arm.length_m)
        out_lat, out_lon = _destination(far_lat, far_lon, out_side_bearing, half_width)
        in_lat, in_lon = _destination(far_lat, far_lon, in_side_bearing, half_width)

        out_node, in_node = next_id, next_id + 1
        next_id += 2
        nodes[out_node] = (out_lon, out_lat)
        nodes[in_node] = (in_lon, in_lat)

        out_line = LineString([(center_lon, center_lat), (out_lon, out_lat)])
        in_line = LineString([(in_lon, in_lat), (center_lon, center_lat)])

        edges.append(Edge(u=JUNCTION_ID, v=out_node, key=0, lanes=arm.lanes, highway="custom",
                           name=arm.name, length_m=_haversine_m(center_lon, center_lat, out_lon, out_lat),
                           geo_line=out_line))
        edges.append(Edge(u=in_node, v=JUNCTION_ID, key=0, lanes=arm.lanes, highway="custom",
                           name=arm.name, length_m=_haversine_m(in_lon, in_lat, center_lon, center_lat),
                           geo_line=in_line))

    # round-robin in the same order the arms were given, matching the old
    # signal_light_coords-pinned behavior this function used to feed - one
    # edge per slot, same as the editor's own single-edge-at-a-time T/A workflow
    slots = [[(e.u, e.v)] for e in edges if e.v == JUNCTION_ID]
    net = NetworkData(
        nodes=nodes, edges=edges, out_edges={}, entry_nodes=[], exit_nodes=[],
        junction_nodes=[JUNCTION_ID], signal_approaches={JUNCTION_ID: slots},
        graph=nx.MultiDiGraph(), bounds=(0.0, 0.0, 0.0, 0.0),
    )
    rebuild_derived(net)
    return net


# Astra Biz Center, BSD City - real junction position (matches the node the
# old OSM import consolidated onto, already verified against the satellite
# basemap and the video) and each arm's real compass bearing (derived once
# from the same OSM fetch, purely for direction - not for lanes or signals).
# Lane counts are set by eye from the video instead of trusting OSM's tags:
# the two "Jalan BSD Raya Utama" arms (the wider road, with a visible
# motorcycle box + bike lane beyond the car lanes) get 5; the two
# "Jalan BSD Boulevard Utara" arms (narrower) get 4.
ASTRA_BIZ_CENTER_CENTER = (-6.28687783196895, 106.63909437403515)  # (lat, lon)
ASTRA_BIZ_CENTER_ARMS = [
    Arm(name="Jalan BSD Boulevard Utara (east)", outward_bearing=281.3, lanes=4),
    Arm(name="Jalan BSD Raya Utama (north)", outward_bearing=31.4, lanes=5),
    Arm(name="Jalan BSD Boulevard Utara (west)", outward_bearing=99.3, lanes=4),
    Arm(name="Jalan BSD Raya Utama (south)", outward_bearing=222.7, lanes=5),
]


def build_astra_biz_center() -> NetworkData:
    lat, lon = ASTRA_BIZ_CENTER_CENTER
    return build_junction(lat, lon, ASTRA_BIZ_CENTER_ARMS)


if __name__ == "__main__":
    from .persistence import save_network

    SAVE_PATH = "data/edited/astra_biz_center.json"
    net = build_astra_biz_center()
    save_network(net, SAVE_PATH)
    print(f"Built a from-scratch {len(ASTRA_BIZ_CENTER_ARMS)}-arm junction "
          f"({len(net.nodes)} nodes, {len(net.edges)} edges) and saved to {SAVE_PATH}")
