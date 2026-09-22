"""
Phase 2 (rebuilt) - the simulation loop: advances every vehicle's IDM
car-following physics each tick, spawns new vehicles, updates the traffic
signal, and despawns vehicles that reach a boundary exit. A vehicle's
"leader" can be a real vehicle on the same edge/lane, a virtual stop line at
a red/yellow signal (skipped entirely for a left-turning vehicle, since this
is left-hand traffic and a left turn never crosses oncoming traffic) or an
unsignalized junction with conflicting traffic, or (one edge of lookahead
only) whatever's already queued at the start of the next edge on its route.
"""
from .network import NetworkData, classify_turn, signal_stop_line_m, turn_angle_deg
from .signals import GREEN, SignalController
from .spawner import Spawner
from .vehicle import Vehicle

# Google Maps only shows a light at junctions OSM actually tags as
# signalized (see network.py) - every other junction (most of them) gets no
# light, but still needs *some* right-of-way rule so crossing traffic
# doesn't visibly drive through itself. This is a simple "whoever's already
# there/closer goes first" yield rule, not a real priority-road system.
YIELD_ZONE_M = 10.0  # a vehicle this close to an unsignalized junction is "approaching" it
CLEARANCE_M = 6.0  # a vehicle this far past a junction still counts as "occupying" it

# Indonesia (and this whole project's real places so far) drives on the
# left, so a left turn never crosses oncoming traffic - the equivalent of
# "right turn on red" in a right-hand-traffic country, and skips the stop
# line entirely. Angles closer to 0 than LEFT_TURN_MAX_DEG are basically
# straight, not a real turn; angles beyond LEFT_TURN_MIN_DEG are a U-turn,
# which still has to stop like any other turn that crosses the junction.
LEFT_TURN_MAX_DEG = -20.0
LEFT_TURN_MIN_DEG = -160.0

# Which lane range (0 = rightmost, edge.lanes-1 = leftmost - see
# render.py's lane-offset convention) each movement uses on an approach with
# a given lane count, so a vehicle sits in the correct lane in advance of
# its turn instead of a random one. Modeled on real Indonesian junctions:
# left-hand traffic keeps the U-turn/right-turn lanes nearest the median
# (rightmost) and the left-turn lane nearest the curb (leftmost), with
# through traffic in between - the mirror image of a right-hand-traffic
# layout. Movements share a lane when there aren't enough lanes to give
# each one its own; with 4+ lanes every movement gets a dedicated lane and
# any extra lanes fold into "straight", the most common movement.
def _lane_range_for_movement(movement: str, lanes: int) -> tuple[int, int]:
    if lanes == 1:
        return 0, 1
    if lanes == 2:
        return (0, 1) if movement in ("uturn", "right") else (1, 2)
    if lanes == 3:
        if movement in ("uturn", "right"):
            return 0, 1
        return (1, 2) if movement == "straight" else (2, 3)
    if movement == "uturn":
        return 0, 1
    if movement == "right":
        return 1, 2
    if movement == "left":
        return lanes - 1, lanes
    return 2, lanes - 1  # straight fills every lane between right and left


class SimulationEngine:
    def __init__(self, net: NetworkData, seed: int = 42):
        self.net = net
        self.spawner = Spawner(net, seed=seed)
        self.signals = SignalController(net)
        self.yield_nodes = self._compute_yield_nodes()
        self.vehicles: list[Vehicle] = []
        self.sim_time = 0.0

        # a vehicle stops at the signal's actual position, not the far edge
        # boundary - matches whatever the renderer draws the light at
        # (network.signal_stop_line_m is the single source of truth for both)
        self.stop_line_setback_m = {
            i: signal_stop_line_m(net.edges[i], None)
            for i in self.signals.incoming_edges
        }

    def _compute_yield_nodes(self) -> set[int]:
        """Every junction with 2+ approaches. Includes signalized junctions
        too - harmless, since `_leader_gap` only falls through to the yield
        check when a specific edge has no signal state at all (state is
        None), which covers the case where only *some* of a junction's
        approaches are confirmed-signalized and the rest need to yield."""
        in_degree: dict[int, int] = {}
        for e in self.net.edges:
            in_degree[e.v] = in_degree.get(e.v, 0) + 1
        return {n for n, d in in_degree.items() if d >= 2}

    def _is_left_turn(self, v: Vehicle) -> bool:
        if v.route_idx + 1 >= len(v.route):
            return False
        current_edge = self.net.edges[v.current_edge]
        next_edge = self.net.edges[v.route[v.route_idx + 1]]
        angle = turn_angle_deg(current_edge, next_edge)
        return LEFT_TURN_MIN_DEG <= angle <= LEFT_TURN_MAX_DEG

    def _lane_for(self, v: Vehicle, route_idx: int) -> int:
        """Which lane of v.route[route_idx] the vehicle belongs in, based on
        the turn it will make at the end of that edge onto the next edge in
        its route - so it's already positioned correctly in advance, the
        way a real driver picks a lane before their turn rather than after
        it. Falls back to a deterministic spread when there's no next edge
        (end of route) or only one lane (no choice to make)."""
        edge = self.net.edges[v.route[route_idx]]
        if edge.lanes <= 1:
            return 0
        if route_idx + 1 >= len(v.route):
            return v.id % edge.lanes
        next_edge = self.net.edges[v.route[route_idx + 1]]
        movement = classify_turn(turn_angle_deg(edge, next_edge))
        start, end = _lane_range_for_movement(movement, edge.lanes)
        return start + v.id % (end - start)

    def _node_conflicts(self, lane_vehicles: dict[tuple[int, int], list[Vehicle]]):
        """For every unsignalized junction with traffic near it right now:
        `occupant_by_node` names an edge whose vehicle is still physically
        inside the junction (within CLEARANCE_M of having entered it), and
        `candidates_by_node` lists every other approach's front vehicle
        within YIELD_ZONE_M of reaching it."""
        occupant_by_node: dict[int, int] = {}
        for v in self.vehicles:
            edge = self.net.edges[v.current_edge]
            if edge.u in self.yield_nodes and v.dist_along < CLEARANCE_M:
                occupant_by_node.setdefault(edge.u, v.current_edge)

        candidates_by_node: dict[int, list[tuple[int, float]]] = {}
        for (edge_idx, _lane), group in lane_vehicles.items():
            edge = self.net.edges[edge_idx]
            if edge.v not in self.yield_nodes:
                continue
            front = group[0]
            remaining = edge.length_m - front.dist_along
            if remaining <= YIELD_ZONE_M:
                candidates_by_node.setdefault(edge.v, []).append((edge_idx, remaining))

        return occupant_by_node, candidates_by_node

    def _leader_gap(self, lane_vehicles: dict[tuple[int, int], list[Vehicle]], v: Vehicle,
                     occupant_by_node: dict[int, int], candidates_by_node: dict[int, list[tuple[int, float]]],
                     ) -> tuple[float | None, float | None]:
        """Returns (gap_m, leader_speed) ahead of `v` in its current lane:
        a real vehicle, a red/yellow stop line, a yield to conflicting
        traffic at an unsignalized junction, or (None, None) for clear road."""
        edge_idx = v.current_edge
        edge = self.net.edges[edge_idx]
        same_lane = lane_vehicles[(edge_idx, v.lane)]
        idx = same_lane.index(v)

        if idx > 0:
            leader = same_lane[idx - 1]
            gap = (leader.dist_along - leader.params["length"]) - v.dist_along
            return gap, leader.speed

        state = self.signals.state_for_edge(edge_idx)
        if state is not None and state != GREEN and not self._is_left_turn(v):
            stop_at = edge.length_m - self.stop_line_setback_m.get(edge_idx, 0.0)
            # only blocks if not past the line yet - a vehicle that already
            # crossed while it was green is committed and keeps going, same
            # as a real driver wouldn't slam the brakes mid-junction because
            # the light changed after they entered
            if v.dist_along < stop_at:
                gap = stop_at - v.dist_along
                return gap, 0.0

        if state is None and edge.v in self.yield_nodes:
            remaining = edge.length_m - v.dist_along
            occupant_edge = occupant_by_node.get(edge.v)
            if occupant_edge is not None and occupant_edge != edge_idx:
                return remaining, 0.0
            candidates = candidates_by_node.get(edge.v, [])
            if candidates:
                best_edge, _ = min(candidates, key=lambda c: c[1])
                if best_edge != edge_idx:
                    return remaining, 0.0

        # one-edge lookahead: without this, a vehicle with a clear road
        # ahead on its *current* edge accelerates right up to the edge
        # boundary with no visibility into whatever's already queued at the
        # start of the next edge, and gets dropped directly on top of it -
        # this closes that gap rather than leaving it as a v1 simplification.
        if v.route_idx + 1 < len(v.route):
            next_edge_idx = v.route[v.route_idx + 1]
            next_lane = self._lane_for(v, v.route_idx + 1)
            next_group = lane_vehicles.get((next_edge_idx, next_lane))
            if next_group:
                blocker = next_group[-1]  # smallest dist_along = nearest the entrance
                remaining = edge.length_m - v.dist_along
                gap = remaining + blocker.dist_along - blocker.params["length"]
                return gap, blocker.speed

        return None, None

    def step(self, dt: float):
        self.signals.update(dt)

        lane_vehicles: dict[tuple[int, int], list[Vehicle]] = {}
        for v in self.vehicles:
            lane_vehicles.setdefault((v.current_edge, v.lane), []).append(v)
        for group in lane_vehicles.values():
            group.sort(key=lambda v: v.dist_along, reverse=True)

        # only insert a spawn if there's physically room for it - otherwise
        # it lands right on top of whatever's already queued at the entry
        # point. Matches the old SUMO pipeline's own "insertion-limited"
        # behavior (not every generated trip got inserted there either) -
        # this is a real capacity limit, not just numbers being dropped.
        for v in self.spawner.step(self.sim_time):
            lane = self._lane_for(v, v.route_idx)
            group = lane_vehicles.setdefault((v.current_edge, lane), [])
            nearest = group[-1] if group else None
            if nearest is not None and nearest.dist_along < v.params["length"] + v.params["min_gap"]:
                continue
            v.lane = lane
            self.vehicles.append(v)
            group.append(v)
            group.sort(key=lambda vv: vv.dist_along, reverse=True)

        occupant_by_node, candidates_by_node = self._node_conflicts(lane_vehicles)

        for v in self.vehicles:
            gap, leader_speed = self._leader_gap(lane_vehicles, v, occupant_by_node, candidates_by_node)
            accel = v.idm_accel(gap, leader_speed)
            v.speed = max(0.0, v.speed + accel * dt)
            v.dist_along += v.speed * dt

        self._resolve_transitions()
        self.sim_time += dt

    def _resolve_transitions(self):
        """Moves every vehicle that reached the end of its edge onto the
        next one. This has to be authoritative, not just advisory like the
        lookahead braking in _leader_gap: several vehicles arriving from
        different edges/lanes can all target the same next (edge, lane) in
        the same tick, and only one snapshot-in-time check (as in
        _leader_gap) can't see them blocking each other. So this tracks
        actual occupancy as it goes, clamping a transitioning vehicle to
        stay behind whatever - pre-existing or already transitioned this
        tick - is nearest the entrance of its target lane, and parking it at
        the edge boundary to retry next tick if there's no room at all."""
        lane_front: dict[tuple[int, int], float] = {}
        pending: list[Vehicle] = []
        for v in self.vehicles:
            edge = self.net.edges[v.current_edge]
            if v.dist_along >= edge.length_m:
                pending.append(v)
            else:
                key = (v.current_edge, v.lane)
                if key not in lane_front or v.dist_along < lane_front[key]:
                    lane_front[key] = v.dist_along

        finished = []
        for v in sorted(pending, key=lambda v: v.id):
            edge = self.net.edges[v.current_edge]
            while v.dist_along >= edge.length_m:
                overflow = v.dist_along - edge.length_m
                if v.route_idx + 1 >= len(v.route):
                    finished.append(v)
                    break

                next_edge_idx = v.route[v.route_idx + 1]
                next_lane = self._lane_for(v, v.route_idx + 1)
                key = (next_edge_idx, next_lane)

                room = lane_front.get(key)
                if room is not None:
                    max_pos = room - v.params["length"] - v.params["min_gap"]
                    if max_pos <= 0:
                        v.dist_along = edge.length_m
                        v.speed = 0.0
                        break
                    overflow = min(overflow, max_pos)

                v.route_idx += 1
                v.dist_along = max(0.0, overflow)
                v.lane = next_lane
                lane_front[key] = v.dist_along
                edge = self.net.edges[v.current_edge]

        if finished:
            finished_ids = {v.id for v in finished}
            self.vehicles = [v for v in self.vehicles if v.id not in finished_ids]
