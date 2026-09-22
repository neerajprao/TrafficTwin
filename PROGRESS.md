# TrafficTwin — Progress Log

Running record of everything set up so far: tools installed, files created, and what each one is for. Updated as work progresses. See [PLAN.md](PLAN.md) for the overall project plan and phases.

---

## Current status (as of 2026-09-21)

**Active junction: Astra Biz Center, BSD City, Tangerang, Banten, Indonesia.**

| Phase | Status |
|---|---|
| 1 — Count the Traffic | Done. Swapped the pretrained COCO YOLOv8m for [geo-trax](https://huggingface.co/rfonod/geo-trax) (YOLOv8s trained on aerial/drone footage) — it detects motorcycles natively, no manual counting workaround needed anymore. See below. |
| 2 — Build the Digital Twin | **Rebuilt (2026-09-21).** Replaced the SUMO/`sumo-gui` pipeline with a custom-built simulator in `twin/` — see below. Old SUMO-based network/demand files in `sumo/` and `scripts/` are left in place but unused. |
| 3 — Baseline Signal Policy | Superseded — was built on the old SUMO pipeline (`rl/run_baseline.py`), not yet rebuilt against `twin/`. |
| 4 — Learned Signal Policy | Superseded — was built on the old SUMO pipeline (`rl/train_ql.py`/`rl/run_learned.py`), not yet rebuilt against `twin/`. |
| 5 — Compare & Explain | Superseded — `analysis/report.md`'s numbers are from the old SUMO pipeline, not the new twin. |
| 6 — Wrap Up | Not started for the rebuilt twin. |

### Current repo layout (Astra Biz Center)

| Path | Role |
|---|---|
| `data/video/astra_biz_center.mp4` | User-provided 4K drone video of the junction (gitignored, not committed). |
| `data/osm/astra_biz_center.osm.xml` | Raw OSM road network around the junction (gitignored, regenerable). |
| `data/basemap/astra_biz_center.png` | Cached stitched satellite image for the twin's background (gitignored, regenerable). |
| `scripts/fetch_osm.py` | Geocodes the junction and fetches its OSM road network — still used, feeds both the old SUMO path and the new `twin/`. |
| `twin/network.py` | Loads the OSM graph directly (no `netconvert`), consolidates the junction node, exposes routable edges. |
| `twin/basemap.py` | Fetches/stitches/caches real satellite tiles and maps lon/lat to screen pixels. |
| `twin/vehicle.py` | Vehicle types (ported from `astra_biz_center.vtypes.xml`) and IDM car-following physics. |
| `twin/spawner.py` | Poisson-process vehicle spawner using the same calibrated `MODE_SPLIT` as `scripts/generate_demand.py`. |
| `twin/signals.py` | Fixed-timer 2-phase traffic signal at the junction. |
| `twin/engine.py` | Per-tick simulation loop: physics, spawning, signal updates, despawning. |
| `twin/render.py` | pygame renderer — satellite backdrop, roads, signal state, vehicles, HUD. |
| `twin/run.py` | Entry point — `python -m twin.run` opens the live simulation window. |
| `scripts/generate_demand.py` | Legacy — generates/routes SUMO demand for the old pipeline (`rl/`, `analysis/`). |
| `sumo/astra_biz_center/*` | Legacy SUMO network/demand/config — still needed by `rl/`/`analysis/` until those are rebuilt. |
| `detection/count_vehicles.py` | Phase 1 — geo-trax (YOLOv8s, aerial-trained) + ByteTrack vehicle counting. |
| `rl/*`, `results/*.csv`, `analysis/*` | Legacy Phase 3-5 pipeline, built on the old SUMO twin — numbers here predate the Phase 2 rebuild. |

---

## Log

### 2026-09-20 — Environment setup

- **Created Python virtual environment** at `.venv/` (Python 3.14.3, via `python3 -m venv .venv`).
  All project Python work happens inside this venv — activate with `source .venv/bin/activate`.

- **Installed SUMO (traffic simulator) via PyPI**, not Homebrew.
  - First tried `brew install sumo` — failed (formula not in Homebrew core).
  - Then tried the `dlr-ts/sumo` Homebrew tap — failed (`undefined method 'cxxstdlib_check'`, formula incompatible with the installed Homebrew version).
  - Succeeded with the official PyPI packages instead: `pip install eclipse-sumo sumolib traci`. This bundles the `sumo` and `netconvert` binaries directly into `.venv/bin/`, so no separate system install is needed.
  - Verified: `sumo --version` and `netconvert --version` both report **Eclipse SUMO 1.27.1**.
  - `SUMO_HOME` is exported automatically by `.venv/bin/activate` (needed by `sumo-rl`/`traci`) — points at `.venv/lib/python3.14/site-packages/sumo`.

- **Installed all other Python dependencies** into `.venv` (see `requirements.txt` for the full list and purpose of each). Notably: `osmnx` (OpenStreetMap data), `sumo-rl` + `gymnasium` + `torch` (reinforcement learning for the signal controller), `ultralytics` + `opencv-python` (YOLO vehicle detection), `pandas`/`matplotlib` (analysis).

---

### 2026-09-20 — Junction: Astra Biz Center, BSD City — **ACTIVE**

User provided both a location and a real video, unblocking Phase 1 and Phase 2 for a new junction.

- **Junction**: Astra Biz Center, BSD City, Tangerang, Banten, Indonesia — a 4-way signalized intersection. Geocoded via `osmnx`/Nominatim to **-6.2887866, 106.6386219**.
- **Video**: user-provided 4K (3840x2160, 30fps, h264) drone clip, 82.28s long, 221MB. Confirmed by inspecting sampled frames that it's a genuine top-down shot directly over the junction (the "Biz Center" sign is visible in-frame), sharp with no motion blur, showing 4 arms with clear lane markings, crosswalks, and dedicated motorcycle waiting boxes (red-marked areas) — a good match for YOLO detection. Moved into `data/video/astra_biz_center.mp4`.

#### Repo scaffolded for the junction

Set up the folder structure (`data/{video,osm,counts}/`, `scripts/`, `sumo/`, `detection/`, `analysis/`, `notebooks/`, `cache/`), and set the data-path ignore rules in `.gitignore` (`data/video/`, `data/osm/`, `cache/`, compiled `.net.xml` files, YOLO weights `*.pt`, `runs/` — all regenerable, so not committed).

#### OSM network fetched and SUMO twin built (Phase 2)

- **`scripts/fetch_osm.py`** — geocodes `"Astra Biz Center, BSD City, Tangerang, Banten, Indonesia"`, fetches the drivable network within a 500m radius via `osmnx` (`simplify=False`, `all_oneway=True`, both required for correct OSM XML export), saves to `data/osm/astra_biz_center.osm.xml` (340 nodes, 349 edges).
- Built `sumo/astra_biz_center/astra_biz_center.net.xml` via `netconvert`. Result: **115 edges, 69 nodes, 1 traffic light, 5 boundary entries / 5 exits** — a single-junction network, which is exactly the simpler, occlusion-free case the project needs.
- **`sumo/astra_biz_center/astra_biz_center.vtypes.xml`** — vehicle types tuned for Indonesian traffic: `motorcycle`, `car`, `van`, `bus`, `truck`.
- The junction's traffic-light program (auto-derived by `netconvert --tls.guess-signals` from OSM) has **3 green phases on a 90s cycle** (two ~33s main-street phases + one 6s protected-turn phase, each followed by a 6s yellow) — this fixed program is what Phase 3's baseline uses.

#### Vehicle counting attempted (Phase 1) — found a major YOLO limitation

- **`detection/count_vehicles.py`** — runs YOLOv8m with ByteTrack (`model.track(..., persist=True)`) over the full video on the Mac's GPU (`device="mps"`), counting unique tracker IDs per class to avoid double-counting the same vehicle across frames.
- First full run (default 640px inference size): **347 cars, 37 trucks, 9 buses, 0 motorcycles.**
- Inspected annotated output frames and found two problems:
  1. **Motorcycles were essentially invisible to the model** — the dense clusters of dozens of motorcycles massed in the video's bike boxes had zero detections.
  2. At default resolution, the model also produced false positives (a rooftop and construction-site debris in the bottom-left of frame got labeled "car"/"truck").
- Diagnosed by testing inference at increasing `imgsz` (640 → 1280 → 1920 → 2560) on a single frame: car detections went 13 → 66 → 81 → 76 (confirms 4K frames were being heavily downscaled and losing small vehicles), but motorcycles stayed at 0 → 0 → 1 → 3 even at max resolution. Cropping into the motorcycle clusters showed the model instead classifying individual motorcycles as low-confidence "car" detections.
- **Conclusion**: this isn't a resolution problem, it's a training-distribution problem — the pretrained COCO model's "motorcycle" class was learned from street-level/side-view photos, not top-down clusters of parked/idle motorcycles, so it can't recognize them from this camera angle regardless of image size.
- **Asked the user how to proceed** (try SAHI tiled inference, manual count, accept as-is, or fine-tune) — **user chose manual counting for motorcycles specifically**, trusting YOLO's car/truck/bus counts.

#### Manual motorcycle count and demand recalibration

- Sampled 11 frames evenly across the 82s video (`ffmpeg select` every 246 frames ≈ 8.2s apart) and visually tallied vehicles in 3 of them in detail.
- Consistent pattern across all three: motorcycle clusters at the bike boxes held roughly **50-70 motorcycles visible at once**, versus roughly **25-30 cars** visible at once — a **~2:1 motorcycle:car ratio**, somewhat higher than the initial placeholder guess of 1.71:1 (2400:1400).
- **Recalibrated `scripts/generate_demand.py`'s `MODE_SPLIT`** to `motorcycle: 2600, car: 1200` veh/h (van/truck/bus unchanged at 300/150/80) to match this ratio, keeping total demand (~4330 veh/h) similar to before since that volume was already producing plausible congestion in the sanity-check sim.
- **Caveat worth remembering for Phase 5**: YOLO's raw car count (347 unique tracker IDs over 82s) wasn't independently validated against a rigorous manual count — track-ID fragmentation (occlusion/turning causing the same physical car to get a new ID) likely inflates tracker-based counts, so treat 347 as an upper-bound-ish estimate, not ground truth. The motorcycle:car *ratio* from manual counting is the actually-trusted calibration signal here, not YOLO's absolute numbers.

#### Fixed demand-generation script bugs along the way

`scripts/generate_demand.py` needed several fixes, since `randomTrips.py`'s flags don't compose the way an early version assumed:
- `--vehicle-class` and a custom `--trip-attributes type="..."` can't be used together (SUMO error: "Trip-attribute 'type' cannot be used together with option --vehicle-class") — switched to `--vclass` (aka `--edge-permission`), which filters edges by vehicle class without forcing a vType definition into the output, freeing up `--trip-attributes` to set the actual `type=` per trip.
- Each per-mode `randomTrips.py` run reset vehicle IDs from 0, causing ID collisions once merged ("Another route for vehicle X exists") — fixed with `--prefix "{veh_type}_"` per run.
- Removed `--validate` and `--additional-files` from the `randomTrips.py` calls (they redefined vTypes that clashed with our own `astra_biz_center.vtypes.xml`); validation/routing now happens once, correctly, in the final `duarouter` pass.
- An early buggy version (using `--vehicle-class` + `--vtype`) leaked stray debug files (`bus`, `car`, `motorcycle`, `truck`, `van`, `routes.rou.xml` at the repo root) via `randomTrips.py`'s internal duarouter validation call — cleaned up once the script was fixed to no longer trigger that path.

#### Digital twin sanity-checked (Phase 2 complete for this junction)

Ran the full 1-hour simulation headlessly after recalibration:
- 2,950 of 4,331 vehicles inserted within the hour (rest still queued to depart — insertion-limited by congestion, as expected for a busy signalized intersection).
- Average speed 5.80 m/s (~20.9 km/h), average waiting time 192s, average time loss 244.6s per vehicle, 158 teleports (mostly jam/yield) — all consistent with a genuinely congested urban intersection.
- **`sumo/astra_biz_center/astra_biz_center.sumocfg`** ties it together; run with `sumo -c astra_biz_center.sumocfg` (headless) or `sumo-gui -c astra_biz_center.sumocfg` (visual).

---

### 2026-09-20 (continued) — Phases 3-5: baseline, learned policy, local-LLM explanation

User asked to continue through the remaining phases, and to use a **local LLM instead of Gemini/Groq** for Phase 5 — Ollama was already installed with several models pulled (`qwen2.5:7b-instruct`, `qwen3.5:9b`, `llama3`), so no API key was needed.

#### Phase 3 — Fixed-timer baseline

- The junction's `netconvert`-derived static `tlLogic` program (3 green phases, 90s cycle — see above) *is* the fixed-timer baseline; no separate implementation needed.
- **`rl/run_baseline.py`** runs it via `sumo-rl`'s `SumoEnvironment` with `fixed_ts=True` (action ignored, original program followed exactly) for a full simulated hour, logging per-step system metrics (queue length, waiting time, speed) to `results/baseline_conn0_ep1.csv`.
- Bug fixed: `SumoEnvironment.close()` does **not** save the metrics CSV — `save_csv()` normally only fires from inside `reset()` when starting episode 2+. Since we only ever run one episode, added an explicit `env.save_csv(...)` call before `env.close()`.

#### Phase 4 — Learned policy (tabular Q-learning)

- **`rl/discretized_obs.py`** — sumo-rl's default observation is a continuous vector (per-lane density/queue), not usable as a Q-table dict key. Wrote a custom `DiscretizedObservationFunction` that collapses state down to `(current_green_phase, binned_total_queue)` — 3 phases × 6 queue bins (0-1, 2-4, 5-9, 10-19, 20-39, 40+) = 18 possible states, small enough for tabular Q-learning to converge in a modest number of episodes. Bug fixed along the way: the returned tuple needed a `.copy()` method (sumo-rl calls `.copy()` on observations internally, which plain tuples don't have) — solved with a small `HashableObs(tuple)` subclass whose `.copy()` returns `self`.
- **`rl/train_ql.py`** — trains `sumo_rl.agents.QLAgent` (alpha=0.1, gamma=0.95) with epsilon-greedy exploration (starts at 1.0, decays ×0.95/episode down to a 0.05 floor) over 40 episodes of the full 1-hour scenario, using the built-in `diff-waiting-time` reward (reduction in accumulated waiting time per decision step). Action space = 3 (which green phase to hold/switch to), decisions every 5 simulated seconds. Saves the learned Q-table to `rl/q_table.pkl`.
- **`rl/run_learned.py`** — loads the trained Q-table and runs one full evaluation hour picking the greedy (highest-Q) action at every decision point (no exploration), logging metrics to `results/learned_conn0_ep1.csv` in the same format as the baseline for direct comparison.

- **Training results**: reward stayed noisy across all 40 episodes (roughly -18 to -100 per episode, no clean upward trend) and only **15 distinct states** were ever visited out of 18 possible — a sign the agent barely explored/converged in this short a run. Kept and evaluated anyway since the point here is demonstrating the pipeline end-to-end, not squeezing out a polished policy; flagged as a caveat in the final report (see below).

#### Phase 5 — Compare & explain (local LLM)

- **`analysis/compare.py`** — loads both result CSVs, computes mean/peak queue length and mean waiting time/speed for each policy plus percentage improvement, then POSTs a plain-language-explanation prompt to a **local Ollama server** (`http://localhost:11434/api/generate`, model `qwen2.5:7b-instruct`) instead of a cloud API — verified Ollama was already running and reachable before wiring this in. Writes a final Markdown report to `analysis/report.md` with a results table plus the model's explanation aimed at a non-technical city-planner audience.
- **Caught and fixed an LLM correctness bug before shipping the report**: the first draft prompt gave the model raw signed percentages and let it reason about which strategy was better — it got this wrong twice. First pass: it read a negative "waiting time improvement" number as a positive improvement, writing "reduced by 22.7%" when the learned policy's waiting time was actually 22.7% *worse*. After fixing the prompt to state pre-computed better/worse directions in words, the second pass got the *direction* right but then swapped *which strategy* achieved which result (attributed the learned policy's queue-length win to the baseline instead). Fixed for good by having the code generate fully pre-attributed fact sentences (e.g. "Mean queue length: the learned policy is BETTER at 513.0 vehicles, vs the fixed-timer baseline at 687.6 vehicles") and instructing the model to only rephrase them, never recompute or re-derive attribution. Verified the final report matches the raw numbers correctly.

### Final results (`analysis/report.md`) — superseded, see 2026-09-21 update below

One simulated hour each, same route file, same random seed:

| Metric | Fixed-timer baseline | Learned (Q-learning) | Result |
|---|---|---|---|
| Mean queue length | 687.6 vehicles | 513.0 vehicles | Learned is 25.4% better |
| Mean waiting time | 561.8 s/vehicle | 689.1 s/vehicle | Learned is 22.7% worse |
| Mean speed | 1.31 m/s | 1.70 m/s | Learned is 29.5% better |
| Peak queue length | 1195 vehicles | 964 vehicles | Learned is lower |

**This was a genuinely mixed result, not a clean win for the learned policy** — it moved more traffic at higher speed with shorter queues, but individual vehicles that got stuck ended up waiting longer on average. This run used the old, eyeballed 2:1 motorcycle:car demand split (see below for the recalibrated version and its different result).

### Still needed / open items

- If revisiting this project: the most impactful next step would be more RL training (more episodes / better state representation), or an actual manual Count MAE validation (PLAN.md's success metric was never rigorously measured — see below).

---

### 2026-09-21 — Swapped in the geo-trax aerial detection model, recalibrated, re-ran everything

**Motivation**: the pretrained COCO YOLOv8m used for Phase 1 (`yolov8m.pt`) couldn't see motorcycles at all from this top-down drone angle (see the 2026-09-20 log above) — a training-distribution problem, not a resolution problem. [geo-trax](https://huggingface.co/rfonod/geo-trax) is a YOLOv8s model specifically trained on 19,339 annotated aerial/drone images (~679k vehicle instances) for exactly this camera angle, with per-class mAP@50 of 0.992 (car), 0.988 (bus), 0.935 (truck), 0.888 (motorcycle) on its test set — directly targeting the gap that forced manual counting last time.

#### Phase 1 — Model swap

- Removed `yolov8m.pt` (COCO weights, gitignored anyway, not committed).
- `detection/count_vehicles.py` now downloads `geotrax_hbb_yolov8s_1920_v1.pt` from Hugging Face (`rfonod/geo-trax`) via `huggingface_hub.hf_hub_download` (cached under `~/.cache/huggingface/hub`), added `huggingface_hub` to `requirements.txt`.
- Runs at `imgsz=1920` (the model's trained/validated resolution) instead of the default 640, using geo-trax's own class ids (0=Car, 1=Bus, 2=Truck, 3=Motorcycle; classes 4/5 = Pedestrian/Bicycle are noted as undertrained by geo-trax's own docs, so excluded).
- Also rewrote the annotated-output rendering to draw boxes manually via OpenCV (smaller font, single-letter class label `C`/`B`/`T`/`M`, no track ID) instead of relying on Ultralytics' default `save=True` plotting, which is not this granularly configurable.
- **New full-video counts** (82.28s, 2466 frames, unique tracker IDs): **Car 802, Motorcycle 1347, Truck 288, Bus 143** (total 2580). Motorcycles are now the largest detected class, consistent with what was visually obvious in the video but invisible to the old model — the swap directly fixed the Phase 1 blocker.
- As before, absolute counts are inflated by track-ID fragmentation (the same physical vehicle re-detected as a new ID after occlusion/stopping) — not re-litigated here, but the *proportions between classes* are more trustworthy than the raw numbers, and are what's used for recalibration below.
- **Count MAE still not rigorously measured** — no manual ground-truth count was redone against the new model's per-class output. Worth doing if this project is revisited, since PLAN.md lists Count MAE as a stated success metric and it's currently an open gap for all vehicle classes, not just motorcycles.

#### Phase 2 — Demand recalibration

- `scripts/generate_demand.py`'s `MODE_SPLIT` was previously based on a manual visual estimate (~2:1 motorcycle:car, eyeballed across 11 sampled frames) because the old model couldn't detect motorcycles at all. Recalibrated using the new model's detected class *proportions* (Car 31.1%, Motorcycle 52.2%, Truck 11.2%, Bus 5.5% of total detections) — motorcycle:car ratio is now ~1.68:1, down from the old 2:1 guess.
- geo-trax has no separate "van" class (its "Car" class folds in vans), so the detected car proportion was split 80/20 into car/van, preserving the old car:van ratio since there's no detection signal to recalibrate that split specifically.
- Total demand held at ~4330 veh/h (same level previously validated to produce plausible congestion, so only the *mix* changed, not the *volume*): **motorcycle 2260, car 1080, van 270, truck 480, bus 240** veh/h (was 2600/1200/300/150/80).
- Regenerated `sumo/astra_biz_center/astra_biz_center.rou.xml` end-to-end via `scripts/generate_demand.py` (note: this needs `source .venv/bin/activate`, not just `.venv/bin/python`, so `duarouter`/`randomTrips.py` are on `PATH`).
- Re-ran the 1-hour sanity simulation: 2769 of 4331 vehicles inserted, avg speed 5.40 m/s, avg waiting time 232.3s, 193 teleports — comparable congestion profile to before, confirms the twin is still plausibly busy after recalibration.

#### Phases 3-5 — Re-run on the recalibrated demand

- **Phase 3 baseline** (`rl/run_baseline.py`) and **Phase 4 training** (`rl/train_ql.py`, same 40 episodes / hyperparameters as before) and **evaluation** (`rl/run_learned.py`) were all re-run against the new route file. Training showed the same qualitative pattern as before — noisy reward (-40 to -100/episode, no clean convergence trend), only 15/18 possible states ever visited — this is a training-budget/state-richness limitation independent of the demand recalibration.
- **Phase 5** (`analysis/compare.py`) re-run against the new results. Along the way, fixed a **stale-assumption bug**: the LLM prompt had hardcoded a "this is a genuinely MIXED result" framing (true for the old demand mix, where the learned policy lost on waiting time) — with the new demand mix, the learned policy now wins on *all three* metrics, so that hardcoded text was actively wrong for the new numbers. Changed `build_prompt()` to compute win/loss counts from the actual `improvements` dict and switch between a "clean sweep" framing and a "mixed result" framing dynamically, rather than assuming one.
- Also needed `ollama serve` running locally (wasn't running by default) before Phase 5 could reach the local LLM.

### Final results (`analysis/report.md`) — current, after recalibration

One simulated hour each, same recalibrated route file, same random seed:

| Metric | Fixed-timer baseline | Learned (Q-learning) | Result |
|---|---|---|---|
| Mean queue length | 629.9 vehicles | 522.9 vehicles | Learned is 17.0% better |
| Mean waiting time | 584.8 s/vehicle | 363.2 s/vehicle | Learned is 37.9% better |
| Mean speed | 1.25 m/s | 1.62 m/s | Learned is 29.3% better |
| Peak queue length | 1070 vehicles | 997 vehicles | Learned is lower |

**This is now a clean sweep for the learned policy** — unlike the pre-recalibration run, it wins on every metric, not just some. Same caveats as before still apply, though:
1. **Still oversaturated** — peak queue near 1,000 vehicles and 6+ minute average waits mean the ~4,330 veh/h synthetic demand likely still exceeds this single junction's real capacity for both strategies.
2. **The Q-learning agent is still lightly trained** (40 episodes, noisy reward curve, only 15/18 states explored) — demonstrates the RL pipeline works end-to-end, not that this specific policy is production-ready.

### 2026-09-21 (continued) — Visualizing the simulation

User asked to see the running SUMO simulation. `sumo-gui` is installed (via the PyPI `eclipse-sumo` package, same as headless `sumo`), but it's built on the FOX toolkit, which needs an X11 server (XQuartz) on macOS — not installed on this machine.

- Attempted `brew install --cask xquartz` — failed partway: the cask downloads fine, but its installer needs `sudo` with an interactive password prompt, which isn't available in a non-interactive shell. **This step needs to be finished by the user directly**: run `brew install --cask xquartz`, enter the admin password when prompted, then **log out and back in** (X11 needs a fresh session). After that, `sumo-gui -c sumo/astra_biz_center/astra_biz_center.sumocfg` (run from that directory, with the venv activated) opens the junction in a live GUI — press ▶ to start, since it opens paused.
- Also, a GUI window launched from this session's sandboxed shell wouldn't display on the user's actual screen even with XQuartz installed — `sumo-gui` needs to be launched from the user's own Terminal, not by the assistant.
- As a substitute that *could* be finished end-to-end headlessly: **`analysis/plot_timeseries.py`** — plots `system_total_stopped` (queue length), `system_mean_waiting_time`, and `system_mean_speed` per simulation step for both policies over the full simulated hour, saved to `analysis/timeseries.png`. Shows the learned policy visibly holding back queue/wait growth for roughly the first 25 simulated minutes before both policies converge as the oversaturated demand overwhelms the junction either way — a clearer picture of *when* the learned policy's advantage matters than the single-number summary in `analysis/report.md` gives.

### Still needed / open items (as of the pre-rebuild state, 2026-09-21)

- Phase 6 wrap-up is complete via the results/caveats above; no further phases remain per PLAN.md scope.
- Everything runs fully locally — no API key needed for Phase 5 (Ollama), no manual counting workaround needed for Phase 1 (geo-trax).
- **Count MAE (PLAN.md's stated success metric) has never actually been measured** against manual ground truth for any class, before or after the model swap — the closest thing done was a rough 3-frame visual sanity check for motorcycles. Worth doing if this project is revisited.
- If revisiting this project: the most impactful next step would be more RL training (more episodes / richer per-approach state representation) given how little the current policy converges in 40 episodes, or validating Count MAE properly.

---

### 2026-09-21 (continued) — Phase 2 rebuilt from scratch as a custom simulator (`twin/`)

User rejected the SUMO-based simulation result as visually unsatisfactory, and `sumo-gui` was a dead end anyway (needs XQuartz/X11, which couldn't be installed non-interactively — see above). Asked for Phase 2 to be rebuilt as a simulator built entirely from scratch: free, high real-life visual quality, and guaranteed to run natively on this M3 Pro. Scope was explicitly narrowed to just Phase 2 (a working, good-looking digital twin) — Phases 3-5 are deferred and untouched.

**New package `twin/`** replaces the SUMO/`netconvert`/`sumo-gui` path entirely for Phase 2:

- **`twin/network.py`** — loads the road graph straight from the already-fetched `data/osm/astra_biz_center.osm.xml` via `ox.graph_from_xml()` (no `netconvert` step). osmnx already stores edge `length` in meters (geodesic) regardless of CRS, so physics uses that directly against the original lon/lat geometry — no separate UTM projection/calibration needed. Used `ox.consolidate_intersections()` (15m tolerance) to merge the raw OSM node cluster at the junction into one node — confirmed it lands exactly on the real signalized junction (`highway=traffic_signals` tag, degree 10). Result: 51 nodes / 90 edges, 4 entry / 4 exit boundary nodes (by in/out-degree 0) — close to the old SUMO network's shape.
- **`twin/basemap.py`** — fetches free Esri World Imagery XYZ tiles (zoom 18, ~64 tiles for this junction) and stitches them into one cached image (`data/basemap/astra_biz_center.png`, gitignored). A `PixelMapper` converts any lon/lat to on-screen pixels via standard slippy-map tile math. Verified by overlaying the OSM road geometry on the fetched image — the alignment is pixel-accurate, roads sit exactly on the real streets and the junction marker lands exactly on the real intersection (visually confirmed, including the actual "Biz Center" building visible in-frame).
- **`twin/vehicle.py`** — 5 vehicle types with parameters ported directly from `astra_biz_center.vtypes.xml` (not re-derived), plus an Intelligent Driver Model (IDM) implementation for car-following acceleration. Desired cruising speed is capped at 11 m/s regardless of a type's open-road max, matching the ~5.5 m/s average the old SUMO run measured under congestion at this specific junction.
- **`twin/spawner.py`** — Poisson-process spawner using the exact same calibrated `MODE_SPLIT` numbers as `scripts/generate_demand.py` (duplicated, not imported, to keep `twin/` independent of the SUMO-pipeline scripts — kept in sync via comment). Routes each spawned vehicle via `networkx.shortest_path` from a random entry to a random exit node; this naturally sends most traffic through the consolidated junction node without needing explicit turning-movement calibration (out of scope for this v1).
- **`twin/signals.py`** — fixed-timer 2-phase signal at the junction (33s green + 6s yellow per phase, 90s cycle, matching the real program's timing already documented above). Approach edges are split into the two phase groups by bearing (edges whose direction is within 45° of each other's axis share a phase) — correctly separates the through-street pair from the cross-street pair.
- **`twin/engine.py`** — per-tick sim loop. **Bug caught during testing**: the first version grouped car-following purely by edge, ignoring the `lanes` count entirely — a 3-lane road was being simulated as a single-file queue, causing artificial gridlock (69% of vehicles stuck at speed ~0, vehicle count climbing unboundedly past 700+ with no steady state). Fixed by assigning each vehicle a lane index (deterministic pseudo-random spread across `edge.lanes`) and grouping car-following by `(edge, lane)` instead of just `edge`. After the fix: vehicle count stabilizes around 120-140 (steady-state, not runaway), zero-speed fraction dropped to ~6%.
- **`twin/render.py`** — pygame renderer: satellite backdrop, road polylines (width scaled by lane count), a red/yellow/green signal indicator at the junction, and vehicles drawn as small oriented, type-colored rectangles offset sideways by lane so they visually spread across the road's real width instead of stacking on the centerline. Plus a HUD (sim clock, live vehicle count, fps).
- **`twin/run.py`** — entry point, `python -m twin.run` opens a live window. Time-scaled 15x (a simulated hour takes ~4 real minutes).

**New dependency**: `pygame`. Needed `brew install sdl2_ttf sdl2_image` first — no prebuilt pygame wheel exists yet for this Python version (3.14), so pip builds it from source, and without those two libraries present at build time it silently produces a pygame with the font and PNG-saving features missing (`NotImplementedError` at first use, not at import time — a manual pygame reinstall was needed after installing each).

**Verification**: ran the engine standalone for a simulated hour (no rendering) — confirmed steady-state vehicle count, no exceptions, ~1,700 steps/sec. Ran the full pipeline (network → basemap → engine → renderer) headlessly via `SDL_VIDEODRIVER=dummy` (this sandboxed session has no attached display) and saved a rendered frame — confirmed visually: real satellite imagery, roads aligned exactly to the real streets, vehicles of the right mix (motorcycle-dominant) spread across lanes and oriented correctly, signal indicator showing red on one approach and green on the other. **Not yet confirmed with an actual live window** — `python -m twin.run` needs to be run from the user's own Terminal to see it on screen, same constraint as `sumo-gui` had, except this time there's no X11/XQuartz dependency at all (`pygame`/SDL2 is Apple Silicon-native), so it should just work.

### Still needed / open items (updated 2026-09-21, post-rebuild)

- **User hasn't yet run `python -m twin.run` themselves to confirm the live window looks right** — only headless/dummy-driver verification has been done from this session.
- Phases 3-5 (baseline vs. learned comparison, RL training, LLM explanation) still run on the old SUMO pipeline and haven't been rebuilt against `twin/` yet — deferred per explicit scope for this pass.
- Turning-movement calibration at the junction is not done — `twin/spawner.py` uses shortest-path routing, not calibrated turn shares.
- The signal program is simplified to 2 phases (through-street pairs); the real program's third short protected-turn phase isn't modeled.
