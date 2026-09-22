# TrafficTwin: Traffic Signal Simulator

A traffic signal simulator for students and city planners who want to compare signal timing strategies without experimenting on a real road.

## Problem & Audience

Students and city planners want to see how different signal timing strategies affect traffic — for example, a simple fixed-timer light versus a "smart" light that adapts to traffic. You can't test this on real streets, so TrafficTwin recreates a junction as a digital twin using a recorded video, and lets you try different strategies on it safely.

## How It Works

```
Recorded traffic video
      │
      ▼
YOLO detects & counts vehicles (checked against manual counts → count MAE)
      │
      ▼
Digital twin of the junction in SUMO
(real road layout from OpenStreetMap, realistic driver behavior,
 calibrated so queues/flows roughly match the video)
      │
      ▼
Try a signal strategy
   ├── Fixed-timer (baseline) — lights change on a set timer
   └── Reinforcement learning (Q-learning / DQN via SUMO-RL + TraCI)
       — watches queue lengths and learns when to switch the light
      │
      ▼
Measure results (mean queue length, mean waiting time, improvement over baseline)
      │
      ▼
AI (local LLM via Ollama) explains the results in plain language
```

## Scope (v1)

**Included:**
- One junction, modeled as a digital twin in SUMO
- One recorded video clip (not a live camera) as the source of vehicle counts
- Road layout imported from OpenStreetMap
- A simple fixed-timer light as the baseline to compare against

**Not included (for now):**
- Multiple connected junctions
- Live video feeds
- Connecting to real traffic light hardware

## Build Phases

### Phase 1 — Count the Traffic
Run a pretrained YOLO model locally on the recorded video to detect and count vehicles per lane over time. Check these counts against manual counts to measure accuracy (count MAE).

### Phase 2 — Build the Digital Twin
Import the real road layout for the junction from OpenStreetMap into SUMO (a free, open-source traffic simulator with realistic driver behavior). Calibrate the simulation so its queues and traffic flow roughly match what was seen in the video.

### Phase 3 — Baseline Signal Policy
Implement the fixed-timer baseline policy, where lights change on a set schedule regardless of traffic conditions.

### Phase 4 — Learned Signal Policy
Build a reinforcement learning controller (Q-learning or DQN) using SUMO-RL and TraCI. It observes queue lengths at the junction and learns through trial and error when to keep or switch a green light.

### Phase 5 — Compare & Explain
Run both policies on the twin and compare them using mean queue length, mean waiting time, and overall improvement of the learned policy over the baseline. Use a local LLM (via Ollama, no API key needed) to turn these numbers into a plain-language explanation of what happened and why.

### Phase 6 — Wrap Up
Finalize the results, double-check everything matches the original scope, and write up the findings.

## Tech Stack

| Part | What we'll use |
|---|---|
| Vehicle detection & counting | [geo-trax](https://huggingface.co/rfonod/geo-trax) — YOLOv8s pretrained on aerial/drone footage, run locally |
| Road layout | OpenStreetMap import |
| Junction simulation | SUMO (free, open-source traffic simulator) |
| Learned signal policy | Q-learning / DQN via SUMO-RL + TraCI |
| Explaining results | Local LLM via [Ollama](https://ollama.com) (`qwen2.5:7b-instruct`) — no API key needed |

Everything runs on free tools and a normal laptop — no paid software or special hardware required.

## Success Metrics

- **Count MAE** — how close YOLO's vehicle counts are to manual counts
- **Mean queue length** — how long the line of cars gets, per strategy
- **Mean waiting time** — how long cars wait, per strategy
- **Improvement** — how much better the learned policy does compared to the fixed-timer baseline

## Requirements (Needed From You)

- **A recorded traffic video clip** of one junction, ideally with a clear top-down or angled view of all lanes and decent lighting.
- **Manual vehicle counts** for a portion of the clip, so we can check YOLO's accuracy (count MAE).
- **Confirmation of the junction's location or layout** (e.g. an address or map link) so the road layout can be imported from OpenStreetMap.
- **Ollama installed locally** (free, no API key) for the AI-generated result explanations — `qwen2.5:7b-instruct` is the model currently used.
- **A laptop that can run Python, SUMO, and the vehicle detection model** (no special hardware needed, but a bit of free disk space and RAM helps).
- **Decisions on open questions when they come up** — e.g. approving the calibration of the simulation, or picking which junction/clip to focus on if there are multiple options.

## Risks & Open Questions

- The video's camera angle or lighting might make YOLO's counting less accurate.
- OpenStreetMap data for the junction may need manual cleanup to match reality.
- Calibrating SUMO so its traffic matches the video may take some trial and error.
- The learned policy (Q-learning/DQN) may need simplified rules to train in reasonable time.
- The local LLM (Ollama) must be running (`ollama serve`) before Phase 5 can generate its explanation — easy to forget since it's not always running by default.
