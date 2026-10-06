from pathlib import Path

# Root directory containing all session data.
DEFAULT_DATA_ROOT = Path('D:/data/cbm-odor')

# Subdirectories of the data root, mirrored by <animal>/<session>/.
BONSAI_SUBDIR = 'bonsai'  # unused directly (no video needed here) - kept for parity
EVENTS_SUBDIR = 'events'  # <data_root>/events/<animal>/<session>/events.csv
HC_SUBDIR = 'hc-ks'        # <data_root>/hc-ks/<animal>/<session>/ (hippocampus)
OB_SUBDIR = 'ob-ks'        # <data_root>/ob-ks/<animal>/<session>/ (olfactory bulb)

# Brain regions to load clusters from: (key, subdir, display label).
REGIONS = [
    ('hc', HC_SUBDIR, 'HC'),
    ('ob', OB_SUBDIR, 'OB'),
]

EVENTS_GLOB = 'events.csv'

# events.csv column prefix (<POSITION_POINT>_x/_y) used for place-field
# spatial binning - the sleap-tracked centroid, not Bonsai's real-time
# bonsai_centroid (that one's for cbm-viewer's video overlay instead).
POSITION_POINT = 'nose'

# events.csv column holding position timestamps, in the *ephys* clock -
# not 'bonsai_ts' (Bonsai's wall clock). spike_times.npy is recorded on the
# ephys/Kilosort sample clock, so alignment must go through this column.
TIMESTAMP_COLUMN = 'timestamp_ms'

# events.csv column holding each frame's trial-flip state (0/1/2) and the
# trial number it belongs to - used to split place fields by state below.
FLIP_STATE_COLUMN = 'flip_state'
TRIAL_NUMBER_COLUMN = 'trial_number'

# The trial-flip states to plot, in display order. flip_state is constant
# across a whole trial, so this splits the session's tracked frames (and
# each cluster's spikes) into up to three independent place fields.
FLIP_STATES = [0, 1, 2]

# events.csv columns used to derive the behavioral epoch (appetitive /
# consummatory / feeding) a frame falls in - see place_field.compute_epochs.
REWARD_STATE_COLUMN = 'reward_state'
POKE_LEFT_COLUMN = 'poke_left'
POKE_RIGHT_COLUMN = 'poke_right'
ITI_COLUMN = 'iti'

# Behavioral epochs to plot, in display order - index must match
# place_field.EPOCH_APPETITIVE/EPOCH_CONSUMMATORY/EPOCH_FEEDING.
EPOCHS = ['appetitive', 'consummatory', 'feeding']

# Any gap this long (seconds) or longer between poke pulses within a feeding
# bout ends feeding at the earlier pulse - see
# place_field.compute_epochs/_prune_feeding_gaps. The animal typically
# re-pokes every ~100-300ms while actively feeding (licking); a longer gap
# usually means it left the port and wandered elsewhere before poking again.
FEEDING_GAP_TOLERANCE_S = 0.5

# Kilosort spike_times.npy sample rate (Hz), for converting samples -> ms.
SAMPLING_RATE_HZ = 30000.0

# Clusters below this whole-session spike count are excluded before place
# fields are even computed (too few spikes for a meaningful rate map).
MIN_SPIKES = 250

# Cluster labels to include (from cluster_info.tsv's 'group', falling back
# to 'KSLabel' when a cluster hasn't been manually reviewed in phy).
# 'noise' is always excluded.
INCLUDE_LABELS = ('good', 'mua')

# Known physical arena extent (pixels), used as fixed spatial bin edges.
# Tracked positions occasionally jitter slightly outside this envelope
# (SLEAP noise near the arena walls), but bins should tile the actual
# arena rather than stretch to whatever the noisy tracked extent happens
# to be for a given session.
#
# The nominal arena is 888x1968, but the tracked nose rarely reaches the
# top/bottom wall - checked across 152 sessions, the Y margin is at least
# ~28px in 151 of them (median ~41px at the bottom, ~61px at the top; one
# outlier session comes within 6px). Y is cropped by a fixed amount on each
# side (25px bottom, 35px top) so the arena box is tight to where the animal
# actually goes, without making the box itself session-dependent - X already
# fills its own bounds to within ~5-24px, so it's left uncropped.
ARENA_X_RANGE_PX = (0, 888)
ARENA_Y_RANGE_PX = (25, 1933)

# Spatial bin size in pixels for occupancy/rate maps.
BIN_SIZE_PX = 153  # 129/2.54cm 50.7/cm

# Spatial bins visited less than this many seconds are excluded (NaN in the rate map).
MIN_OCCUPANCY_S = 0.1

# Zoom factor for the display-only upsampled/smoothed rate map.
UPSAMPLE_FACTOR = 8

# colorcet colormap used for rate-map panels (see colorcet.com for the full
# list of names, e.g. 'fire', 'bmy', 'kbc').
RATE_MAP_CMAP = 'fire'

# Trajectory & Spike Positions panel marker styling.
TRAJECTORY_COLOR = 'C0'
TRAJECTORY_MARKER_ALPHA = 0.1
SPIKE_COLOR = 'red'
SPIKE_MARKER_ALPHA = TRAJECTORY_MARKER_ALPHA  # matches the trajectory markers

# Spacing (pixels) between tick marks on every spatial Head-X/Head-Y panel -
# kept equal on both axes so distances read the same regardless of which
# axis you're looking at.
TICK_SPACING_PX = 250
