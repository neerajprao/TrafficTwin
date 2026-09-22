"""
Phase 2 (rebuilt) - entry point for the custom digital twin. Run with:

    .venv/bin/python -m twin.run

Opens a live pygame window on data/edited/astra_biz_center.json - a
hand-built junction (roads, directions, and signal placement all drawn and
configured in-app, not fetched from OSM). Drag to pan, scroll to zoom, R to
reset the view, E to edit roads (see twin/render.py's edit-mode HUD text for
the full key list: drawing roads, setting lanes, and T/A for signals). No
SUMO/XQuartz involved - this is a plain SDL2 window, native on Apple Silicon.
"""
from .app import run

SAVE_PATH = "data/edited/astra_biz_center.json"

if __name__ == "__main__":
    run(caption="TrafficTwin - Astra Biz Center", save_path=SAVE_PATH)
