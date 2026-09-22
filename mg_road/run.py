"""
Dummy check - runs the exact same twin/ digital twin engine, pointed at
MG Road, Bangalore instead of Astra Biz Center, to sanity-check the engine
works at an arbitrary place. Not calibrated to real MG Road traffic (still
uses the Astra Biz Center vehicle mix) - this is just a visual smoke test.

Run with:  .venv/bin/python -m mg_road.run

Drag to pan, scroll to zoom, R to reset the view, E to edit roads.
"""
from twin.app import run

OSM_PATH = "mg_road/data/mg_road.osm.xml"
BASEMAP_CACHE_PATH = "mg_road/data/mg_road_basemap.png"
SAVE_PATH = "mg_road/data/mg_road_edited.json"

# Real signalized junctions OSM's own `highway=traffic_signals` tags found
# automatically don't need to go here. Add a (lat, lon) pair per *additional*
# real-life signal OSM missed - open the place in Google Maps, right-click
# the junction, click the coordinates at the top of the context menu to copy
# them, and paste as (lat, lon) below.
EXTRA_SIGNAL_COORDS = (
    # (12.9750, 77.6070),
)

if __name__ == "__main__":
    run(osm_path=OSM_PATH, basemap_cache_path=BASEMAP_CACHE_PATH,
        caption="TrafficTwin - MG Road, Bangalore (dummy)", extra_signal_coords=EXTRA_SIGNAL_COORDS,
        save_path=SAVE_PATH)
