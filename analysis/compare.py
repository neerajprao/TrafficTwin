"""
Phase 5 - Compare & Explain.

Loads the baseline (fixed-timer) and learned (Q-learning) simulation metrics,
computes mean queue length / mean waiting time / improvement, and asks a
local Ollama model to explain the results in plain language.
"""
import json

import pandas as pd
import requests

BASELINE_CSV = "results/baseline_conn0_ep1.csv"
LEARNED_CSV = "results/learned_conn0_ep1.csv"
REPORT_OUT = "analysis/report.md"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b-instruct"


def summarize(csv_path: str) -> dict:
    df = pd.read_csv(csv_path)
    return {
        "mean_queue_length": df["system_total_stopped"].mean(),
        "mean_waiting_time": df["system_mean_waiting_time"].mean(),
        "mean_speed": df["system_mean_speed"].mean(),
        "peak_queue_length": df["system_total_stopped"].max(),
    }


def pct_improvement(baseline: float, learned: float) -> float:
    """Positive = learned is better (lower) than baseline. Negative = learned is worse."""
    if baseline == 0:
        return 0.0
    return 100.0 * (baseline - learned) / baseline


def _fact_sentence(metric: str, unit: str, baseline_val: float, learned_val: float, pct: float) -> str:
    """A fully pre-attributed, unambiguous fact sentence - naming which strategy is
    better directly next to its number, so the LLM has no attribution left to get wrong."""
    if abs(pct) < 1.0:
        return f"{metric}: essentially the same under both strategies ({baseline_val:.1f}{unit})."
    better, better_val, worse, worse_val = (
        ("the learned policy", learned_val, "the fixed-timer baseline", baseline_val)
        if pct > 0
        else ("the fixed-timer baseline", baseline_val, "the learned policy", learned_val)
    )
    return (
        f"{metric}: {better} is BETTER at {better_val:.1f}{unit}, "
        f"vs {worse} at {worse_val:.1f}{unit} ({abs(pct):.1f}% difference)."
    )


def build_prompt(baseline: dict, learned: dict, improvements: dict) -> str:
    queue_fact = _fact_sentence("Mean queue length", " vehicles", baseline["mean_queue_length"], learned["mean_queue_length"], improvements["queue"])
    waiting_fact = _fact_sentence("Mean waiting time", "s/vehicle", baseline["mean_waiting_time"], learned["mean_waiting_time"], improvements["waiting"])
    speed_fact = _fact_sentence("Mean speed", " m/s", baseline["mean_speed"], learned["mean_speed"], improvements["speed"])

    learned_wins = sum(1 for pct in improvements.values() if pct > 1.0)
    baseline_wins = sum(1 for pct in improvements.values() if pct < -1.0)
    if baseline_wins == 0:
        outcome_note = (
            "Note this is a CLEAN SWEEP for the learned policy: it is better (or "
            "essentially tied) on every metric above, not just some of them. Describe "
            "it as an unambiguous win on these metrics, while still noting the caveats "
            "below (oversaturated demand, small state space, short training)."
        )
    else:
        outcome_note = (
            "Note this is a genuinely MIXED result: the learned policy is NOT strictly "
            "better on every metric (re-read the three FACTS above carefully - at least "
            "one of them names the fixed-timer baseline as better, not the learned "
            "policy). Do not describe the learned policy as an unambiguous win."
        )

    return f"""You are explaining a traffic simulation experiment to a city planner who is not
a data scientist. Two signal-timing strategies were tested on a digital twin of a real
4-way signalized junction (Astra Biz Center, BSD City, Tangerang, Indonesia), built in
SUMO from real road geometry and a motorcycle-heavy Indonesian traffic mix, over a
simulated 1-hour period each.

Strategy A - Fixed-timer baseline: the junction's existing traffic light program, which
switches on a fixed schedule regardless of how much traffic is present.

Strategy B - Learned policy: a Q-learning reinforcement-learning agent that watches the
queue length at the junction every 5 seconds and decides whether to keep or switch the
green light, trained over 40 simulated hours.

FACTS (these three sentences are already correct and already say which strategy is
better for each metric - do not recompute, re-derive, or swap which strategy is named as
better in any of them; just restate them in your own plain-language phrasing):
- {queue_fact}
- {waiting_fact}
- {speed_fact}

{outcome_note}

Also note: both policies show very high absolute queue lengths and waiting times (peak
queue near {baseline['peak_queue_length']:.0f} vehicles, waits over 9 minutes). This
indicates the synthetic demand used (motorcycle-heavy, ~4300 vehicles/hour) likely exceeds
this small single-junction network's real capacity, i.e. the scenario is oversaturated /
gridlocked for both strategies, not just realistically busy.

Write a short (3-4 paragraph) plain-language explanation for the city planner covering:
1. What was tested and how.
2. What the numbers mean in practical terms, using the pre-computed directions above
   exactly as given (do not flip or reinterpret them).
3. Whether the learned policy is worth pursuing given the result above, and caveats
   (synthetic/oversaturated demand, small state space, short training, not a live
   deployment).
Do not use markdown headers or bullet lists - write it as flowing prose paragraphs."""


if __name__ == "__main__":
    baseline = summarize(BASELINE_CSV)
    learned = summarize(LEARNED_CSV)

    improvements = {
        "queue": pct_improvement(baseline["mean_queue_length"], learned["mean_queue_length"]),
        "waiting": pct_improvement(baseline["mean_waiting_time"], learned["mean_waiting_time"]),
        "speed": pct_improvement(baseline["mean_speed"], learned["mean_speed"]) * -1,  # higher speed is better
    }

    print("=== Baseline (fixed-timer) ===")
    for k, v in baseline.items():
        print(f"  {k}: {v:.2f}")
    print("=== Learned (Q-learning) ===")
    for k, v in learned.items():
        print(f"  {k}: {v:.2f}")
    print("=== Improvement (learned vs. baseline) ===")
    for k, v in improvements.items():
        print(f"  {k}: {v:.1f}%")

    prompt = build_prompt(baseline, learned, improvements)

    print(f"\nAsking local Ollama model '{OLLAMA_MODEL}' for a plain-language explanation...")
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    explanation = resp.json()["response"].strip()

    report = f"""# TrafficTwin Results — Astra Biz Center Junction

## Metrics

| Metric | Fixed-timer baseline | Learned (Q-learning) | Improvement |
|---|---|---|---|
| Mean queue length (vehicles) | {baseline['mean_queue_length']:.1f} | {learned['mean_queue_length']:.1f} | {improvements['queue']:.1f}% |
| Mean waiting time (s/vehicle) | {baseline['mean_waiting_time']:.1f} | {learned['mean_waiting_time']:.1f} | {improvements['waiting']:.1f}% |
| Mean speed (m/s) | {baseline['mean_speed']:.2f} | {learned['mean_speed']:.2f} | {improvements['speed']:.1f}% |
| Peak queue length (vehicles) | {baseline['peak_queue_length']:.0f} | {learned['peak_queue_length']:.0f} | - |

## Explanation (generated locally by {OLLAMA_MODEL} via Ollama)

{explanation}
"""
    with open(REPORT_OUT, "w") as f:
        f.write(report)
    print(f"\nReport written to {REPORT_OUT}")
