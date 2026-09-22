"""
Phase 5 (visual) - plots system-level metrics over the simulated hour for
both policies, so the simulation's behavior can be seen without sumo-gui.
"""
import matplotlib.pyplot as plt
import pandas as pd

BASELINE_CSV = "results/baseline_conn0_ep1.csv"
LEARNED_CSV = "results/learned_conn0_ep1.csv"
OUT_PNG = "analysis/timeseries.png"

METRICS = [
    ("system_total_stopped", "Queue length (vehicles)"),
    ("system_mean_waiting_time", "Mean waiting time (s)"),
    ("system_mean_speed", "Mean speed (m/s)"),
]

if __name__ == "__main__":
    baseline = pd.read_csv(BASELINE_CSV)
    learned = pd.read_csv(LEARNED_CSV)

    fig, axes = plt.subplots(len(METRICS), 1, figsize=(10, 9), sharex=True)
    for ax, (col, label) in zip(axes, METRICS):
        ax.plot(baseline["step"] / 60, baseline[col], label="Fixed-timer baseline", color="#d62728", linewidth=1)
        ax.plot(learned["step"] / 60, learned[col], label="Learned (Q-learning)", color="#2ca02c", linewidth=1)
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)

    axes[0].set_title("Astra Biz Center junction — simulated 1-hour run, baseline vs. learned policy")
    axes[0].legend(loc="upper left")
    axes[-1].set_xlabel("Simulated time (minutes)")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    print(f"Saved {OUT_PNG}")
