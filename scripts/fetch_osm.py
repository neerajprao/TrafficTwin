"""Fetch the road network around Silk Board Junction, Bangalore from OpenStreetMap
and save it as raw OSM XML for SUMO's netconvert to import.
"""
import osmnx as ox

CENTER = (12.9158171, 77.6240368)  # Silk Board Junction, Bangalore
RADIUS_M = 1000  # covers the junction and approach roads on all arms, far enough to separate each arm's carriageways into distinct boundary points
OUT_PATH = "data/osm/silk_board.osm.xml"

if __name__ == "__main__":
    ox.settings.useful_tags_way += ["lanes", "maxspeed", "junction"]
    ox.settings.all_oneway = True  # required for correct OSM XML export (preserves one-way flyover ramps)
    G = ox.graph_from_point(CENTER, dist=RADIUS_M, network_type="drive", simplify=False)
    print(f"Fetched graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
    ox.io.save_graph_xml(G, filepath=OUT_PATH)
    print(f"Saved OSM XML to {OUT_PATH}")
