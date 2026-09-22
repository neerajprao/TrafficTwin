# TrafficTwin — Project Timeline

Everything done on this project, grouped by build phase (see [PLAN.md](PLAN.md) for the phase definitions). Within each phase, entries are in the order they happened, and name every file created, modified, or deleted, plus everything downloaded/installed. See [PROGRESS.md](PROGRESS.md) for the earlier, narrative log this file was originally summarized from — from the digital-twin rebuild onward, this file is now the more current and detailed of the two.

---

## Phase 0 — Environment setup — **Done**

- Created the Python virtual environment (`.venv/`, Python 3.14.3, via `python3 -m venv .venv`).
- **Installed SUMO via PyPI, not Homebrew**: `brew install sumo` failed (not in Homebrew core); the `dlr-ts/sumo` tap failed (`cxxstdlib_check` incompatible with the installed Homebrew version). Succeeded with `pip install eclipse-sumo sumolib traci`, which bundles the `sumo`/`netconvert` binaries into `.venv/bin/` directly. `SUMO_HOME` is exported by `.venv/bin/activate`.
- Installed the rest of `requirements.txt`: `osmnx`, `sumo-rl` + `gymnasium` + `torch` (RL), `ultralytics` + `opencv-python` (YOLO), `pandas`/`matplotlib` (analysis), `huggingface_hub` (model download).
- **Installed pygame's native build dependencies**: no prebuilt wheel exists for Python 3.14, so `pip install pygame` builds from source; `brew install sdl2_ttf sdl2_image` was required first (font rendering and PNG loading are silently missing otherwise — the broken build doesn't fail, it just raises `NotImplementedError` on first use of the missing feature, not at import time). Reinstalled pygame after each brew install to pick them up.
- User provided the junction location and a real 4K drone video (Astra Biz Center, BSD City, Indonesia — 82.28s, top-down, sharp, motorcycle waiting boxes visible) — placed at `data/video/astra_biz_center.mp4` (gitignored, not committed, ~221MB).
- Scaffolded the repo folder structure: `data/{video,osm,counts,basemap,edited}/`, `scripts/`, `sumo/`, `detection/`, `analysis/`, `notebooks/`, `cache/`, `twin/`. Set `.gitignore` rules for regenerable/large data (`data/video/`, `data/osm/`, `data/basemap/`, `data/edited/`, `mg_road/data/`, `cache/`, `*.net.xml`, `*.pt`, `runs/`, `.venv/`, `__pycache__/`).
- **Closed out this session** (2026-09-22): audited the environment end to end — every import in `requirements.txt` and every package `twin/` actually uses at runtime (`osmnx`, `pygame`, `shapely`, `networkx`, `requests`, `PIL`, `opencv-python`, `ultralytics`, `huggingface_hub`, `sumolib`, `traci`, `pandas`, `matplotlib`, `gymnasium`, `torch`) imports cleanly in `.venv`, `pygame`'s SDL2 font/PNG support is intact, `sumo`/`netconvert` both report 1.27.1. Found and fixed one real gap: `requirements.txt` never explicitly listed `networkx` or `shapely`, even though `twin/network.py`, `twin/persistence.py`, `twin/editor.py`, `twin/junction_builder.py`, and `twin/lane_network_import.py` all import them directly — they were only present because `osmnx` happens to pull them in transitively, which would silently break if a future `osmnx` version dropped that dependency. Added both explicitly to `requirements.txt`, plus a comment noting `requests` (already listed) is also used directly by `twin/basemap.py`, not just Phase 5's Ollama calls.

**Downloaded/installed this phase:** `eclipse-sumo`, `sumolib`, `traci`, `osmnx`, `sumo-rl`, `gymnasium`, `torch`, `ultralytics`, `opencv-python`, `pandas`, `matplotlib`, `huggingface_hub` (pip); `sdl2_ttf`, `sdl2_image` (Homebrew); `pygame` (pip, built from source).

## Phase 1 — Count the Traffic — Done, one open gap
- **First pass — hit a major limitation**: ran a pretrained COCO YOLOv8m model with ByteTrack over the full video. Detected cars/trucks/buses but **completely missed motorcycles** — a training-distribution problem (COCO's motorcycle class was learned from street-level photos, not top-down clusters), not a resolution problem. Fell back to **manual visual counting** for motorcycles specifically, trusting YOLO's counts for the other classes.
- **Model swap**: replaced the pretrained COCO YOLOv8m with **[geo-trax](https://huggingface.co/rfonod/geo-trax)** — a YOLOv8s model trained specifically on aerial/drone footage, downloaded via Hugging Face (`geotrax_hbb_yolov8s_1920_v1.pt`, cached under `~/.cache/huggingface/hub`).
- Re-ran detection at the model's native 1920px resolution: **Car 802, Motorcycle 1347, Truck 288, Bus 143** — motorcycles now detected natively, no manual counting needed. (Absolute counts are inflated by track-ID fragmentation; the *proportions* — ~31% car / 52% motorcycle / 11% truck / 6% bus — are the trusted signal and what `spawner.py`'s `MODE_SPLIT` is calibrated from.)
- Reworked the annotated-video output to draw smaller, single-letter class labels (C/B/T/M) with no track ID clutter, per request.
- **Open gap, unchanged**: Count MAE (PLAN.md's own stated success metric) has never been measured against manual ground truth for any class. Flagged repeatedly through the project; still true.

## Phase 2 — Build the Digital Twin — substantially rebuilt this session

### Before this session (already on record)
- Fetched the OSM road network around Astra Biz Center via `osmnx`; built a SUMO network via `netconvert` (115 edges, 69 nodes, 1 traffic light); defined 5 vehicle types tuned for Indonesian traffic; calibrated demand twice (manual 2:1 moto:car ratio, then geo-trax's ~1.68:1); rebuilt the whole thing from scratch as a custom pygame simulator (`twin/`) after the user rejected SUMO's visuals and `sumo-gui` turned out to need XQuartz/X11 (not installed, admin password needed, couldn't complete non-interactively).

### This session

**1. Fixed a phantom-signal bug (roads/signals "not proper").**
Investigated by extracting video frames (`ffmpeg` was broken — missing `libjxl` dylib after a Homebrew upgrade — used `opencv-python` instead) and rendering the twin headlessly at matching zoom for comparison. Found `net.junction_nodes` was `[0, 1, 12]` instead of just `[1]` (the real crossroads): nodes 0 and 12 were OSM-tagged `highway=traffic_signals` points ~43–93m up the same road, almost certainly mid-block pedestrian crossings, each getting an invented generic 2-phase program.
- **Modified**: `twin/network.py` (`load_network()` gained a `signal_light_coords` param; when given, only the junction(s) those real surveyed coordinates resolve to become `junction_nodes` — raw OSM tags elsewhere no longer qualify on their own), `twin/app.py` (threaded the param through to `load_network()`).
- Verified: `junction_nodes` reduced to `[1]`, zoomed render showed exactly 4 signals at the real junction, 1-hour headless run clean.

**2. Added turn-based lane assignment** (free-left/straight/right/u-turn each get their own lane where possible).
- **Modified**: `twin/network.py` (added `classify_turn()`, `STRAIGHT_MAX_DEG`/`UTURN_MIN_DEG` constants — a turn-angle classifier separate from the existing left-turn-skips-signal logic), `twin/engine.py` (added `_lane_range_for_movement()` mapping movement → lane range per lane count, replaced the old random `(id + route_idx) % lanes` lane picker with a single `_lane_for(v, route_idx)` used consistently at spawn, lookahead, and edge-transition).
- Verified: tallied actual vehicle lane assignments against expected ranges (matched exactly), 1-hour run clean.

**3. Rebuilt the junction entirely from scratch (no OSM lanes/signals).**
User asked to stop trusting OSM's lane/signal data and build the roads by hand instead, using only real-world position/direction for alignment.
- **Created**: `twin/junction_builder.py` (`Arm` dataclass, `build_junction()`, `build_astra_biz_center()` — 4 arms with lane counts set by eye from the video: 5 lanes for the two "Jalan BSD Raya Utama" arms, 4 for the two "Jalan BSD Boulevard Utara" arms; divided-carriageway offset per arm to match the video's medians).
- Ran it to generate `data/edited/astra_biz_center.json` (9 nodes, 8 edges) — first version of the hand-built junction.
- **Deleted and regenerated** `data/basemap/astra_biz_center.png` (stale — cached for the old, much larger OSM bounds; the new tighter bounds needed a fresh satellite fetch).
- Verified: all 4 real surveyed signal coordinates still resolved to the correct arm; 1-hour run and render both clean.

**4. Built full manual road + signal editing in-app**, then started from a blank canvas.
User asked to place roads, directions, and signals by hand rather than have them generated.
- **Modified**: `twin/network.py` (added `signal_approaches` field to `NetworkData` — node → ordered rotation slots of edges; `toggle_junction_signal()`, `toggle_signal_approach()`; `rebuild_derived()` gained pruning for stale approaches, a "leaf node" rule so a hand-drawn dead end — always a bidirectional pair via `add_road()` — still counts as a valid spawn/despawn point, and a "fully closed network" fallback so a network with no boundary at all still spawns traffic somewhere rather than never spawning anything), `twin/persistence.py` (schema gained `signal_approaches` and an explicit `bounds` field, needed for a truly empty blank canvas), `twin/signals.py` (`SignalController` reads `net.signal_approaches` directly instead of matching real-world coordinates), `twin/engine.py` (dropped the now-redundant `signal_light_coords` param), `twin/render.py` (dropped `signal_light_coords`, added numbered approach-rotation markers and an in-editor label showing a selected road's rotation position), `twin/editor.py` (added `toggle_selected_junction()`/`toggle_selected_approach()` for the new **T**/**A** keys), `twin/app.py` (wired **T** to toggle a selected node's signal status, **A** to add/remove the selected road from that junction's rotation), `twin/spawner.py` (guarded `_make_route()` against empty entry/exit lists so a not-yet-drawn blank canvas doesn't crash), `twin/run.py` (removed the now-dead hardcoded `EXTRA_SIGNAL_COORDS`/`SIGNAL_LIGHT_COORDS`, since signals are now configured entirely in-app).
- **Deleted** the hand-built 4-arm junction from step 3 and replaced `data/edited/astra_biz_center.json` with a genuine blank canvas (0 nodes, 0 edges, real-world bounds only, so there's room to draw in).
- Verified: blank canvas loads and renders with no crash, spawns nothing until roads exist as expected.

**5. Added autosave.**
- **Modified**: `twin/app.py` (`AUTOSAVE_INTERVAL_S` constant; `maybe_save()` now resets the `edited` flag after a successful save so it doesn't rewrite the file needlessly; a periodic check in the main loop saves once per real second whenever there's an unsaved edit).

**6. Fixed two real bugs the user hit while actually using the editor.**
- **"Network move coordinates not being saved"** — actually a stale satellite-image cache, not a data-loss bug: `load_basemap()` cached by file existence only, never checking whether the *current* network bounds still matched what the cached image was fetched for. After a move-network-mode drag crossed a satellite-tile boundary (~40m), the road data (saved correctly) was being plotted against the same old tile image at a newly (and wrongly) computed pixel origin.
  - **Modified**: `twin/basemap.py` (added `_tile_extent()` and `_meta_path()`; `load_basemap()` now records the exact tile-grid extent it fetched in a `<cache>.meta.json` sidecar and only trusts the cached image if the current request's extent still matches — otherwise it refetches automatically).
- **"Can't see vehicles when not in edit mode"** — the user's actual saved network (26 nodes, 52 edges) turned out to be a fully closed loop (every node had exactly 2 neighbors), so it had zero boundary nodes and the spawner could never place a single vehicle, in or out of edit mode.
  - **Modified**: `twin/network.py` (the "fully closed network" fallback from step 4, confirmed against this exact file: 183 vehicles spawned within 5 simulated minutes afterward).

**7. Imported a richer, per-lane junction description wholesale.**
User provided `lampu_merah_vietnam_junction.json` (root of the repo) — real per-lane centerline geometry, explicit curved through-junction paths per movement, and 4 real protected signal phases — and asked for it to replace the roads and signals entirely.
- **Created**: `twin/lane_network_import.py` (`load_lane_network()` — converts the file's `nodes`/`lanes`/`connections`/`traffic_signals`/`signal_phases` into a `NetworkData`; each physical lane and each through-junction movement path becomes its own single-lane `Edge`, so routing follows the file's exact given geometry rather than this project's usual inferred-turn-lane approach; left turns reuse their `free_left_slip` lane's own already-complete geometry instead of also adding the file's redundant `connections` entry for the same path).
  - Fixed two bugs found while building this: (a) originally loaded every node in the file, including pure curve waypoints that are never real graph endpoints — these were wrongly registering as spawn/despawn points; fixed to only keep nodes actually used as some edge's `u`/`v`. (b) the synthetic "junction" namespace node (needed as a dict key for the signal rotation, since this file has no single shared junction node) had no edges of its own, so it was wrongly counting as *both* an entry and an exit node — excluded explicitly.
- **Modified**: `twin/network.py` (`signal_approaches`'s type generalized from `dict[node, list[edge]]` to `dict[node, list[list[edge]]]` — a rotation slot can now be a *group* of edges that go green together, not just one, since this file's whole 3-lane approach turns green as a unit; `toggle_signal_approach()` updated to wrap the editor's single-edge toggles as one-item groups so existing hand-editor behavior is unchanged), `twin/signals.py` (`SignalController` rewritten to cycle grouped rotation slots with a real green→yellow→red cycle, replacing the old single-edge green→red-only round robin — this also upgraded the hand-editor's own signals to get a proper yellow phase), `twin/render.py` (approach-marker drawing and the in-editor label updated for nested slot groups), `twin/persistence.py` (nested-list schema for `signal_approaches`, plus a compatibility shim so an older flat-list save file still loads), `twin/junction_builder.py` (updated to emit one-edge-per-slot groups, matching the new schema).
- Backed up the previous hand-drawn network to `/tmp/astra_biz_center_backup_before_lane_import.json` before overwriting.
- Ran the importer, saved the result to `data/edited/astra_biz_center.json` (53 nodes, 44 edges). **Deleted and regenerated** `data/basemap/astra_biz_center.png` (+ its new `.meta.json`) for the new bounds.
- Verified: all 4 signal phases cycle correctly (one 3-lane group green, proper yellow), 1-hour run clean, headless render confirmed the curved lane geometry, fanned approaches, and grouped signal markers on the real satellite imagery; regression-checked `mg_road` (OSM path, unrelated to any of this) still works.

**8. Observed the source video directly and adapted the simulation, with an explicit correction along the way.**
- Sampled ~17 frames every 5s across the full 82.28s clip, plus native-resolution crops of each corner's signal pole (confirmed the actual light color is **not observable** — the drone is close to straight overhead, so only the black top of each signal housing is ever in frame, never the illuminated face) and a 0.5s-apart frame pair to roughly estimate free-flow speed (~10–13 m/s, consistent with the project's existing ~5.5 m/s congested-average figure — no change needed there).
- **Created**: `data/video_observations.md` — records what was directly observed (two arms hold large static motorcycle queues for the entire clip, a third arm's queue visibly discharges partway through, a fourth never queues at all; multiple arms are never all stopped, or moving in true isolation, at the same time) versus what's inferred with lower confidence (exact signal phase structure — since light color isn't visible, a persistent queue during a real green and a genuinely-still-red queue look identical), and explicitly flags that the drone footage's orientation relative to true north was never established, so which video arm maps to which of the file's N/S/E/W labels is unconfirmed.
- **First adaptation (later reverted)**: read the video's paired discharge pattern as an opposing-pair signal and merged `lampu_merah_vietnam_junction.json`'s 4 independent phases into 2 shared rotation slots (N+S, W+E) in `twin/lane_network_import.py`.
- **Correction, on explicit instruction**: only one approach's lights are ever green at a time, never two together. Reverted the merge — `lane_network_import.py` now uses the file's own 4 independent phases as-is (one rotation slot per phase, unchanged from step 7), and `data/video_observations.md` was updated to describe the opposing-pair reading as tried-then-reverted rather than adopted, with the reasoning why the video evidence doesn't actually distinguish the two (a chronically oversaturated single-approach queue looks identical to a paired-phase queue from vehicle behavior alone).
- **Kept**: a modest per-arm demand weighting (two of the four arms spawn ~1.5x more traffic than the other two, via repeated entries in `net.entry_nodes`) matching the video's visibly uneven queue sizes — clearly flagged in code and in the observations file as a best guess on *which* two arms, not a confirmed one.
- Re-saved `data/edited/astra_biz_center.json` and regenerated `data/basemap/astra_biz_center.png`/`.meta.json` after both the initial adaptation and the correction. Verified each time: direct signal-state sampling across a full cycle, 1-hour headless run, render.

### Still open for Phase 2
- **Demand/capacity calibration hasn't been checked frame-by-frame against the video for this specific lane-accurate network.** A 1-hour run on the current network showed only ~25–40 vehicles present at a time with average speed ~1.8 m/s (more gridlocked than the ~5.5 m/s congested-but-moving figure this project has otherwise treated as realistic) — plausible given this network's tighter, lane-accurate capacity versus the old coarse multi-lane roads, but not actually confirmed against the video.
- **Which video arm is which compass label (N/S/E/W) is unconfirmed** — would need a proper pixel-to-map georeference of the drone footage, not attempted. The per-arm demand weighting above is a best guess, not a measured fact.
- `PLAN.md`/`PROGRESS.md` still describe the original SUMO/OpenStreetMap pipeline and don't reflect any of this session's work — not a functional gap, but stale if read expecting current state.

## Phase 3 — Baseline Signal Policy
- Ran the junction's existing fixed-timer light program headlessly as the baseline, logged metrics. Re-ran once demand was recalibrated against geo-trax's counts.
- **Superseded** — built entirely on the old SUMO pipeline (`rl/run_baseline.py`), not yet rebuilt against the current `twin/` engine (untouched this session).

## Phase 4 — Learned Signal Policy
- Built a discretized observation function and trained a tabular Q-learning agent (40 episodes) to control the light; evaluated it greedily against the baseline. Re-trained on the recalibrated demand.
- **Superseded** — same as Phase 3, built on the old SUMO pipeline (`rl/train_ql.py`/`rl/run_learned.py`), untouched this session.

## Phase 5 — Compare & Explain
- Computed mean queue length, mean waiting time, mean speed for both policies; used a local Ollama LLM (`qwen2.5:7b-instruct`) for a plain-language explanation, after fixing two rounds of LLM attribution bugs. First result was a genuinely mixed outcome; after demand recalibration, a clean sweep for the learned policy on all three metrics (fixed a stale "mixed result" framing bug in the prompt along the way).
- **Superseded** — `analysis/report.md`'s numbers are from the old SUMO pipeline, not the current twin. Untouched this session.

## Phase 6 — Wrap Up
- Updated `PLAN.md`/`PROGRESS.md` for the geo-trax swap and the Ollama switch (since superseded again by this session's work, see Phase 2's open items).
- `sumo-gui` visualization attempt abandoned (XQuartz/X11 dependency, couldn't install non-interactively); built `analysis/plot_timeseries.py`/`analysis/timeseries.png` as a headless substitute.
- **Paused, then resumed this session** with the full custom-engine rebuild documented under Phase 2 above. Not yet revisited for the current state of the twin.

---

*Updated through the signal-phase correction (one approach green at a time, never two) and the Phase 0 environment audit. Update as work resumes.*
