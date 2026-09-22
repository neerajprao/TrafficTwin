"""
A coarse, discretized observation function for tabular Q-learning.

sumo-rl's DefaultObservationFunction returns a continuous vector (per-lane
density/queue), which isn't usable as a dict key for a tabular Q-table. This
collapses the state down to (current green phase, binned total queue at the
junction) - small enough for a Q-table to learn over a modest number of
episodes, while still capturing the two things that matter for a "should I
switch the light" decision.
"""
from gymnasium import spaces

from sumo_rl.environment.observations import ObservationFunction

QUEUE_BIN_EDGES = [2, 5, 10, 20, 40]  # -> 6 bins: 0-1, 2-4, 5-9, 10-19, 20-39, 40+
N_QUEUE_BINS = len(QUEUE_BIN_EDGES) + 1


def _bin_queue(queue: int) -> int:
    b = 0
    for edge in QUEUE_BIN_EDGES:
        if queue >= edge:
            b += 1
    return b


class HashableObs(tuple):
    """A tuple that also satisfies sumo-rl's `observation.copy()` call site."""

    def copy(self):
        return self


class DiscretizedObservationFunction(ObservationFunction):
    """Observation = (current_green_phase, binned_total_queue) as a hashable tuple."""

    def __call__(self):
        phase = self.ts.green_phase
        queue = self.ts.get_total_queued()
        return HashableObs((phase, _bin_queue(queue)))

    def observation_space(self):
        return spaces.MultiDiscrete([self.ts.num_green_phases, N_QUEUE_BINS])
