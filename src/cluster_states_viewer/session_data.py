"""Discovers sessions and loads one session's position tracking (plus its
per-frame trial-flip state) and Kilosort/phy cluster data (both brain
regions). Place fields themselves are computed by place_field_worker.py,
since that's slow enough to want a background thread.
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, place_field


@dataclass
class ClusterInfo:
    cluster_id: int      # original Kilosort/phy cluster id
    region: str            # 'hc' or 'ob'
    label: str              # 'good' or 'mua'
    best_channel: int | None
    n_spikes: int           # whole-session spike count
    spike_times_ms: np.ndarray  # ephys-clock ms, whole session (not yet window-restricted)

    # filled in by place_field_worker.py, pooled across every epoch/flip
    # state - used only for the SI column, not plotted anywhere anymore:
    spike_x: np.ndarray | None = None
    spike_y: np.ndarray | None = None
    spike_hist: np.ndarray | None = None      # raw spike-count histogram
    rate_map: np.ndarray | None = None            # whole-session rate map (Hz)
    rate_map_upsampled: np.ndarray | None = None  # ...and its upsampled/smoothed version
    si: float = float('nan')                      # Skaggs SI (bits/spike), full-session rate map only

    # filled in by place_field_worker.py, restricted to the appetitive epoch
    # only - the Flip State tab's top-row rate map/color-scale reference:
    appetitive_rate_map: np.ndarray | None = None
    appetitive_rate_map_upsampled: np.ndarray | None = None

    # filled in by place_field_worker.py, one entry per config.FLIP_STATES
    # value - restricted to the appetitive epoch (see ClusterSessionData):
    rate_maps: dict = field(default_factory=dict)             # state -> rate map (Hz)
    rate_maps_upsampled: dict = field(default_factory=dict)   # state -> upsampled rate map

    # filled in by place_field_worker.py, one entry per config.EPOCHS index:
    epoch_rate_maps: dict = field(default_factory=dict)            # epoch idx -> rate map (Hz)
    epoch_rate_maps_upsampled: dict = field(default_factory=dict)  # epoch idx -> upsampled rate map
    epoch_spike_x: dict = field(default_factory=dict)               # epoch idx -> spike x positions
    epoch_spike_y: dict = field(default_factory=dict)               # epoch idx -> spike y positions


@dataclass
class GroupStats:
    """Occupancy/duration/trial-count for one subset of a session's tracked
    frames - either one flip_state value or one behavioral epoch."""
    key: int
    occupancy_time: np.ndarray  # seconds per spatial bin, same edges as the session
    duration_s: float           # total tracked time in this group
    n_trials: int                # distinct trial_number values in this group


def discover_sessions(data_root: Path):
    """(animal, session, events_path, hc_dir, ob_dir) tuples for every
    session with events.csv and at least one region's spike_times.npy.
    hc_dir/ob_dir are None when that region has no kilosort output here."""
    sessions = []
    events_root = data_root / config.EVENTS_SUBDIR
    for animal_dir in sorted(events_root.iterdir()):
        if not animal_dir.is_dir():
            continue
        for sess_dir in sorted(animal_dir.iterdir()):
            events_path = sess_dir / config.EVENTS_GLOB
            if not events_path.exists():
                continue

            region_dirs = {}
            for key, subdir, _label in config.REGIONS:
                region_dir = data_root / subdir / animal_dir.name / sess_dir.name
                if (region_dir / 'spike_times.npy').exists():
                    region_dirs[key] = region_dir

            if not region_dirs:
                continue
            sessions.append((animal_dir.name, sess_dir.name, events_path,
                              region_dirs.get('hc'), region_dirs.get('ob')))
    return sessions


def _read_label_column(path: Path) -> dict:
    """Read a phy cluster_*.tsv label file into {cluster_id: label}, using
    whichever of 'group'/'KSLabel' is actually the header - cluster_group.tsv
    is headed 'KSLabel' (and lists every cluster) until someone actually
    curates in phy, at which point it's headed 'group' and lists only the
    clusters that were manually reviewed."""
    df = pd.read_csv(path, sep='\t')
    label_col = 'group' if 'group' in df.columns else 'KSLabel'
    return dict(zip(df['cluster_id'].astype(int), df[label_col]))


def load_region_clusters(region_dir: Path, region_key: str) -> list[ClusterInfo]:
    """Load one region's Kilosort/phy output, keeping only clusters labeled
    per config.INCLUDE_LABELS with at least config.MIN_SPIKES spikes.

    Deliberately does not use cluster_info.tsv - that file is only written
    once a session has been manually opened in phy (verified: several
    sessions here never have it). cluster_KSLabel.tsv (automatic, always
    present) is the base label; cluster_group.tsv overrides it per-cluster
    wherever that file is actually headed 'group' (i.e. curation happened),
    so every cluster ends up labeled good/mua/noise with 'noise' only ever
    coming from manual curation.
    """
    spike_times = np.load(region_dir / 'spike_times.npy').flatten()
    spike_clusters = np.load(region_dir / 'spike_clusters.npy').flatten()
    templates = np.load(region_dir / 'templates.npy')

    labels = _read_label_column(region_dir / 'cluster_KSLabel.tsv')
    group_path = region_dir / 'cluster_group.tsv'
    if group_path.exists():
        group_df = pd.read_csv(group_path, sep='\t')
        if 'group' in group_df.columns:
            labels.update(dict(zip(group_df['cluster_id'].astype(int), group_df['group'])))

    clusters = []
    for cluster_id, label in labels.items():
        if label not in config.INCLUDE_LABELS:
            continue

        mask = spike_clusters == cluster_id
        n_spikes = int(mask.sum())
        if n_spikes < config.MIN_SPIKES:
            continue

        cluster_spike_times_ms = spike_times[mask] / (config.SAMPLING_RATE_HZ / 1000.0)

        best_channel = None
        if cluster_id < len(templates):
            template = templates[cluster_id]
            best_channel = int(np.argmax(np.max(np.abs(template), axis=0)))

        clusters.append(ClusterInfo(
            cluster_id=cluster_id, region=region_key, label=label,
            best_channel=best_channel, n_spikes=n_spikes,
            spike_times_ms=cluster_spike_times_ms,
        ))
    return clusters


def _has_phy_curation_file(region_dir: Path) -> bool:
    """cluster_info.tsv is only written once a session has been manually
    opened in phy - its absence means the region's cluster labels are
    Kilosort's automatic KSLabel only, never reviewed by a person."""
    return (region_dir / 'cluster_info.tsv').exists()


class ClusterSessionData:
    def __init__(self, animal: str, session: str, events_path: Path,
                 hc_dir: Path | None, ob_dir: Path | None):
        self.animal = animal
        self.session = session
        self.events_path = events_path

        x_col, y_col = f'{config.POSITION_POINT}_x', f'{config.POSITION_POINT}_y'
        needed = {config.TIMESTAMP_COLUMN, x_col, y_col,
                  config.FLIP_STATE_COLUMN, config.TRIAL_NUMBER_COLUMN,
                  config.REWARD_STATE_COLUMN, config.POKE_LEFT_COLUMN,
                  config.POKE_RIGHT_COLUMN, config.ITI_COLUMN}
        events = pd.read_csv(events_path, usecols=lambda c: c in needed)
        # Epoch is computed on the full chronological event stream, before
        # the position-tracking dropna below, so a dropped-tracking frame
        # can never hide a reward_state/poke/iti transition from the state
        # machine (see place_field.compute_epochs).
        events = events.sort_values(config.TIMESTAMP_COLUMN)
        events['_epoch'] = place_field.compute_epochs(
            events[config.REWARD_STATE_COLUMN].to_numpy(),
            events[config.POKE_LEFT_COLUMN].to_numpy(),
            events[config.POKE_RIGHT_COLUMN].to_numpy(),
            events[config.ITI_COLUMN].to_numpy(),
            events[config.TIMESTAMP_COLUMN].to_numpy(),
            config.FEEDING_GAP_TOLERANCE_S)
        events = events.dropna(subset=[config.TIMESTAMP_COLUMN, x_col, y_col])

        self.frame_ms = events[config.TIMESTAMP_COLUMN].to_numpy(dtype=float)
        self.x = events[x_col].to_numpy(dtype=float)
        self.y = events[y_col].to_numpy(dtype=float)
        self.flip_state = events[config.FLIP_STATE_COLUMN].to_numpy()
        self.trial_number = events[config.TRIAL_NUMBER_COLUMN].to_numpy()
        self.epoch = events['_epoch'].to_numpy()

        # Bin edges tile the known fixed arena extent (not the tracked
        # positions' own min/max), so they're the same across every session
        # and shared across every cluster and every per-state rate map here.
        self.x_edges, self.y_edges = place_field.make_bin_edges(
            config.ARENA_X_RANGE_PX, config.ARENA_Y_RANGE_PX, config.BIN_SIZE_PX)
        self.occupancy_time, self.time_per_frame_s = place_field.compute_occupancy(
            self.frame_ms, self.x, self.y, self.x_edges, self.y_edges)
        self.p_i = (self.occupancy_time / np.sum(self.occupancy_time)).flatten()

        # The Flip State tab is scoped to the appetitive epoch only (search +
        # ITI), so every flip-state's occupancy/duration/trial-count below is
        # restricted to appetitive frames, not the whole session.
        self.appetitive_mask = self.epoch == place_field.EPOCH_APPETITIVE
        appetitive_mask = self.appetitive_mask
        self.appetitive_occupancy_time = place_field.occupancy_from_positions(
            self.x[appetitive_mask], self.y[appetitive_mask],
            self.x_edges, self.y_edges, self.time_per_frame_s)

        self.flip_state_stats: dict[int, GroupStats] = {}
        for state in config.FLIP_STATES:
            mask = (self.flip_state == state) & appetitive_mask
            occ = place_field.occupancy_from_positions(
                self.x[mask], self.y[mask], self.x_edges, self.y_edges, self.time_per_frame_s)
            n_trials = int(np.unique(self.trial_number[mask]).size) if mask.any() else 0
            self.flip_state_stats[state] = GroupStats(
                key=state, occupancy_time=occ, duration_s=float(occ.sum()), n_trials=n_trials)

        self.epoch_stats: dict[int, GroupStats] = {}
        for i in range(len(config.EPOCHS)):
            mask = self.epoch == i
            occ = place_field.occupancy_from_positions(
                self.x[mask], self.y[mask], self.x_edges, self.y_edges, self.time_per_frame_s)
            n_trials = int(np.unique(self.trial_number[mask]).size) if mask.any() else 0
            self.epoch_stats[i] = GroupStats(
                key=i, occupancy_time=occ, duration_s=float(occ.sum()), n_trials=n_trials)

        # Region keys present but missing phy's manually-curated cluster_info.tsv
        # (labels for these come from Kilosort's automatic KSLabel only) -
        # surfaced as a flag in the UI.
        self.uncurated_regions: list[str] = []

        self.clusters: list[ClusterInfo] = []
        for key, region_dir in (('hc', hc_dir), ('ob', ob_dir)):
            if region_dir is None:
                continue
            self.clusters += load_region_clusters(region_dir, key)
            if not _has_phy_curation_file(region_dir):
                self.uncurated_regions.append(key)
