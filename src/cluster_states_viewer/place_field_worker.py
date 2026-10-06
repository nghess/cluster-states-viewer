"""Computes place fields for every cluster in a loaded session on a
background thread, so a session with many clusters doesn't freeze the UI.

For each cluster this computes one pooled (all flip states/epochs)
trajectory/spike-count histogram for the top-row panels, plus one rate map
per trial-flip state and one rate map per behavioral epoch for the two
tabs' bottom rows. A spike's flip state/epoch is looked up from its nearest
tracked frame's flip_state/epoch (flip_state is constant within a trial, so
that lookup is exact; epoch can change within a trial, but a spike's
*nearest* frame is still the correct frame to attribute it to)."""
import numpy as np
from PySide6.QtCore import QThread, Signal

from . import config, place_field
from .session_data import ClusterSessionData


class PlaceFieldWorker(QThread):
    progress = Signal(int, int)  # (done, total)
    finished_ok = Signal(list)   # list[ClusterInfo], place fields filled in

    def __init__(self, session: ClusterSessionData, parent=None):
        super().__init__(parent)
        self.session = session

    def run(self):
        session = self.session
        clusters = session.clusters
        total = len(clusters)

        for i, cluster in enumerate(clusters):
            spike_times = cluster.spike_times_ms
            # restrict to the tracked time window
            spike_times = spike_times[(spike_times >= session.frame_ms[0]) &
                                       (spike_times <= session.frame_ms[-1])]

            frame_idx = place_field.align_spikes_indices(spike_times, session.frame_ms)
            spike_x, spike_y = session.x[frame_idx], session.y[frame_idx]
            spike_state = session.flip_state[frame_idx]
            spike_epoch = session.epoch[frame_idx]

            rate_map, spike_hist = place_field.compute_rate_map(
                spike_x, spike_y, session.occupancy_time,
                session.x_edges, session.y_edges, config.MIN_OCCUPANCY_S)

            cluster.spike_x = spike_x
            cluster.spike_y = spike_y
            cluster.spike_hist = spike_hist
            cluster.rate_map = rate_map
            cluster.rate_map_upsampled = place_field.upsample_rate_map(
                rate_map, factor=config.UPSAMPLE_FACTOR)
            cluster.si = place_field.skaggs_si(rate_map.flatten(), session.p_i)

            # Flip State tab is scoped to the appetitive epoch only (see
            # ClusterSessionData), so both its own top-row rate map and
            # every per-flip-state rate map below are restricted the same way.
            appetitive_mask = spike_epoch == place_field.EPOCH_APPETITIVE
            appetitive_rate_map, _ = place_field.compute_rate_map(
                spike_x[appetitive_mask], spike_y[appetitive_mask], session.appetitive_occupancy_time,
                session.x_edges, session.y_edges, config.MIN_OCCUPANCY_S)
            cluster.appetitive_rate_map = appetitive_rate_map
            cluster.appetitive_rate_map_upsampled = place_field.upsample_rate_map(
                appetitive_rate_map, factor=config.UPSAMPLE_FACTOR)

            for state in config.FLIP_STATES:
                mask = (spike_state == state) & appetitive_mask
                stats = session.flip_state_stats[state]
                rate_map, _ = place_field.compute_rate_map(
                    spike_x[mask], spike_y[mask], stats.occupancy_time,
                    session.x_edges, session.y_edges, config.MIN_OCCUPANCY_S)
                cluster.rate_maps[state] = rate_map
                cluster.rate_maps_upsampled[state] = place_field.upsample_rate_map(
                    rate_map, factor=config.UPSAMPLE_FACTOR)

            for epoch_idx in range(len(config.EPOCHS)):
                mask = spike_epoch == epoch_idx
                stats = session.epoch_stats[epoch_idx]
                cluster.epoch_spike_x[epoch_idx] = spike_x[mask]
                cluster.epoch_spike_y[epoch_idx] = spike_y[mask]
                rate_map, _ = place_field.compute_rate_map(
                    spike_x[mask], spike_y[mask], stats.occupancy_time,
                    session.x_edges, session.y_edges, config.MIN_OCCUPANCY_S)
                cluster.epoch_rate_maps[epoch_idx] = rate_map
                cluster.epoch_rate_maps_upsampled[epoch_idx] = place_field.upsample_rate_map(
                    rate_map, factor=config.UPSAMPLE_FACTOR)

            self.progress.emit(i + 1, total)

        self.finished_ok.emit(clusters)
