"""
Phase 2 (rebuilt) - a Google Maps-style camera: uniform zoom plus pan offset
on top of the raw basemap-pixel space that PixelMapper produces. Shared by
twin/render.py and any place (e.g. mg_road/run.py) that reuses it.
"""
from dataclasses import dataclass

MIN_ZOOM = 0.4
MAX_ZOOM = 8.0


@dataclass
class Camera:
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x * self.zoom + self.offset_x, y * self.zoom + self.offset_y

    def from_screen(self, sx: float, sy: float) -> tuple[float, float]:
        """Inverse of to_screen - turns a mouse position back into raw
        basemap-pixel space, for the road editor's hit-testing."""
        return (sx - self.offset_x) / self.zoom, (sy - self.offset_y) / self.zoom

    def pan(self, dx: float, dy: float):
        self.offset_x += dx
        self.offset_y += dy

    def zoom_at(self, screen_x: float, screen_y: float, factor: float):
        """Zooms in/out by `factor`, keeping the point currently under
        (screen_x, screen_y) fixed on screen - the same feel as scrolling
        the mouse wheel over a spot on Google Maps."""
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        applied = new_zoom / self.zoom
        self.offset_x = screen_x - (screen_x - self.offset_x) * applied
        self.offset_y = screen_y - (screen_y - self.offset_y) * applied
        self.zoom = new_zoom
