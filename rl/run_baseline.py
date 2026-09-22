"""
Phase 3 - Baseline Signal Policy.

Runs the junction's fixed-timer signal program (the static tlLogic that
netconvert derived from OSM: two ~33s main-street greens with short
protected-turn phases, 90s cycle) for one full hour and logs system-level
metrics for comparison against the learned policy.
"""
from sumo_rl import SumoEnvironment

NET = "sumo/astra_biz_center/astra_biz_center.net.xml"
ROUTE = "sumo/astra_biz_center/astra_biz_center.rou.xml"
SIM_SECONDS = 3600
OUT_CSV = "results/baseline"

if __name__ == "__main__":
    env = SumoEnvironment(
        net_file=NET,
        route_file=ROUTE,
        out_csv_name=OUT_CSV,
        use_gui=False,
        num_seconds=SIM_SECONDS,
        delta_time=5,
        single_agent=True,
        fixed_ts=True,
        sumo_seed=42,
        sumo_warnings=False,
    )

    env.reset()
    done = False
    while not done:
        _, _, terminated, truncated, _ = env.step(None)
        done = terminated or truncated
    env.save_csv(OUT_CSV, 1)
    env.close()
    print(f"Baseline run complete. Metrics saved to {OUT_CSV}_conn0_ep1.csv")
