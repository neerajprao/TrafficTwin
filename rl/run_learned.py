"""
Phase 4 (evaluation) - runs the trained Q-learning policy greedily (no
exploration) for one full hour and logs system-level metrics in the same
format as run_baseline.py, for a like-for-like comparison.
"""
import pickle

from sumo_rl import SumoEnvironment

from discretized_obs import DiscretizedObservationFunction

NET = "sumo/astra_biz_center/astra_biz_center.net.xml"
ROUTE = "sumo/astra_biz_center/astra_biz_center.rou.xml"
Q_TABLE_IN = "rl/q_table.pkl"
SIM_SECONDS = 3600
OUT_CSV = "results/learned"

if __name__ == "__main__":
    with open(Q_TABLE_IN, "rb") as f:
        q_table = pickle.load(f)
    print(f"Loaded Q-table with {len(q_table)} states.")

    env = SumoEnvironment(
        net_file=NET,
        route_file=ROUTE,
        out_csv_name=OUT_CSV,
        use_gui=False,
        num_seconds=SIM_SECONDS,
        delta_time=5,
        yellow_time=3,
        min_green=8,
        max_green=45,
        single_agent=True,
        reward_fn="diff-waiting-time",
        observation_class=DiscretizedObservationFunction,
        sumo_seed=42,
        sumo_warnings=False,
    )

    state, _ = env.reset()
    state = tuple(state)
    done = False
    unseen_states = 0
    while not done:
        if state in q_table:
            action = int(max(range(len(q_table[state])), key=lambda a: q_table[state][a]))
        else:
            unseen_states += 1
            action = 0
        next_state, _, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
        state = tuple(next_state)
    env.save_csv(OUT_CSV, 1)
    env.close()

    if unseen_states:
        print(f"Note: hit {unseen_states} states not seen during training (fell back to action 0).")
    print(f"Learned-policy run complete. Metrics saved to {OUT_CSV}_conn0_ep1.csv")
