# cluster-states-viewer

Desktop viewer for cbm-odor sessions' spike-sorted clusters, split two
different ways: by trial-flip state and by behavioral epoch. Loads a
session's hippocampus (`hc-ks`) and olfactory-bulb (`ob-ks`) Kilosort/phy
output, computes each cluster's place field split each way, and shows them
in a sortable table with two plot tabs.

This is a variant of `cluster-viewer` that skips the shuffle-null
significance test (SSI) - though it still reports the Skaggs SI itself for
the full-session rate map - and instead splits the place field into a
separate rate map per group.

## Setup

```
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```
.venv\Scripts\python.exe src\cluster_states_viewer\main.py
```

Pick an animal/session and click Load. Sessions are discovered from
`<DATA_ROOT>/<EVENTS_SUBDIR>/<animal>/<session>/events.csv` (position
tracking) paired with `<DATA_ROOT>/<HC_SUBDIR|OB_SUBDIR>/<animal>/<session>/`
(Kilosort/phy output for each brain region) - a session needs events.csv
and at least one region present. Data root and subdirectory names are set
in `src/cluster_states_viewer/config.py`.

## What it shows

- On Load, every `good`/`mua` cluster (per phy's `group` label, falling
  back to Kilosort's automatic `KSLabel` for clusters nobody's manually
  reviewed; `noise` is always excluded) from both regions has its place
  field computed on a background thread.
- A sortable table (Cluster, Region, Label, Channel, N Spikes, SI) - click a
  row, or use the up/down arrow keys once a row is selected, to plot that
  cluster. SI is the Skaggs spatial information (bits/spike) of the
  full-session rate map only (no per-state SI, no significance test).
- Two plot tabs, both built around the same top row (pooled across the
  whole session, as in cluster-viewer): trajectory + spike-position
  overlay, occupancy histogram, and the full-session rate map (the same
  place field cluster-viewer shows). Each tab's bottom row splits that
  place field a different way:
  - **Flip State** tab: one rate map per `flip_state` value (0, 1, 2). A
    spike's state comes from its nearest tracked frame's `flip_state`
    (constant within a trial, so this is exact).
  - **Epoch** tab: one rate map per behavioral epoch - **appetitive** (ITI
    + search, until the reward cue), **consummatory** (cue until the
    animal pokes a reward port), and **feeding** (poke until the next ITI
    begins). A session's full event stream (reward_state/poke_left/
    poke_right/iti) is walked chronologically with a small state machine
    (see `place_field.compute_epochs`) to label every tracked frame, since
    `reward_state` itself is only true for about one frame (the cue pulse)
    rather than for the whole wait-for-poke window.
  In both tabs, each group's own occupancy normalizes its rate map - bin
  edges and the color scale (taken from the full-session map) are shared
  across every panel so they stay directly comparable. Each bottom-row
  subplot title includes that group's total tracked duration (seconds) and
  number of trials.
- The overall plot title (shown on both tabs) includes the animal/session
  and the selected cluster's id/region.

Position tracking uses `events.csv`'s sleap-tracked `centroid_x/y` and its
`timestamp_ms` column - the *ephys*-clock timestamp (not `bonsai_ts`, which
is Bonsai's own wall clock), since spike times from `spike_times.npy` are on
the ephys/Kilosort sample clock and need to be compared against something
in that same clock domain.

## Known limitations / next steps

- Spatial bins use a fixed pixel size (`config.BIN_SIZE_PX`, ~1cm) with
  arena bounds auto-derived from the tracked positions, rather than a fixed
  bin count or a hand-set arena rectangle.
- No cross-region or cross-session comparison views; one session's clusters
  at a time.
- No SSI/significance test - see `cluster-viewer` for that.
# cluster-states-viewer
