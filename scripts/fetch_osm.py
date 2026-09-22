"""
Geocodes the target junction and downloads the drivable OSM road network
around it, saving raw OSM XML for netconvert to build a SUMO network from.
"""
import osmnx as ox

PLACE_QUERY = "Astra Biz Center, BSD City, Tangerang, Banten, Indonesia"
RADIUS_M = 500
OUT_PATH = "data/osm/astra_biz_center.osm.xml"

# Must be set before fetching so one-way streets (ramps, divided arterials)
# export correctly to OSM XML instead of collapsing into duplicate edges.
ox.settings.all_oneway = True

if __name__ == "__main__":
    point = ox.geocode(PLACE_QUERY)
    print(f"Geocoded '{PLACE_QUERY}' -> {point}")

    graph = ox.graph_from_point(
        point, dist=RADIUS_M, network_type="drive", simplify=False
    )
    print(f"Fetched graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    ox.save_graph_xml(graph, filepath=OUT_PATH)
    print(f"Saved OSM XML to {OUT_PATH}")
