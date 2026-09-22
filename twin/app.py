"""
Phase 2 (rebuilt) - shared app loop for any place's digital twin (used by
both twin/run.py for Astra Biz Center and mg_road/run.py). Opens the pygame
window, runs the sim loop, and wires Google Maps-style controls (drag to
pan, scroll wheel to zoom centered on the cursor, R to reset the view) plus
the road editor (twin/editor.py): E toggles edit mode, which pauses the
simulation so roads can be added/connected/deleted, then resumes fresh.
"""
import math
import os
import sys

import pygame

from .basemap import CACHE_PATH as DEFAULT_BASEMAP_CACHE_PATH
from .basemap import ZOOM as BASEMAP_ZOOM
from .basemap import PixelMapper, load_basemap
from .camera import Camera
from .editor import CLICK_MOVE_THRESHOLD_PX, RoadEditor
from .engine import SimulationEngine
from .network import OSM_PATH as DEFAULT_OSM_PATH
from .network import load_network
from .persistence import load_saved_network, save_network
from .render import Renderer
from .slider import SpeedSlider

WINDOW_MAX_DIM = 1000
FPS = 30
# Real time (1x) by default. At the old fixed 15x, a 20s green phase flashed
# by in ~1.3 real seconds and every acceleration/deceleration compressed
# into a fraction of a second, looking sped-up rather than gradual - this
# makes what's on screen match a real stopwatch by default, while the speed
# slider (0.5x-5x, top-right) lets you speed things up or slow them down.
TIME_SCALE = 1.0
ZOOM_STEP = 1.15
AUTOSAVE_INTERVAL_S = 1.0


def run(osm_path: str = DEFAULT_OSM_PATH, basemap_cache_path: str = DEFAULT_BASEMAP_CACHE_PATH,
        caption: str = "TrafficTwin", extra_signal_coords: tuple[tuple[float, float], ...] = (),
        signal_light_coords: tuple[tuple[float, float], ...] = (), save_path: str | None = None):
    print("Loading road network...")
    if save_path and os.path.exists(save_path):
        print(f"Found saved edited network at {save_path}, loading that instead of OSM...")
        net = load_saved_network(save_path)
    else:
        net = load_network(osm_path=osm_path, extra_signal_coords=extra_signal_coords,
                           signal_light_coords=signal_light_coords)
    print(f"Signalized junctions: {len(net.junction_nodes)}")

    print("Loading satellite basemap (cached after first run)...")
    basemap_image, origin_xtile, origin_ytile = load_basemap(net.bounds, cache_path=basemap_cache_path)

    raw_w, raw_h = basemap_image.size
    fit_zoom = WINDOW_MAX_DIM / max(raw_w, raw_h)
    window_size = (int(raw_w * fit_zoom), int(raw_h * fit_zoom))

    pygame.init()
    pygame.display.set_caption(caption)
    screen = pygame.display.set_mode(window_size)

    center_lat = (net.bounds[1] + net.bounds[3]) / 2
    pixel_mapper = PixelMapper(BASEMAP_ZOOM, origin_xtile, origin_ytile, center_lat)
    basemap_surface = pygame.image.frombytes(basemap_image.tobytes(), (raw_w, raw_h), "RGB").convert()

    camera = Camera(zoom=fit_zoom)

    def rebuild_sim():
        return (SimulationEngine(net),
                Renderer(screen, basemap_surface, net, pixel_mapper, camera))

    engine, renderer = rebuild_sim()
    editor = RoadEditor(net, pixel_mapper, camera)
    slider = SpeedSlider(window_size[0])
    slider.value = TIME_SCALE

    clock = pygame.time.Clock()
    edit_mode = False
    dragging_pan = False
    mouse_down_pos = None
    edited = False
    autosave_timer = 0.0
    running = True

    def maybe_save():
        nonlocal edited
        if edited and save_path:
            save_network(net, save_path)
            print(f"Autosaved to {save_path}")
            edited = False

    print("Running. Drag to pan, scroll to zoom, R to reset view, E to edit roads, ESC/close to quit.")
    while running:
        real_dt_ms = clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    camera.zoom = fit_zoom
                    camera.offset_x = 0.0
                    camera.offset_y = 0.0
                elif event.key == pygame.K_e:
                    if edit_mode:
                        maybe_save()
                    edit_mode = not edit_mode
                    editor.clear_selection()
                    print("Entered edit mode - paused." if edit_mode else "Resumed simulation.")
                elif edit_mode and pygame.K_1 <= event.key <= pygame.K_9:
                    editor.set_selected_lanes(event.key - pygame.K_0)
                    edited = True
                elif edit_mode and event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                    force = bool(event.mod & pygame.KMOD_SHIFT)
                    if editor.delete_selected(force=force):
                        engine, renderer = rebuild_sim()
                        edited = True
                elif edit_mode and event.key == pygame.K_s:
                    edited = True
                    if save_path:
                        maybe_save()
                    else:
                        print("No save path configured for this place - edits won't persist.")
                elif edit_mode and event.key == pygame.K_t:
                    if editor.toggle_selected_junction():
                        engine, renderer = rebuild_sim()
                        edited = True
                elif edit_mode and event.key == pygame.K_a:
                    if editor.toggle_selected_approach():
                        engine, renderer = rebuild_sim()
                        edited = True
                elif edit_mode and event.key == pygame.K_m:
                    editor.toggle_move_network_mode()
                    print("Move-network mode: drag anywhere to shift all roads together."
                          if editor.move_network_mode else "Move-network mode off.")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_down_pos = event.pos
                if slider.on_mouse_down(event.pos):
                    dragging_pan = False
                elif edit_mode and editor.move_network_mode:
                    editor.begin_move_network(event.pos)
                    dragging_pan = False
                elif edit_mode:
                    dragging_pan = not editor.on_mouse_down(event.pos)
                else:
                    dragging_pan = True
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if slider.dragging:
                    slider.on_mouse_up()
                elif edit_mode and editor.move_network_mode:
                    editor.end_move_network()
                elif edit_mode:
                    moved = mouse_down_pos is not None and math.hypot(
                        event.pos[0] - mouse_down_pos[0], event.pos[1] - mouse_down_pos[1]) > CLICK_MOVE_THRESHOLD_PX
                    if editor.on_mouse_up(event.pos, moved):
                        engine, renderer = rebuild_sim()
                        edited = True
                dragging_pan = False
                mouse_down_pos = None
            elif event.type == pygame.MOUSEMOTION:
                if slider.dragging:
                    slider.on_mouse_motion(event.pos)
                elif edit_mode and editor.move_network_mode and pygame.mouse.get_pressed()[0]:
                    if editor.drag_move_network(event.pos):
                        engine, renderer = rebuild_sim()
                        edited = True
                elif edit_mode:
                    editor.on_mouse_motion(event.pos)
                if dragging_pan:
                    camera.pan(*event.rel)
            elif event.type == pygame.MOUSEWHEEL:
                factor = ZOOM_STEP if event.y > 0 else (1 / ZOOM_STEP)
                camera.zoom_at(*pygame.mouse.get_pos(), factor)

        if not edit_mode:
            sim_dt = min(real_dt_ms / 1000.0, 0.1) * slider.value
            engine.step(sim_dt)

        autosave_timer += real_dt_ms / 1000.0
        if autosave_timer >= AUTOSAVE_INTERVAL_S:
            autosave_timer = 0.0
            maybe_save()

        renderer.draw(engine, clock.get_fps(), editor=editor if edit_mode else None, slider=slider)
        pygame.display.flip()

    maybe_save()
    pygame.quit()
    sys.exit(0)
