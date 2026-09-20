"""Generate synthetic traffic demand for the Silk Board Junction digital twin.

Silk Board is one of Bangalore's most congested junctions, so demand is set heavy
and motorcycle-dominant to reflect the real vehicle mix. This is a placeholder
until a recorded video + manual counts are available to calibrate real demand
(see PLAN.md Phase 2).

Workflow: randomTrips.py picks random origin/destination pairs biased toward the
network's fringe (boundary) edges -- i.e. the real arms of the junction -- for
each vehicle class separately (so we control the mode split), then duarouter
merges everything and computes real routes through the network.
"""
import os
import subprocess
import sys

import sumo as _sumo

SUMO_HOME = _sumo.SUMO_HOME
RANDOM_TRIPS = os.path.join(SUMO_HOME, "tools", "randomTrips.py")

NET_FILE = "sumo/silk_board/silk_board.net.xml"
OUT_DIR = "sumo/silk_board"
SIM_DURATION_S = 3600  # 1 hour simulation
SEED = 42

# Mode split modeled on typical Bangalore arterial junction traffic
# (motorcycle-dominant, sizeable autos, cars, some buses/trucks).
# vclass = SUMO permission class used to pick valid fringe edges for that mode.
# vtype  = the custom vType id from silk_board.vtypes.xml assigned to each trip.
# veh_per_hour = target demand for that mode over the full simulation.
MODES = [
    {"name": "motorcycle", "vclass": "motorcycle", "vtype": "motorcycle", "veh_per_hour": 2000},
    {"name": "car", "vclass": "passenger", "vtype": "car", "veh_per_hour": 1200},
    {"name": "auto", "vclass": "taxi", "vtype": "auto_rickshaw", "veh_per_hour": 480},
    {"name": "truck", "vclass": "truck", "vtype": "truck", "veh_per_hour": 200},
    {"name": "bus", "vclass": "bus", "vtype": "bus", "veh_per_hour": 120},
]

# Bias trip endpoints strongly toward the network's boundary edges (the real
# roads entering/leaving the modeled area) rather than picking short hops
# between interior junctions.
FRINGE_FACTOR = 100


def main():
    trip_files = []
    for mode in MODES:
        period = SIM_DURATION_S / mode["veh_per_hour"]
        trip_file = f"{OUT_DIR}/silk_board.{mode['name']}.trips.xml"
        cmd = [
            sys.executable, RANDOM_TRIPS,
            "-n", NET_FILE,
            "-o", trip_file,
            "-b", "0", "-e", str(SIM_DURATION_S),
            "-p", str(period),
            "--fringe-factor", str(FRINGE_FACTOR),
            "--vclass", mode["vclass"],
            "--trip-attributes", f'type="{mode["vtype"]}"',
            "--prefix", mode["name"],
            "--seed", str(SEED),
            "--validate",
        ]
        print(f"Generating {mode['name']} trips (~{mode['veh_per_hour']} veh/h, period={period:.2f}s)...")
        subprocess.run(cmd, check=True)
        trip_files.append(trip_file)

    # Merge all per-mode trip files into one, sorted by departure time.
    merged_trips = f"{OUT_DIR}/silk_board.trips.xml"
    merge_trip_files(trip_files, merged_trips)

    # Route the merged trips through the real network -> final .rou.xml
    routed_file = f"{OUT_DIR}/silk_board.rou.xml"
    duarouter = os.path.join(SUMO_HOME, "bin", "duarouter") if os.path.exists(
        os.path.join(SUMO_HOME, "bin", "duarouter")
    ) else "duarouter"
    cmd = [
        duarouter,
        "-n", NET_FILE,
        "-r", merged_trips,
        "-a", f"{OUT_DIR}/silk_board.vtypes.xml",
        "-o", routed_file,
        "--ignore-errors",
        "--seed", str(SEED),
    ]
    print("Routing merged trips with duarouter...")
    subprocess.run(cmd, check=True)
    print(f"Done. Routed demand written to {routed_file}")


def merge_trip_files(trip_files, out_path):
    import xml.etree.ElementTree as ET

    all_trips = []
    for f in trip_files:
        tree = ET.parse(f)
        for trip in tree.getroot().findall("trip"):
            all_trips.append(trip)
    all_trips.sort(key=lambda t: float(t.get("depart")))

    root = ET.Element("routes")
    for trip in all_trips:
        root.append(trip)
    ET.ElementTree(root).write(out_path, encoding="UTF-8", xml_declaration=True)
    print(f"Merged {len(all_trips)} trips -> {out_path}")


if __name__ == "__main__":
    main()
