"""Place-field math: spike alignment, occupancy/rate maps. Adapted from
cluster-viewer's place_field.py, minus the Skaggs SI / shuffle-null
significance test (this viewer skips SSI entirely) and with spike-to-frame
alignment split out so a spike's nearest frame index can be reused to look
up which trial-flip state it fell in. Pure numpy/scipy - no plotting here.
"""
import numpy as np


def make_bin_edges(x_range, y_range, bin_size_px):
    """
    Spatial bin edges tiling a fixed physical extent exactly (e.g. the known
    arena bounds in config.ARENA_X_RANGE_PX/ARENA_Y_RANGE_PX), rather than
    the tracked positions' own min/max - which run slightly outside the
    arena in places (tracking noise) and would otherwise shift bin edges off
    the true (0, 0) corner and stretch them past the far wall.
    """
    def edges_for(lo, hi):
        n_bins = max(1, round((hi - lo) / bin_size_px))
        return np.linspace(lo, hi, n_bins + 1)

    return edges_for(*x_range), edges_for(*y_range)


def align_spikes_indices(spike_times, frame_ms):
    """Nearest-tracked-frame index for each spike time."""
    idx = np.searchsorted(frame_ms, spike_times)
    idx = np.clip(idx, 1, len(frame_ms) - 1)
    left_diff = np.abs(spike_times - frame_ms[idx - 1])
    right_diff = np.abs(spike_times - frame_ms[idx])
    return np.where(left_diff < right_diff, idx - 1, idx)


def align_spikes(spike_times, frame_ms, x, y):
    """Nearest-tracked-frame (x, y) for each spike time."""
    idx = align_spikes_indices(spike_times, frame_ms)
    return x[idx], y[idx]


def frame_interval_s(frame_ms):
    """Median inter-frame interval (seconds), from the first 100 gaps -
    assumes a roughly constant frame rate."""
    return float(np.median(np.diff(frame_ms[:100])) / 1000.0)


def compute_occupancy(frame_ms, x, y, x_edges, y_edges):
    """
    Time spent per spatial bin (seconds), from tracked positions.

    Assumes a roughly constant frame interval (uses the median of the first
    100 inter-frame gaps to convert frame counts to seconds).
    """
    time_per_frame_s = frame_interval_s(frame_ms)
    occupancy_time = occupancy_from_positions(x, y, x_edges, y_edges, time_per_frame_s)
    return occupancy_time, time_per_frame_s


def occupancy_from_positions(x, y, x_edges, y_edges, time_per_frame_s):
    """
    Time spent per spatial bin (seconds) for an arbitrary subset of tracked
    positions, given a frame interval computed elsewhere. Used to build a
    per-flip-state occupancy map: the state's own frames are rarely
    contiguous in time (trials of other states fall in between), so the
    frame interval must come from the full chronological session
    (frame_interval_s / compute_occupancy) rather than being re-derived from
    this subset's own (gappy) timestamps.
    """
    occ_hist, _, _ = np.histogram2d(x, y, bins=[x_edges, y_edges])
    return occ_hist * time_per_frame_s


def compute_rate_map(spike_x, spike_y, occupancy_time, x_edges, y_edges, min_occupancy_s):
    """
    Firing rate map (Hz): spike count per bin / occupancy time per bin.
    Bins visited less than min_occupancy_s are set to NaN.
    """
    spike_hist, _, _ = np.histogram2d(spike_x, spike_y, bins=[x_edges, y_edges])
    rate_map = np.divide(
        spike_hist, occupancy_time,
        out=np.full_like(spike_hist, np.nan, dtype=float),
        where=occupancy_time >= min_occupancy_s
    )
    return rate_map, spike_hist


EPOCH_APPETITIVE, EPOCH_CONSUMMATORY, EPOCH_FEEDING = range(3)


def compute_epochs(reward_state, poke_left, poke_right, iti, frame_ms, gap_tolerance_s):
    """
    Behavioral-epoch state machine, walked chronologically over every row of
    the full event stream (not just tracked frames, so a transition isn't
    missed just because a frame got dropped for lacking position tracking):

      appetitive   -> consummatory   on reward_state's False->True edge (the
                      brief click/cue pulse marking the target found)
      consummatory -> feeding        on the next poke_left/poke_right
                      False->True edge
      feeding      -> appetitive     on the next iti False->True edge, then
                      pruned back wherever the animal wasn't actually near a
                      poke (see _prune_feeding_gaps)

    appetitive is both the default state and where the cycle returns to, so
    it covers the ITI and the search leading up to the next cue. reward_state
    itself is only true for about one frame (the cue pulse), not for the
    whole wait-for-poke window, so that window has to be tracked as an
    explicit state rather than read directly off the reward_state column.
    """
    reward_state = np.asarray(reward_state, dtype=bool)
    poke = np.asarray(poke_left, dtype=bool) | np.asarray(poke_right, dtype=bool)
    iti = np.asarray(iti, dtype=bool)
    frame_ms = np.asarray(frame_ms, dtype=float)

    n = len(reward_state)
    epoch = np.empty(n, dtype=np.int8)
    state = EPOCH_APPETITIVE
    prev_reward_state = prev_poke = prev_iti = False
    for i in range(n):
        rs, pk, it = reward_state[i], poke[i], iti[i]
        if state == EPOCH_APPETITIVE and rs and not prev_reward_state:
            state = EPOCH_CONSUMMATORY
        elif state == EPOCH_CONSUMMATORY and pk and not prev_poke:
            state = EPOCH_FEEDING
        elif state == EPOCH_FEEDING and it and not prev_iti:
            state = EPOCH_APPETITIVE
        epoch[i] = state
        prev_reward_state, prev_poke, prev_iti = rs, pk, it

    _prune_feeding_gaps(epoch, poke, frame_ms, gap_tolerance_s)
    return epoch


def _prune_feeding_gaps(epoch, poke, frame_ms, tolerance_s):
    """
    Reclassifies, back to appetitive (in place), any part of a feeding run
    that is more than `tolerance_s` away in time from the nearest poke pulse.

    A feeding bout is usually a tight burst of poke pulses every ~100-300ms
    (repeated licking) right at the reward port - but some bouts have long
    internal gaps, several seconds apart, where the animal has actually left
    the port and wandered elsewhere before poking again (confirmed against
    position data: those gaps line up with 1000px+ excursions across the
    arena, not a quick in-and-out). The original "first poke to ITI" window
    pulled those excursions' positions into the feeding place field; this
    keeps only the time actually spent near a poke, splitting one long run
    into several short ones wherever a gap exceeds tolerance.
    """
    tolerance_ms = tolerance_s * 1000.0
    is_feeding = epoch == EPOCH_FEEDING
    if not is_feeding.any():
        return

    diff = np.diff(is_feeding.astype(np.int8))
    starts = np.where(diff == 1)[0] + 1
    ends = np.where(diff == -1)[0] + 1  # exclusive
    if is_feeding[0]:
        starts = np.r_[0, starts]
    if is_feeding[-1]:
        ends = np.r_[ends, len(epoch)]

    for start, end in zip(starts, ends):
        seg_poke = poke[start:end]
        seg_t = frame_ms[start:end]
        poke_t = seg_t[seg_poke]
        if poke_t.size == 0:
            continue
        idx = np.clip(np.searchsorted(poke_t, seg_t), 1, len(poke_t) - 1)
        nearest_gap = np.minimum(seg_t - poke_t[idx - 1], poke_t[idx] - seg_t)
        far_offsets = np.where(nearest_gap > tolerance_ms)[0]
        if far_offsets.size:
            epoch[start + far_offsets] = EPOCH_APPETITIVE


def skaggs_si(rate_map_flat, p_i):
    """
    Vectorized Skaggs spatial information.

        SI = sum_i  p_i * (r_i / r_mean) * log2(r_i / r_mean)

    rate_map_flat : flattened rate map (Hz), NaN for unvisited bins
    p_i : flattened occupancy probability per bin (same shape, sums to 1)

    Returns SI in bits/spike, or 0.0 if the mean rate is zero.
    """
    valid = ~np.isnan(rate_map_flat)
    denom = np.sum(p_i[valid])
    if denom == 0:
        return 0.0
    r_mean = np.sum(rate_map_flat[valid] * p_i[valid]) / denom
    if r_mean == 0:
        return 0.0
    active = valid & (rate_map_flat > 0)
    ratio = rate_map_flat[active] / r_mean
    return float(np.sum(p_i[active] * ratio * np.log2(ratio)))


def upsample_rate_map(rate_map, factor=8, order=3):
    """
    Smooth zoom of a rate map for display. NaN regions stay NaN (a bin is
    considered valid in the output only if the upsampled mask is >= 0.5).
    """
    from scipy.ndimage import zoom

    valid_mask = ~np.isnan(rate_map.T)
    rate_filled = np.nan_to_num(rate_map.T, nan=0.0)
    rate_upsampled = zoom(rate_filled, factor, order=order)
    mask_upsampled = zoom(valid_mask.astype(float), factor, order=order)
    rate_upsampled[mask_upsampled < 0.5] = np.nan
    return rate_upsampled
