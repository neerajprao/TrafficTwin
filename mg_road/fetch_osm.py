"""
Dummy check - geocodes MG Road, Bangalore and downloads the drivable OSM
road network around it, same approach as scripts/fetch_osm.py but for a
different place, to sanity-check that twin/ works anywhere, not just at
Astra Biz Center.
"""
import osmnx as ox

PLACE_QUERY = "MG Road, Bengaluru, Karnataka, India"
RADIUS_M = 500
OUT_PATH = "mg_road/data/mg_road.osm.xml"

ox.settings.all_oneway = True

if __name__ == "__main__":
    point = ox.geocode(PLACE_QUERY)
    print(f"Geocoded '{PLACE_QUERY}' -> {point}")
    graph = ox.graph_from_point(point, dist=RADIUS_M, network_type="drive", simplify=False)
    ox.save_graph_xml(graph, filepath=OUT_PATH)
    print(f"Saved OSM network to {OUT_PATH}")
