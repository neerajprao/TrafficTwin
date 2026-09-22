"""
Phase 2 (rebuilt) - in-app road editor. Lets you add, connect, and delete
roads directly in the pygame window instead of only ever loading whatever
OpenStreetMap happened to map. Wired into twin/app.py's event loop; drawn by
Renderer.draw_editor_overlay() in twin/render.py.

Interaction model (app.py disambiguates click vs. drag by mouse movement):
  - mousedown on an existing node, then drag, then release on another node
    (or empty space, which creates a new node there first) -> draws a road
  - click (no drag) on empty space -> places a standalone new node
  - click (no drag) on a node -> selects it (Delete removes it + its edges)
  - click (no drag) on a road -> selects it (1-9 sets lane count, Delete
    removes it)
  - drag starting on empty space is unchanged - still pans the camera
"""
import math

from shapely.affinity import translate

from .basemap import PixelMapper
from .camera import Camera
from .network import (NetworkData, add_node, add_road, rebuild_derived, remove_edge, remove_node,
                       toggle_junction_signal, toggle_signal_approach)

NODE_HIT_RADIUS_PX = 14
EDGE_HIT_RADIUS_PX = 8
CLICK_MOVE_THRESHOLD_PX = 5


def _point_segment_dist(p, a, b) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class RoadEditor:
    def __init__(self, net: NetworkData, pm: PixelMapper, camera: Camera):
        self.net = net
        self.pm = pm
        self.camera = camera
        self.selected_node: int | None = None
        self.selected_edge: int | None = None
        self.drag_from_node: int | None = None
        self.drag_current: tuple[float, float] | None = None
        self.move_network_mode = False
        self._move_last_screen: tuple[float, float] | None = None

    def node_screen_pos(self, node_id: int) -> tuple[float, float]:
        lon, lat = self.net.nodes[node_id]
        return self.camera.to_screen(*self.pm.to_pixel(lon, lat))

    def hit_test_node(self, screen_pos: tuple[float, float]) -> int | None:
        best, best_d = None, NODE_HIT_RADIUS_PX
        for n in self.net.nodes:
            d = math.hypot(*(a - b for a, b in zip(self.node_screen_pos(n), screen_pos)))
            if d < best_d:
                best, best_d = n, d
        return best

    def hit_test_edge(self, screen_pos: tuple[float, float]) -> int | None:
        best, best_d = None, EDGE_HIT_RADIUS_PX
        for i, e in enumerate(self.net.edges):
            d = _point_segment_dist(screen_pos, self.node_screen_pos(e.u), self.node_screen_pos(e.v))
            if d < best_d:
                best, best_d = i, d
        return best

    def clear_selection(self):
        self.selected_node = None
        self.selected_edge = None

    def on_mouse_down(self, screen_pos: tuple[float, float]) -> bool:
        """Returns True if this press started a road-drag (from a node) -
        the caller should not also treat this as the start of a pan."""
        node = self.hit_test_node(screen_pos)
        if node is not None:
            self.drag_from_node = node
            self.drag_current = screen_pos
            return True
        return False

    def on_mouse_motion(self, screen_pos: tuple[float, float]):
        if self.drag_from_node is not None:
            self.drag_current = screen_pos

    def on_mouse_up(self, screen_pos: tuple[float, float], moved: bool) -> bool:
        """Returns True if the network topology changed (caller should
        rebuild SimulationEngine/Renderer)."""
        if self.drag_from_node is not None:
            start = self.drag_from_node
            self.drag_from_node = None
            self.drag_current = None
            if not moved:
                self.selected_node = start
                self.selected_edge = None
                return False
            target = self.hit_test_node(screen_pos)
            if target is None:
                raw_x, raw_y = self.camera.from_screen(*screen_pos)
                lon, lat = self.pm.to_lonlat(raw_x, raw_y)
                target = add_node(self.net, lon, lat)
            if target != start:
                add_road(self.net, start, target)
                self.clear_selection()
                return True
            return False

        if moved:
            return False  # was a pan over empty space

        edge = self.hit_test_edge(screen_pos)
        if edge is not None:
            self.selected_edge = edge
            self.selected_node = None
            return False

        raw_x, raw_y = self.camera.from_screen(*screen_pos)
        lon, lat = self.pm.to_lonlat(raw_x, raw_y)
        add_node(self.net, lon, lat)
        self.clear_selection()
        return True

    def toggle_move_network_mode(self):
        self.move_network_mode = not self.move_network_mode
        self._move_last_screen = None
        self.clear_selection()

    def begin_move_network(self, screen_pos: tuple[float, float]):
        self._move_last_screen = screen_pos

    def drag_move_network(self, screen_pos: tuple[float, float]) -> bool:
        """Shifts every node AND every edge's actual road geometry
        (geo_line - what the renderer draws, which for real OSM roads has
        its own curved interior points, not just the two endpoint nodes) by
        the real-world (lon/lat) delta implied by the screen-space mouse
        movement, so the whole network can be nudged to realign with the
        satellite basemap as one rigid block. Returns True if it moved
        anything (caller should refresh the renderer)."""
        if self._move_last_screen is None:
            self._move_last_screen = screen_pos
            return False
        last = self._move_last_screen
        self._move_last_screen = screen_pos
        if last == screen_pos:
            return False
        lon0, lat0 = self.pm.to_lonlat(*self.camera.from_screen(*last))
        lon1, lat1 = self.pm.to_lonlat(*self.camera.from_screen(*screen_pos))
        dlon, dlat = lon1 - lon0, lat1 - lat0
        for n, (lon, lat) in self.net.nodes.items():
            self.net.nodes[n] = (lon + dlon, lat + dlat)
        for e in self.net.edges:
            e.geo_line = translate(e.geo_line, xoff=dlon, yoff=dlat)
        rebuild_derived(self.net)
        return True

    def end_move_network(self):
        self._move_last_screen = None

    def toggle_selected_junction(self) -> bool:
        """Toggles whether the selected node is a manually-configured
        signal junction (T key). Returns True if it did anything (a node
        was actually selected) - caller should mark the network edited and
        rebuild the sim, since SignalController bakes this in at construction."""
        if self.selected_node is None:
            return False
        toggle_junction_signal(self.net, self.selected_node)
        return True

    def toggle_selected_approach(self) -> bool:
        """Toggles the selected road into/out of its far end's signal
        rotation (A key) - only does something when that far end is
        currently a manually-configured junction (drawn red after T)."""
        if self.selected_edge is None:
            return False
        edge = self.net.edges[self.selected_edge]
        return toggle_signal_approach(self.net, edge.v, self.selected_edge)

    def set_selected_lanes(self, lanes: int):
        if self.selected_edge is None:
            return
        edge = self.net.edges[self.selected_edge]
        for e in self.net.edges:
            if {e.u, e.v} == {edge.u, edge.v}:
                e.lanes = lanes

    def delete_selected(self, force: bool = False) -> bool:
        if self.selected_node is not None:
            if self.selected_node in self.net.junction_nodes and not force:
                print("That's a real signalized junction - hold Shift+Delete to remove it anyway "
                      "(this also removes its traffic light and every road that meets there).")
                return False
            remove_node(self.net, self.selected_node, force=force)
            self.clear_selection()
            return True
        if self.selected_edge is not None:
            edge = self.net.edges[self.selected_edge]
            to_delete = [i for i, e in enumerate(self.net.edges) if {e.u, e.v} == {edge.u, edge.v}]
            for i in sorted(to_delete, reverse=True):
                remove_edge(self.net, i)
            self.clear_selection()
            return True
        return False
