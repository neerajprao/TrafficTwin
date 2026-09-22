"""
Phase 2 (rebuilt) - pygame renderer: draws the real satellite backdrop, the
road geometry, the junction's live signal state, and every vehicle as a
small oriented, type-colored icon, plus a HUD with sim clock/vehicle count.
Everything is drawn through a Camera (see camera.py) so the view can be
panned and zoomed like a map.
"""
import math

import pygame

from .basemap import PixelMapper
from .camera import Camera
from .editor import RoadEditor
from .engine import SimulationEngine
from .network import NetworkData, signal_stop_point
from .signals import GREEN, RED, YELLOW
from .slider import HANDLE_RADIUS_PX, TRACK_HEIGHT_PX, SpeedSlider
from .vehicle import VEHICLE_TYPES

LANE_WIDTH_M = 3.2
ROAD_COLOR = (255, 255, 255)
ROAD_ALPHA = 90
SIGNAL_COLORS = {GREEN: (0, 220, 0), YELLOW: (240, 200, 0), RED: (220, 0, 0)}
HUD_COLOR = (255, 255, 255)
HUD_BG = (0, 0, 0, 140)
NODE_COLOR = (80, 160, 255)
JUNCTION_NODE_COLOR = (220, 40, 40)
APPROACH_MARKER_COLOR = (0, 220, 0)
SELECTED_COLOR = (255, 220, 0)
DRAG_LINE_COLOR = (255, 255, 255)
SLIDER_TRACK_COLOR = (120, 120, 120)
SLIDER_HANDLE_COLOR = (255, 255, 255)


class Renderer:
    def __init__(self, screen: pygame.Surface, basemap_surface: pygame.Surface,
                 net: NetworkData, pixel_mapper: PixelMapper, camera: Camera):
        self.screen = screen
        self.basemap_raw = basemap_surface  # native resolution, unscaled
        self.net = net
        self.pm = pixel_mapper
        self.camera = camera
        self.font = pygame.font.SysFont("menlo,monospace", 18)

        self._road_points = [
            [self.pm.to_pixel(lon, lat) for lon, lat in edge.geo_line.coords]
            for edge in net.edges
        ]
        self.overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)

        self._basemap_scaled = self.basemap_raw
        self._basemap_scaled_zoom = None

        # one signal-light position per approach edge, drawn at exactly the
        # same point network.signal_stop_line_m has vehicles actually stop
        # at - never separately estimated, so a vehicle can't stop past a
        # light it's supposed to be obeying. Which edges actually get a
        # light comes from net.signal_approaches (set by hand in the editor,
        # see editor.py's T/A keys); once a junction has any approach
        # configured, its other approaches simply don't get a light drawn -
        # they weren't added to the rotation.
        edge_index_by_uv = {(e.u, e.v): i for i, e in enumerate(net.edges)}
        self._configured_junctions = set(net.signal_approaches.keys())
        self._pinned_edges = {
            edge_index_by_uv[uv]
            for slots in net.signal_approaches.values()
            for slot in slots
            for uv in slot
            if uv in edge_index_by_uv
        }
        self._signal_positions = {
            i: self.pm.to_pixel(*signal_stop_point(edge, None))
            for i, edge in enumerate(net.edges)
        }

    def _draw_basemap(self):
        cam = self.camera
        if cam.zoom != self._basemap_scaled_zoom:
            raw_w, raw_h = self.basemap_raw.get_size()
            size = (max(1, round(raw_w * cam.zoom)), max(1, round(raw_h * cam.zoom)))
            self._basemap_scaled = pygame.transform.smoothscale(self.basemap_raw, size)
            self._basemap_scaled_zoom = cam.zoom
        self.screen.blit(self._basemap_scaled, (cam.offset_x, cam.offset_y))

    def _draw_roads(self):
        self.overlay.fill((0, 0, 0, 0))
        for edge, raw_pts in zip(self.net.edges, self._road_points):
            pts = [self.camera.to_screen(x, y) for x, y in raw_pts]
            width = max(1, round(edge.lanes * 3 * self.camera.zoom))
            pygame.draw.lines(self.overlay, (*ROAD_COLOR, ROAD_ALPHA), False, pts, width)
        self.screen.blit(self.overlay, (0, 0))

    def _vehicle_heading(self, edge_idx: int, fraction: float) -> float:
        edge = self.net.edges[edge_idx]
        p1 = edge.geo_line.interpolate(max(0.0, fraction - 0.01), normalized=True)
        p2 = edge.geo_line.interpolate(min(1.0, fraction + 0.01), normalized=True)
        px1, py1 = self.pm.to_pixel(p1.x, p1.y)
        px2, py2 = self.pm.to_pixel(p2.x, p2.y)
        return math.degrees(math.atan2(py2 - py1, px2 - px1))

    def _draw_vehicle(self, edge_idx: int, dist_along: float, lane: int, vtype: str):
        edge = self.net.edges[edge_idx]
        fraction = max(0.0, min(1.0, dist_along / edge.length_m))
        point = edge.geo_line.interpolate(fraction, normalized=True)
        raw_x, raw_y = self.pm.to_pixel(point.x, point.y)
        heading = self._vehicle_heading(edge_idx, fraction)

        # offset sideways from the centerline so vehicles spread across the
        # road's actual lane width instead of stacking on one line
        lane_offset_m = (lane - (edge.lanes - 1) / 2) * LANE_WIDTH_M
        lane_offset_px = lane_offset_m / self.pm.meters_per_pixel
        heading_rad = math.radians(heading)
        raw_x += lane_offset_px * math.sin(heading_rad)
        raw_y -= lane_offset_px * math.cos(heading_rad)

        px, py = self.camera.to_screen(raw_x, raw_y)
        px_per_m = self.camera.zoom / self.pm.meters_per_pixel

        params = VEHICLE_TYPES[vtype]
        length_px = max(3, params["length"] * px_per_m)
        width_px = max(2, params["width"] * px_per_m)

        surf = pygame.Surface((length_px, width_px), pygame.SRCALPHA)
        pygame.draw.rect(surf, params["color"], (0, 0, length_px, width_px), border_radius=2)
        rotated = pygame.transform.rotate(surf, -heading)
        rect = rotated.get_rect(center=(px, py))
        self.screen.blit(rotated, rect)

    def _draw_signals(self, engine: SimulationEngine):
        z = self.camera.zoom
        for edge_idx in engine.signals.incoming_edges:
            edge = self.net.edges[edge_idx]
            if edge.v in self._configured_junctions and edge_idx not in self._pinned_edges:
                continue
            state = engine.signals.state_for_edge(edge_idx)
            raw_x, raw_y = self._signal_positions[edge_idx]
            sx, sy = self.camera.to_screen(raw_x, raw_y)
            color = SIGNAL_COLORS[state]
            pygame.draw.circle(self.screen, (20, 20, 20), (sx, sy), 6 * z)
            pygame.draw.circle(self.screen, color, (sx, sy), 4.5 * z)

    def _draw_hud(self, engine: SimulationEngine, fps: float, editing: bool, move_network_mode: bool = False):
        if move_network_mode:
            text = "MOVE-NETWORK MODE - drag anywhere to shift all roads together, M: stop moving, E: resume"
        elif editing:
            text = ("EDIT MODE - click empty space: new node, drag from a node: draw road, "
                    "click a road: select (1-9 sets lanes), select a node + T: toggle signal "
                    "junction (red), select a road into one + A: add/remove from its rotation "
                    "(green # = order), Delete: remove (Shift+Delete for a signal junction), "
                    "M: move whole network, S: save, E: resume")
        else:
            elapsed = int(engine.sim_time)
            text = (f"sim time {elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
                    f"   vehicles {len(engine.vehicles)}   zoom {self.camera.zoom:.1f}x   fps {fps:.0f}"
                    f"   [drag to pan, scroll to zoom, R to reset, E to edit roads]")
        surf = self.font.render(text, True, HUD_COLOR)
        bg = pygame.Surface((surf.get_width() + 16, surf.get_height() + 10), pygame.SRCALPHA)
        bg.fill(HUD_BG)
        self.screen.blit(bg, (8, 8))
        self.screen.blit(surf, (16, 13))

    def _draw_speed_slider(self, slider: SpeedSlider):
        label = self.font.render(f"speed {slider.value:.1f}x", True, HUD_COLOR)
        bg = pygame.Surface((label.get_width() + 16, label.get_height() + 10), pygame.SRCALPHA)
        bg.fill(HUD_BG)
        bg_x = slider.track_x0 - 4
        bg_y = slider.track_y - label.get_height() - 14
        self.screen.blit(bg, (bg_x, bg_y))
        self.screen.blit(label, (bg_x + 8, bg_y + 5))

        pygame.draw.line(self.screen, SLIDER_TRACK_COLOR, (slider.track_x0, slider.track_y),
                          (slider.track_x1, slider.track_y), TRACK_HEIGHT_PX)
        hx, hy = slider.handle_pos()
        pygame.draw.circle(self.screen, SLIDER_HANDLE_COLOR, (hx, hy), HANDLE_RADIUS_PX)
        pygame.draw.circle(self.screen, (0, 0, 0), (hx, hy), HANDLE_RADIUS_PX, 1)

    def _draw_editor_overlay(self, editor: RoadEditor):
        z = self.camera.zoom

        if editor.selected_edge is not None:
            e = self.net.edges[editor.selected_edge]
            p1, p2 = editor.node_screen_pos(e.u), editor.node_screen_pos(e.v)
            pygame.draw.line(self.screen, SELECTED_COLOR, p1, p2, max(2, round(6 * z)))
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            label_text = f"lanes: {e.lanes}  (press 1-9)"
            slots = self.net.signal_approaches.get(e.v)
            if slots is not None:
                key = (e.u, e.v)
                position = next((i + 1 for i, slot in enumerate(slots) if key in slot), None)
                if position is not None:
                    label_text += f"   signal approach #{position} (A to remove)"
                else:
                    label_text += "   A: add to this junction's signal rotation"
            label = self.font.render(label_text, True, SELECTED_COLOR)
            self.screen.blit(label, (mid[0] + 10, mid[1] - 10))

        for n in self.net.nodes:
            if n == editor.selected_node:
                color = SELECTED_COLOR
            elif n in self.net.junction_nodes:
                color = JUNCTION_NODE_COLOR  # signalized junction (T to toggle) - not deletable
            else:
                color = NODE_COLOR
            pygame.draw.circle(self.screen, color, editor.node_screen_pos(n), max(3, 5 * z))

        # numbered markers for every approach already in some junction's
        # rotation, so the configured order is visible at a glance - all
        # edges sharing a slot (a whole approach's several lanes going
        # green together) show the same number
        edge_index_by_uv = {(edge.u, edge.v): i for i, edge in enumerate(self.net.edges)}
        for slots in self.net.signal_approaches.values():
            for position, slot in enumerate(slots, start=1):
                for uv in slot:
                    idx = edge_index_by_uv.get(uv)
                    if idx is None:
                        continue
                    raw_x, raw_y = self._signal_positions[idx]
                    sx, sy = self.camera.to_screen(raw_x, raw_y)
                    pygame.draw.circle(self.screen, (20, 20, 20), (sx, sy), 8 * z)
                    pygame.draw.circle(self.screen, APPROACH_MARKER_COLOR, (sx, sy), 6 * z)
                    label = self.font.render(str(position), True, (0, 0, 0))
                    self.screen.blit(label, label.get_rect(center=(sx, sy)))

        if editor.drag_from_node is not None and editor.drag_current is not None:
            pygame.draw.line(self.screen, DRAG_LINE_COLOR,
                              editor.node_screen_pos(editor.drag_from_node), editor.drag_current, 2)

    def draw(self, engine: SimulationEngine, fps: float, editor: RoadEditor | None = None,
              slider: SpeedSlider | None = None):
        self.screen.fill((0, 0, 0))
        self._draw_basemap()
        self._draw_roads()
        if editor is None:
            for v in engine.vehicles:
                self._draw_vehicle(v.current_edge, v.dist_along, v.lane, v.vtype)
            self._draw_signals(engine)
        else:
            self._draw_editor_overlay(editor)
        self._draw_hud(engine, fps, editing=editor is not None,
                       move_network_mode=editor is not None and editor.move_network_mode)
        if slider is not None:
            self._draw_speed_slider(slider)
