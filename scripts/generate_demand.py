"""
Phase 2 - generates synthetic traffic demand for the Astra Biz Center
junction so the digital twin is drivable end-to-end. Mode split is
calibrated against the geo-trax model's per-class vehicle counts from the
source video (see detection/count_vehicles.py).
"""
import subprocess
import sys

NET = "sumo/astra_biz_center/astra_biz_center.net.xml"
VTYPES = "sumo/astra_biz_center/astra_biz_center.vtypes.xml"
OUT_DIR = "sumo/astra_biz_center"
SIM_END = 3600  # seconds (1 hour)

RANDOM_TRIPS = ".venv/lib/python3.14/site-packages/sumo/tools/randomTrips.py"

# vehicles/hour per type. Ratio calibrated from the geo-trax model's unique
# tracker-ID counts over the full 82.28s source video (Car 802, Motorcycle
# 1347, Truck 288, Bus 143 - see detection/count_vehicles.py and
# PROGRESS.md). Absolute counts aren't used directly for veh/h since
# track-ID fragmentation inflates them - only the *proportions between
# classes* are trusted. geo-trax has no separate "van" class (it folds vans
# into "Car"), so the detected car share is split 80/20 between car/van,
# matching the previous car:van ratio. Total demand held at ~4330 veh/h
# (same level previously sanity-checked to produce plausible congestion).
MODE_SPLIT = {
    "motorcycle": 2260,
    "car": 1080,
    "van": 270,
    "truck": 480,
    "bus": 240,
}

VCLASS_MAP = {
    "motorcycle": "motorcycle",
    "car": "passenger",
    "van": "delivery",
    "truck": "truck",
    "bus": "bus",
}


def run_random_trips(veh_type: str, veh_per_hour: int) -> str:
    period = 3600.0 / veh_per_hour
    out_trips = f"{OUT_DIR}/astra_biz_center.{veh_type}.trips.xml"
    cmd = [
        sys.executable, RANDOM_TRIPS,
        "-n", NET,
        "-o", out_trips,
        "--begin", "0",
        "--end", str(SIM_END),
        "--period", str(period),
        "--fringe-factor", "100",
        "--vclass", VCLASS_MAP[veh_type],
        "--trip-attributes", f'type="{veh_type}"',
        "--prefix", f"{veh_type}_",
        "--seed", "42",
    ]
    subprocess.run(cmd, check=True)
    return out_trips


if __name__ == "__main__":
    trip_files = []
    for veh_type, vph in MODE_SPLIT.items():
        print(f"Generating {vph} veh/h of {veh_type}...")
        trip_files.append(run_random_trips(veh_type, vph))

    merged = f"{OUT_DIR}/astra_biz_center.trips.xml"
    print(f"Merging trip files into {merged}...")
    with open(merged, "w") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<routes>\n')
        all_trips = []
        for tf in trip_files:
            with open(tf) as f:
                content = f.read()
            import re
            all_trips.extend(re.findall(r"<trip .*?/>", content, re.DOTALL))
        # sort by depart time
        def depart_time(trip_str):
            m = re.search(r'depart="([\d.]+)"', trip_str)
            return float(m.group(1)) if m else 0.0
        all_trips.sort(key=depart_time)
        for t in all_trips:
            out.write(f"    {t}\n")
        out.write("</routes>\n")

    routed = f"{OUT_DIR}/astra_biz_center.rou.xml"
    print(f"Routing trips through the network with duarouter -> {routed}...")
    subprocess.run([
        "duarouter",
        "-n", NET,
        "-r", merged,
        "-a", VTYPES,
        "-o", routed,
        "--ignore-errors",
        "--seed", "42",
    ], check=True)

    print("Done.")
