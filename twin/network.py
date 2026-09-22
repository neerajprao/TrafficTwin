"""
Phase 2 (rebuilt) - loads the Astra Biz Center road network straight from the
already-fetched OSM data (data/osm/astra_biz_center.osm.xml, from
scripts/fetch_osm.py) as a routable graph for the custom digital twin, with
no SUMO/netconvert step involved.

osmnx already stores edge length in meters (geodesic) regardless of the
graph's CRS, so edges keep their original lon/lat geometry (used directly for
rendering) while `length_m` is used for all physics. Signalized junctions are
found from real OSM `highway=traffic_signals` tags (after consolidating each
one's raw multi-node cluster into a single node, same role netconvert played
for SUMO) - OSM's tagging is crowdsourced and sometimes incomplete, so
`extra_signal_coords` lets a caller manually add real signals OSM missed.
"""
import math
import warnings
from dataclasses import dataclass

import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, Point

OSM_PATH = "data/osm/astra_biz_center.osm.xml"
CONSOLIDATE_TOLERANCE_M = 15  # merges the OSM shape-node cluster at the
# signalized junction into one node, same role netconvert played for SUMO.
DEFAULT_SIGNAL_SETBACK_M = 20.0  # generic stop-line distance when no real position was given


@dataclass
class Edge:
    u: int
    v: int
    key: int
    lanes: int
    highway: str
    name: str | None
    length_m: float
    geo_line: LineString  # lon/lat coordinates, in travel direction u -> v


@dataclass
class NetworkData:
    nodes: dict[int, tuple[float, float]]  # node id -> (lon, lat)
    edges: list[Edge]
    out_edges: dict[int, list[int]]  # node id -> indices into `edges`
    entry_nodes: list[int]
    exit_nodes: list[int]
    junction_nodes: list[int]  # every signalized junction (real OSM tags + manual additions)
    # node id -> ordered list of rotation slots, each slot a list of (u, v)
    # edges that are all green together (one slot = one signal phase). Set
    # by hand in the editor (T to toggle a junction, A to add/remove an
    # approach - twin/editor.py, which always uses single-edge slots) or by
    # a richer import (twin/lane_network_import.py) that groups a whole
    # approach's several lanes into one slot. Identified by (u, v) rather
    # than a raw edge-list index so an entry survives edge-list splicing
    # when other roads are added/removed elsewhere (see rebuild_derived). A
    # node present here (even with no slots yet) is fully manually
    # controlled - SignalController never invents a fallback phase for it,
    # unlike an OSM-tagged junction_nodes entry with no config at all.
    signal_approaches: dict[int, list[list[tuple[int, int]]]]
    graph: nx.MultiDiGraph  # for shortest_path routing, weighted by length_m
    bounds: tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)


def _first(value):
    """OSM tags like `highway`/`lanes` are sometimes a list when a way was
    split with conflicting tags; just take the first value."""
    return value[0] if isinstance(value, list) else value


def _lanes(value) -> int:
    value = _first(value)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _nearest_node(nodes: dict[int, tuple[float, float]], lat: float, lon: float) -> int:
    """Brute-force nearest node by lon/lat - the network is only ~50-100
    nodes, and it's a tiny area, so plain squared distance in degree-space
    is accurate enough for nearest-neighbor purposes without adding a
    scipy/scikit-learn dependency just for this."""
    return min(nodes, key=lambda n: (nodes[n][0] - lon) ** 2 + (nodes[n][1] - lat) ** 2)


def load_network(osm_path: str = OSM_PATH, extra_signal_coords: tuple[tuple[float, float], ...] = (),
                  signal_light_coords: tuple[tuple[float, float], ...] = ()) -> NetworkData:
    """`extra_signal_coords` is a sequence of (lat, lon) pairs for real
    signalized junctions OSM didn't tag - each is snapped to its nearest
    network node and added alongside whatever OSM's own tags found.

    `signal_light_coords` is the same real surveyed per-approach light
    positions used by SignalController/Renderer. When given, they're
    authoritative about which junction is actually signal-controlled: OSM's
    own `highway=traffic_signals` tags are dropped in favor of exactly the
    node(s) these coordinates resolve to. Without this, a raw OSM tag
    elsewhere nearby (e.g. a mid-block pedestrian-crossing signal) ends up
    in `junction_nodes` with no confirmed position of its own, and
    SignalController invents a generic phase program for it - a phantom
    traffic light that doesn't exist in reality. `extra_signal_coords`
    still adds on top of this, for a genuinely different junction that's
    confirmed real but has no per-approach data yet."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = ox.graph_from_xml(osm_path)
        # capture every real `highway=traffic_signals` tag's position *before*
        # consolidation - consolidate_intersections merges clusters of nearby
        # raw OSM nodes into one, and when two separately-tagged signal nodes
        # land in the same merged cluster, only one survives with the tag
        # intact, silently dropping the other. Re-matching by real-world
        # position afterwards (same as `extra_signal_coords` below) means a
        # tag is never lost to that merge, no matter how consolidation groups
        # things.
        raw_signal_coords = [
            (data["y"], data["x"]) for _, data in g.nodes(data=True) if data.get("highway") == "traffic_signals"
        ]
        g = ox.project_graph(g)
        g = ox.consolidate_intersections(
            g, rebuild_graph=True, tolerance=CONSOLIDATE_TOLERANCE_M, dead_ends=False
        )
        g = ox.project_graph(g, to_crs="epsg:4326")

    nodes = {n: (data["x"], data["y"]) for n, data in g.nodes(data=True)}

    edges: list[Edge] = []
    out_edges: dict[int, list[int]] = {n: [] for n in g.nodes}
    for u, v, k, data in g.edges(keys=True, data=True):
        edges.append(Edge(
            u=u, v=v, key=k,
            lanes=_lanes(data.get("lanes")),
            highway=str(_first(data.get("highway", "unclassified"))),
            name=_first(data.get("name")),
            length_m=float(data["length"]),
            geo_line=data["geometry"],
        ))
        out_edges[u].append(len(edges) - 1)

    in_deg = dict(g.in_degree())
    out_deg = dict(g.out_degree())
    entry_nodes = [n for n in g.nodes if in_deg[n] == 0]
    exit_nodes = [n for n in g.nodes if out_deg[n] == 0]

    lons = [lon for lon, _ in nodes.values()]
    lats = [lat for _, lat in nodes.values()]
    bounds = (min(lons), min(lats), max(lons), max(lats))

    net = NetworkData(
        nodes=nodes, edges=edges, out_edges=out_edges,
        entry_nodes=entry_nodes, exit_nodes=exit_nodes,
        junction_nodes=[], signal_approaches={}, graph=g, bounds=bounds,
    )

    if signal_light_coords:
        # authoritative: only the junction(s) the real surveyed positions
        # actually resolve to - raw OSM tags elsewhere are not enough on
        # their own (see docstring above).
        signalized = {net.edges[i].v for i in resolve_pinned_edges(net, signal_light_coords)}
    else:
        signalized = {n for n, data in g.nodes(data=True) if data.get("highway") == "traffic_signals"}
        for lat, lon in raw_signal_coords:
            signalized.add(_nearest_node(nodes, lat, lon))
    for lat, lon in extra_signal_coords:
        signalized.add(_nearest_node(nodes, lat, lon))
    net.junction_nodes = sorted(signalized) if signalized else [max(dict(g.degree()), key=dict(g.degree()).get)]

    return net


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters - osmnx computes edge length this way
    too, but only for edges it fetched; hand-drawn roads need it computed
    directly since there's no OSM way behind them."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def add_node(net: NetworkData, lon: float, lat: float) -> int:
    """Used by the road editor (twin/editor.py). New nodes get negative IDs
    so they never collide with a real OSM node ID."""
    node_id = min((n for n in net.nodes if n < 0), default=0) - 1
    net.nodes[node_id] = (lon, lat)
    net.out_edges[node_id] = []
    rebuild_derived(net)
    return node_id


def add_road(net: NetworkData, u: int, v: int, lanes: int = 2) -> list[int]:
    """Appends a bidirectional pair of edges between two existing nodes
    (every road elsewhere in the network is already a directed pair like
    this), straight-line geometry, length from _haversine_m since there's no
    OSM way to read it from."""
    new_indices = []
    for a, b in ((u, v), (v, u)):
        lon1, lat1 = net.nodes[a]
        lon2, lat2 = net.nodes[b]
        net.edges.append(Edge(
            u=a, v=b, key=0, lanes=max(1, lanes), highway="custom", name=None,
            length_m=_haversine_m(lon1, lat1, lon2, lat2),
            geo_line=LineString([(lon1, lat1), (lon2, lat2)]),
        ))
        new_indices.append(len(net.edges) - 1)
    rebuild_derived(net)
    return new_indices


def remove_edge(net: NetworkData, edge_idx: int):
    del net.edges[edge_idx]
    rebuild_derived(net)


def remove_node(net: NetworkData, node_id: int, force: bool = False):
    """Also removes every edge touching it. Refuses to remove a signalized
    junction node outright - it's usually a real traffic light plus the hub
    several roads meet at, so deleting it silently cascades into losing a
    chunk of the network; pass force=True to remove it anyway (e.g. the
    editor's Shift+Delete), which also drops it from junction_nodes."""
    if node_id in net.junction_nodes and not force:
        return
    net.edges[:] = [e for e in net.edges if e.u != node_id and e.v != node_id]
    del net.nodes[node_id]
    net.out_edges.pop(node_id, None)
    if node_id in net.junction_nodes:
        net.junction_nodes.remove(node_id)
    rebuild_derived(net)


def toggle_junction_signal(net: NetworkData, node_id: int) -> bool:
    """Toggles whether `node_id` is a manually-configured signalized
    junction (twin/editor.py's T key). Returns the new state (True = now
    signalized, with an empty approach rotation to add to next). Turning
    off drops it from both `junction_nodes` and `signal_approaches`."""
    if node_id in net.signal_approaches:
        del net.signal_approaches[node_id]
        if node_id in net.junction_nodes:
            net.junction_nodes.remove(node_id)
        return False
    net.signal_approaches[node_id] = []
    if node_id not in net.junction_nodes:
        net.junction_nodes.append(node_id)
    return True


def toggle_signal_approach(net: NetworkData, node_id: int, edge_idx: int) -> bool:
    """Toggles edge `edge_idx` into/out of `node_id`'s round-robin rotation
    (twin/editor.py's A key) as its own single-edge slot, appending to the
    end when adding - rotation order is click order. No-op (returns False)
    if `node_id` isn't currently a manually-configured junction, or the
    edge doesn't actually arrive there. (A richer multi-edge slot, where a
    whole approach's several lanes go green together, can only come from an
    import like twin/lane_network_import.py - the editor always deals in
    one edge at a time.)"""
    if node_id not in net.signal_approaches:
        return False
    edge = net.edges[edge_idx]
    if edge.v != node_id:
        return False
    slot = [(edge.u, edge.v)]
    slots = net.signal_approaches[node_id]
    if slot in slots:
        slots.remove(slot)
    else:
        slots.append(slot)
    return True


def rebuild_derived(net: NetworkData):
    """Fully recomputes everything derived from `nodes`/`edges` after an
    edit - out_edges, entry/exit nodes, the routing graph, and bounds.
    Simplest and safest option given edits are rare, user-triggered, and
    this network is only ~50-100 nodes: edge-list indices shift on removal,
    so patching these incrementally isn't worth it."""
    out_edges: dict[int, list[int]] = {n: [] for n in net.nodes}
    for i, e in enumerate(net.edges):
        out_edges.setdefault(e.u, []).append(i)
    net.out_edges = out_edges

    in_deg: dict[int, int] = {n: 0 for n in net.nodes}
    out_deg: dict[int, int] = {n: 0 for n in net.nodes}
    for e in net.edges:
        out_deg[e.u] = out_deg.get(e.u, 0) + 1
        in_deg[e.v] = in_deg.get(e.v, 0) + 1
    net.entry_nodes = [n for n in net.nodes if in_deg.get(n, 0) == 0]
    net.exit_nodes = [n for n in net.nodes if out_deg.get(n, 0) == 0]

    # A hand-drawn dead end (exactly one neighbor, connected both ways -
    # add_road always creates a bidirectional pair, so it never satisfies
    # in_deg==0/out_deg==0 the way an OSM-clipped boundary naturally does)
    # still represents "off the edge of the drawn area" - so it's both a
    # valid entry (vehicles spawn heading in) and exit (heading out).
    # Without this, a network built entirely by hand in the editor would
    # have no spawn points at all.
    neighbors: dict[int, set[int]] = {n: set() for n in net.nodes}
    for e in net.edges:
        neighbors[e.u].add(e.v)
        neighbors[e.v].add(e.u)
    for n, neighs in neighbors.items():
        if len(neighs) == 1 and in_deg.get(n, 0) >= 1 and out_deg.get(n, 0) >= 1:
            if n not in net.entry_nodes:
                net.entry_nodes.append(n)
            if n not in net.exit_nodes:
                net.exit_nodes.append(n)

    # a fully closed network (every node has 2+ neighbors - e.g. a loop of
    # roads with no dangling stub anywhere) has no boundary at all under
    # either rule above, which would otherwise mean zero entry/exit nodes
    # and the spawner (twin/spawner.py) never placing a single vehicle.
    # Rather than silently simulating nothing, fall back to spawning and
    # despawning at any node - traffic just does local trips within
    # whatever was actually drawn.
    if not net.entry_nodes and not net.exit_nodes and net.nodes:
        net.entry_nodes = list(net.nodes)
        net.exit_nodes = list(net.nodes)

    net.junction_nodes = [n for n in net.junction_nodes if n in net.nodes]

    # drop any manually-configured approach edge whose (u, v) no longer
    # exists (the road was deleted), any slot left with no edges at all as
    # a result, and any junction node that no longer exists
    valid_uv = {(e.u, e.v) for e in net.edges}
    for node in list(net.signal_approaches):
        if node not in net.nodes:
            del net.signal_approaches[node]
            continue
        pruned_slots = []
        for slot in net.signal_approaches[node]:
            pruned = [uv for uv in slot if uv in valid_uv]
            if pruned:
                pruned_slots.append(pruned)
        net.signal_approaches[node] = pruned_slots

    g = nx.MultiDiGraph()
    for n, (lon, lat) in net.nodes.items():
        g.add_node(n, x=lon, y=lat)
    for e in net.edges:
        g.add_edge(e.u, e.v, key=e.key, length=e.length_m)
    net.graph = g

    if net.nodes:
        lons = [lon for lon, _ in net.nodes.values()]
        lats = [lat for _, lat in net.nodes.values()]
        net.bounds = (min(lons), min(lats), max(lons), max(lats))


def shortest_route(net: NetworkData, start: int, end: int) -> list[int] | None:
    """Returns a list of edge indices (into net.edges) from start to end, or
    None if unreachable."""
    try:
        node_path = nx.shortest_path(net.graph, start, end, weight="length")
    except nx.NetworkXNoPath:
        return None
    route = []
    for u, v in zip(node_path[:-1], node_path[1:]):
        candidates = [i for i in net.out_edges[u] if net.edges[i].v == v]
        if not candidates:
            return None
        # prefer the shortest parallel edge (matches nx's own weighting)
        route.append(min(candidates, key=lambda i: net.edges[i].length_m))
    return route


def edge_bearing_at_end(edge: Edge) -> float:
    """Compass bearing (degrees, 0=N/east-CW... using atan2 convention) of
    travel direction on the last segment of the edge, i.e. the direction
    traffic is heading as it arrives at `edge.v`."""
    coords = list(edge.geo_line.coords)
    (lon1, lat1), (lon2, lat2) = coords[-2], coords[-1]
    return math.degrees(math.atan2(lon2 - lon1, lat2 - lat1)) % 360


def edge_bearing_at_start(edge: Edge) -> float:
    """Same as edge_bearing_at_end but for the direction traffic is already
    heading as it leaves `edge.u` - i.e. the departure heading onto this
    edge, not the arrival heading."""
    coords = list(edge.geo_line.coords)
    (lon1, lat1), (lon2, lat2) = coords[0], coords[1]
    return math.degrees(math.atan2(lon2 - lon1, lat2 - lat1)) % 360


def turn_angle_deg(edge_in: Edge, edge_out: Edge) -> float:
    """Signed turn angle (degrees) from edge_in's arrival heading to
    edge_out's departure heading, normalized to (-180, 180]. Negative =
    turning left (counterclockwise), positive = turning right (clockwise),
    near 0 = essentially straight through."""
    incoming = edge_bearing_at_end(edge_in)
    outgoing = edge_bearing_at_start(edge_out)
    return ((outgoing - incoming + 180) % 360) - 180


# Buckets for turn_angle_deg used to assign vehicles a lane matching their
# actual movement (twin/engine.py) - distinct from engine.py's own narrower
# LEFT_TURN_MIN/MAX_DEG, which decides whether a left turn may skip the stop
# line (a right-of-way rule), not which lane it belongs in.
STRAIGHT_MAX_DEG = 45.0
UTURN_MIN_DEG = 135.0


def classify_turn(angle: float) -> str:
    """Which of the 4 movements a turn_angle_deg() angle represents:
    "straight", "left", "right", or "uturn". Symmetric buckets, unlike
    engine.py's own left-turn-only threshold, since every movement needs a
    lane assignment, not just left turns."""
    a = abs(angle)
    if a <= STRAIGHT_MAX_DEG:
        return "straight"
    if a >= UTURN_MIN_DEG:
        return "uturn"
    return "left" if angle < 0 else "right"


def resolve_pinned_edges(net: NetworkData, signal_light_coords: tuple[tuple[float, float], ...]) -> list[int]:
    """For each (lat, lon) given, returns the index of whichever approach
    edge reaches its junction nearest to that point - in the same order the
    coordinates were given. Shared by SignalController and Renderer so both
    agree on which real-world position refers to which edge; matched purely
    by real geographic distance (not screen pixels), so it doesn't depend on
    zoom/pan state."""
    incoming = [i for i, e in enumerate(net.edges) if e.v in net.junction_nodes]
    pinned = []
    for lat, lon in signal_light_coords:
        if not incoming:
            break
        nearest = min(incoming, key=lambda i: _approach_dist(net.edges[i], lat, lon))
        pinned.append(nearest)
    return pinned


def resolve_pinned_positions(net: NetworkData, signal_light_coords: tuple[tuple[float, float], ...]) -> dict[int, tuple[float, float]]:
    """edge_idx -> (lat, lon) for each given coordinate, matched the same
    way resolve_pinned_edges does."""
    return dict(zip(resolve_pinned_edges(net, signal_light_coords), signal_light_coords))


def _approach_dist(edge: Edge, lat: float, lon: float) -> float:
    # 1.0 (the edge's very last point) is the shared junction node itself -
    # identical for every approach, so it can't tell them apart. A bit short
    # of that, still on this specific approach road, actually distinguishes
    # which real-world corner a coordinate is nearest to.
    fraction = max(0.0, 1.0 - 10.0 / edge.length_m)
    p = edge.geo_line.interpolate(fraction, normalized=True)
    return (p.x - lon) ** 2 + (p.y - lat) ** 2


def signal_stop_line_m(edge: Edge, pinned_latlon: tuple[float, float] | None) -> float:
    """Distance (meters) back from the junction end of this edge where its
    stop line sits - both the physics stop point and the drawn light are
    derived from this, so a vehicle always stops exactly at the light, never
    past it. A real given position is projected onto the edge to find how
    far back it actually is; otherwise a generic default is used. Either
    way, capped so it can never overshoot past the edge's own start."""
    if pinned_latlon is not None:
        lat, lon = pinned_latlon
        frac = edge.geo_line.project(Point(lon, lat), normalized=True)
        setback = edge.length_m * (1.0 - frac)
    else:
        setback = DEFAULT_SIGNAL_SETBACK_M
    return min(max(0.0, setback), edge.length_m * 0.4)


def signal_stop_point(edge: Edge, pinned_latlon: tuple[float, float] | None) -> tuple[float, float]:
    """(lon, lat) of the same stop line signal_stop_line_m describes."""
    setback = signal_stop_line_m(edge, pinned_latlon)
    frac = max(0.0, 1.0 - setback / edge.length_m)
    p = edge.geo_line.interpolate(frac, normalized=True)
    return p.x, p.y
