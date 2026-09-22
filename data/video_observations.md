# Video observations — Astra Biz Center junction

Direct observations from `data/video/astra_biz_center.mp4` (82.28s, 4K, top-down drone,
night), taken to calibrate the digital twin's signal timing and demand. Frames sampled
every 5s across the full clip, plus tight crops at native resolution for specific checks.
Where something couldn't be confirmed directly, that's stated rather than guessed at.

## Signal behavior

**Can't be read directly:** the drone is nearly straight overhead, so the traffic
signal housings are only ever seen from above (their black tops) — the illuminated
face pointing at approaching traffic is never in frame. Signal *color* was not
observable in this footage. Everything below is inferred from vehicle behavior only.

**What was observed, high confidence:**
- Two of the four arms hold a large, essentially unmoving motorcycle queue (tens of
  motorcycles packed into the marked motorcycle box) for the *entire* 82s clip, with
  no visible discharge.
- A third arm's motorcycle queue is large and static for the first ~45s, then visibly
  discharges/clears between roughly t=45s and t=60s.
- The fourth arm never shows a large stationary queue at all — traffic there moves
  continuously throughout.
- At no point in the clip are all four arms stopped simultaneously, and at no point
  does only one arm move in isolation — movement always involves traffic from more
  than one direction crossing at once.

**Interpretation (tried, then reverted):** this pattern initially read as consistent
with an opposing-pair signal (two arms share a green, then the cross-street's two
arms share the next), and was briefly implemented that way, merging opposing arms
into shared rotation slots. **Corrected on explicit instruction: only one arm's
lights are ever green at a time, never two together.** The video's queue-persistence
pattern doesn't actually distinguish the two designs — a queue that never fully
clears during its own single-approach green (chronic oversaturation, very plausible
for a motorcycle box this dense) looks identical to a queue that's genuinely still
red under an opposing-pair scheme — so the single-approach reading stands as the
correct one. The signal color itself was never visible either way (see above).

**Adaptation applied:** `lampu_merah_vietnam_junction.json`'s own 4 independent
phases (P_N, P_S, P_W, P_E, each conflicting with all 3 others - i.e. only one ever
green) are used as-is: one rotation slot per phase, 33s green + 6s yellow, cycling
N → S → W → E → N (~156s full cycle). No merging.

## Which video arm is which compass label — not confirmed

The drone's frame orientation relative to true north was not established (this would
need a proper pixel-to-map georeference, not attempted here), and an earlier pass this
session used compass-sounding names for the arms (e.g. "Boulevard Utara (east)") that
were descriptive shorthand from OSM node numbering, not verified compass bearings. So
while the *video* clearly shows two arms much busier (persistent large motorcycle
queues) than the other two, that could not be confidently mapped onto the lane
file's specific N/S/E/W labels. Documented here rather than guessed into the demand
model as fact.

## Vehicle counts by type

Overall type mix across the full clip (geo-trax detection, already on record from
Phase 1, unique tracker IDs over 82s): **Car 802, Motorcycle 1347, Truck 288, Bus
143** (~31% car / 52% motorcycle / 11% truck / 6% bus of total detections). As noted
when this was first measured, the absolute counts are inflated by track-ID
fragmentation (occlusion/stopping causes the same physical vehicle to get a new ID),
but the *proportions* are the trusted signal — already what `spawner.py`'s
`MODE_SPLIT` is calibrated from, unchanged here.

**Per-arm distribution (visual, approximate — not re-run through YOLO per arm):** two
arms visibly carry much denser motorcycle queues (tens of motorcycles clustered at
once) alongside moderate car queues; a third arm carries a moderate motorcycle
cluster mixed with cars, vans, and the occasional bus; the fourth arm carries very
few queued motorcycles and comparatively steady, moderate car flow with occasional
trucks — this is the arm that never shows a large stationary queue in the signal
observations above either.

## Speed

Free-flowing vehicles (not blocked by a queue) were tracked over a 0.5s frame gap
and estimated at roughly **10–13 m/s (36–47 km/h)** — a rough visual estimate, not a
calibrated pixel-tracking measurement. This is consistent with (slightly above) the
project's already-documented congested-average figure of **~5.5 m/s**, which is what
`twin/vehicle.py`'s `URBAN_SPEED_CAP = 11.0 m/s` was already set from. No change made
here — the existing cap already sits right in the observed range.

## What changed in the simulation as a result

1. **Signal phases** (`twin/lane_network_import.py`): kept as the source file's own
   4 independent phases, one rotation slot each — only one approach's lights are
   ever green at a time (33s green + 6s yellow per slot, `twin/signals.py`'s
   existing `GREEN_S`/`YELLOW_S`). An opposing-pair merge was tried and reverted
   (see above).
2. **Speed cap**: left unchanged — already consistent with what was observed.
3. **Per-arm demand weighting**: added a modest spawn-rate bias (1.3x vs 0.85x)
   favoring two of the four arms, matching the observed uneven queue sizes — flagged
   as a best guess on *which* two arms, since the video-to-compass mapping isn't
   confirmed (see above).
