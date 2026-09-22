"""
Phase 2 (rebuilt) - vehicle physics for the custom digital twin. Per-type
parameters are ported directly from
sumo/astra_biz_center/astra_biz_center.vtypes.xml (not re-derived), so the
five vehicle types still match what was calibrated from the source video.
Motion uses the Intelligent Driver Model (IDM) for car-following.
"""
from dataclasses import dataclass

# length(m), width(m), min_gap(m), max_speed(m/s), accel(m/s^2), decel(m/s^2), color(RGB)
VEHICLE_TYPES = {
    "motorcycle": dict(length=2.0, width=0.8, min_gap=1.0, max_speed=25.0, accel=3.5, decel=5.0, color=(255, 230, 0)),
    "car":        dict(length=4.5, width=1.8, min_gap=2.0, max_speed=19.4, accel=2.6, decel=4.5, color=(180, 180, 180)),
    "van":        dict(length=5.5, width=2.0, min_gap=2.0, max_speed=16.7, accel=2.0, decel=4.0, color=(0, 105, 210)),
    "bus":        dict(length=12.0, width=2.5, min_gap=2.5, max_speed=15.0, accel=1.2, decel=3.5, color=(0, 155, 55)),
    "truck":      dict(length=8.0, width=2.5, min_gap=2.5, max_speed=14.0, accel=1.0, decel=3.5, color=(155, 80, 0)),
}

# Real observed urban speeds at this junction are much lower than each
# type's open-road max (PROGRESS.md logged ~5.5 m/s average under
# congestion) - cap desired cruising speed so the sim looks like this
# specific busy junction rather than an open highway.
URBAN_SPEED_CAP = 11.0  # m/s (~40 km/h)

IDM_TIME_HEADWAY = 1.3  # s, desired following gap in time
IDM_DELTA = 4  # acceleration exponent


@dataclass(eq=False)
class Vehicle:
    id: int
    vtype: str
    route: list[int]  # edge indices into NetworkData.edges
    route_idx: int = 0
    dist_along: float = 0.0  # meters into the current edge
    speed: float = 0.0  # m/s
    lane: int = 0  # lane index within the current edge, 0-based

    @property
    def params(self) -> dict:
        return VEHICLE_TYPES[self.vtype]

    @property
    def desired_speed(self) -> float:
        return min(self.params["max_speed"], URBAN_SPEED_CAP)

    @property
    def current_edge(self) -> int:
        return self.route[self.route_idx]

    def idm_accel(self, gap: float | None, leader_speed: float | None) -> float:
        """IDM acceleration given the gap (m) to whatever is ahead (a real
        leader vehicle or a red-light stop line) and that obstacle's speed
        (None means free road ahead)."""
        p = self.params
        v, v0, a, b = self.speed, self.desired_speed, p["accel"], p["decel"]

        free_road_term = 1.0 - (v / v0) ** IDM_DELTA if v0 > 0 else 0.0

        if leader_speed is None:
            return a * free_road_term

        dv = v - leader_speed
        s_star = p["min_gap"] + max(0.0, v * IDM_TIME_HEADWAY + (v * dv) / (2 * (a * b) ** 0.5))
        gap = max(gap, 0.1)
        interaction_term = (s_star / gap) ** 2
        return a * (free_road_term - interaction_term)
