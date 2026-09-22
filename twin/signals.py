"""
Phase 2 (rebuilt) - traffic signals at every signalized junction in the
network. A junction manually configured in the editor or a richer import
(net.signal_approaches - twin/editor.py's T/A keys, or
twin/lane_network_import.py) cycles through its rotation slots one at a
time, GREEN_S seconds green then YELLOW_S yellow before the next slot's
green begins - no two slots green together, no phase invented for an
approach nobody added. A slot can be a single edge (the editor's own T/A
workflow, one lane at a time) or a whole group of edges that all go green
together (a richer import grouping a full approach's several lanes under
one real signal phase). A junction that's only in net.junction_nodes (e.g.
an untouched OSM `highway=traffic_signals` tag) falls back to a generic
bearing-based 2-phase program (opposing/through approaches share a phase),
echoing the real ~33s/33s timing already documented for Astra Biz Center in
PROGRESS.md.
"""
from .network import NetworkData, edge_bearing_at_end

GREEN_S = 33.0
YELLOW_S = 6.0
CYCLE_S = 2 * (GREEN_S + YELLOW_S)

RED, YELLOW, GREEN = "red", "yellow", "green"


def _phase_groups(net: NetworkData, node: int) -> list[list[int]]:
    incoming = [i for i, e in enumerate(net.edges) if e.v == node]
    if not incoming:
        return [[], []]

    axis_bearing = edge_bearing_at_end(net.edges[incoming[0]]) % 180
    group_a, group_b = [], []
    for i in incoming:
        bearing = edge_bearing_at_end(net.edges[i]) % 180
        diff = min(abs(bearing - axis_bearing), 180 - abs(bearing - axis_bearing))
        (group_a if diff < 45 else group_b).append(i)
    return [group_a, group_b]


class SignalController:
    def __init__(self, net: NetworkData):
        self.junction_nodes = net.junction_nodes

        edge_index_by_uv = {(e.u, e.v): i for i, e in enumerate(net.edges)}
        self.rotation_by_node: dict[int, list[list[int]]] = {}
        for node, slots in net.signal_approaches.items():
            resolved = [[edge_index_by_uv[uv] for uv in slot if uv in edge_index_by_uv] for slot in slots]
            resolved = [s for s in resolved if s]  # a slot whose only edge(s) got deleted
            if resolved:
                self.rotation_by_node[node] = resolved

        # only junctions with no manual config at all still use the
        # generic 2-phase fallback - a manually-configured junction (even
        # with zero slots added yet) never gets one invented for it
        self.groups_by_node = {
            node: _phase_groups(net, node)
            for node in self.junction_nodes if node not in net.signal_approaches
        }
        self.offset_by_node = {node: (node * 37.0) % CYCLE_S for node in self.groups_by_node}

        self.incoming_edges = (
            [i for slots in self.rotation_by_node.values() for slot in slots for i in slot]
            + [i for groups in self.groups_by_node.values() for group in groups for i in group]
        )
        self._edge_to_phase = {
            edge_idx: (node, group_idx)
            for node, groups in self.groups_by_node.items()
            for group_idx, group in enumerate(groups)
            for edge_idx in group
        }
        self._edge_to_rotation = {
            edge_idx: (node, position)
            for node, slots in self.rotation_by_node.items()
            for position, slot in enumerate(slots)
            for edge_idx in slot
        }

        self.time = 0.0

    def update(self, dt: float):
        self.time += dt

    def _phase_state(self, node: int, group_idx: int) -> str:
        t = (self.time + self.offset_by_node[node]) % CYCLE_S
        if group_idx == 0:
            if t < GREEN_S:
                return GREEN
            if t < GREEN_S + YELLOW_S:
                return YELLOW
            return RED
        else:
            offset = GREEN_S + YELLOW_S
            if t < offset:
                return RED
            if t < offset + GREEN_S:
                return GREEN
            return YELLOW

    def _rotation_state(self, node: int, position: int) -> str:
        slots = self.rotation_by_node[node]
        slot_len = GREEN_S + YELLOW_S
        cycle_len = slot_len * len(slots)
        t = self.time % cycle_len
        active = int(t // slot_len)
        if active != position:
            return RED
        return GREEN if (t % slot_len) < GREEN_S else YELLOW

    def state_for_edge(self, edge_idx: int) -> str | None:
        """None if this edge doesn't approach a signalized junction, or
        approaches one but wasn't added to its rotation (no signal control
        applies - it's handled as an ordinary yield junction)."""
        rotation = self._edge_to_rotation.get(edge_idx)
        if rotation is not None:
            return self._rotation_state(*rotation)
        phase = self._edge_to_phase.get(edge_idx)
        if phase is not None:
            return self._phase_state(*phase)
        return None
