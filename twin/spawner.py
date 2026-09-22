"""
Phase 2 (rebuilt) - spawns vehicles at the network's boundary entry nodes as
a Poisson process per type, then routes each one via shortest path to a
random exit node. Turning-movement calibration (matching real turn-share
counts) is out of scope for this v1 - shortest-path routing naturally sends
most traffic through the junction, which is enough for a working twin.
"""
import random

from .network import NetworkData, shortest_route
from .vehicle import Vehicle

# Same calibrated vehicles/hour as scripts/generate_demand.py's MODE_SPLIT -
# duplicated here (not imported) to keep this package independent of the
# SUMO-pipeline scripts directory. Keep these two in sync if recalibrated.
MODE_SPLIT = {
    "motorcycle": 2260,
    "car": 1080,
    "van": 270,
    "truck": 480,
    "bus": 240,
}


class Spawner:
    def __init__(self, net: NetworkData, seed: int = 42):
        self.net = net
        self.rng = random.Random(seed)
        self.next_spawn_time = {
            vtype: self.rng.expovariate(vph / 3600.0) for vtype, vph in MODE_SPLIT.items()
        }
        self._next_id = 0

    def _make_route(self) -> list[int] | None:
        if not self.net.entry_nodes or not self.net.exit_nodes:
            return None  # blank/unfinished canvas - nothing to spawn onto yet
        entry = self.rng.choice(self.net.entry_nodes)
        exits = [n for n in self.net.exit_nodes if n != entry]
        self.rng.shuffle(exits)
        for exit_node in exits:
            route = shortest_route(self.net, entry, exit_node)
            if route:
                return route
        return None

    def step(self, sim_time: float) -> list[Vehicle]:
        """Returns newly spawned vehicles due as of sim_time."""
        spawned = []
        for vtype, vph in MODE_SPLIT.items():
            while sim_time >= self.next_spawn_time[vtype]:
                route = self._make_route()
                if route:
                    self._next_id += 1
                    spawned.append(Vehicle(id=self._next_id, vtype=vtype, route=route))
                self.next_spawn_time[vtype] += self.rng.expovariate(vph / 3600.0)
        return spawned
