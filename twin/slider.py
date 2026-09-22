"""
Phase 2 (rebuilt) - speed slider widget: a draggable HUD control (0.5x-5x)
for the simulation's time scale, drawn by Renderer._draw_speed_slider() and
driven by mouse events routed from twin/app.py's event loop.
"""
MIN_SPEED = 0.5
MAX_SPEED = 5.0

TRACK_WIDTH_PX = 140
TRACK_HEIGHT_PX = 4
HANDLE_RADIUS_PX = 8
MARGIN_PX = 16


class SpeedSlider:
    def __init__(self, screen_width: int):
        self.value = 1.0
        self.dragging = False
        # fixed top-right placement, clear of the HUD text on the left
        self.track_x0 = screen_width - MARGIN_PX - TRACK_WIDTH_PX
        self.track_x1 = screen_width - MARGIN_PX
        self.track_y = MARGIN_PX + 12

    def _value_to_x(self, value: float) -> float:
        frac = (value - MIN_SPEED) / (MAX_SPEED - MIN_SPEED)
        return self.track_x0 + frac * (self.track_x1 - self.track_x0)

    def _x_to_value(self, x: float) -> float:
        frac = (x - self.track_x0) / (self.track_x1 - self.track_x0)
        frac = max(0.0, min(1.0, frac))
        return MIN_SPEED + frac * (MAX_SPEED - MIN_SPEED)

    def handle_pos(self) -> tuple[float, float]:
        return self._value_to_x(self.value), self.track_y

    def hit_test(self, screen_pos: tuple[float, float]) -> bool:
        hx, hy = self.handle_pos()
        x, y = screen_pos
        if abs(y - self.track_y) > HANDLE_RADIUS_PX + 4:
            return False
        return self.track_x0 - HANDLE_RADIUS_PX <= x <= self.track_x1 + HANDLE_RADIUS_PX

    def on_mouse_down(self, screen_pos: tuple[float, float]) -> bool:
        """Returns True if this press landed on the slider (caller should
        not also treat it as the start of a pan/edit action)."""
        if not self.hit_test(screen_pos):
            return False
        self.dragging = True
        self.value = self._x_to_value(screen_pos[0])
        return True

    def on_mouse_motion(self, screen_pos: tuple[float, float]):
        if self.dragging:
            self.value = self._x_to_value(screen_pos[0])

    def on_mouse_up(self):
        self.dragging = False
