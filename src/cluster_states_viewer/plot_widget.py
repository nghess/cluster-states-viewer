"""Matplotlib-backed displays for one cluster's place field, as two tabs:

  PlaceFieldPlot       - scoped to the appetitive epoch only (search + ITI).
                         Top row: trajectory+spikes, occupancy, and rate map,
                         all appetitive-only. Bottom row: one rate map per
                         trial-flip state (0/1/2), also appetitive-only.
  EpochPlaceFieldPlot  - one column per behavioral epoch (appetitive/
                         consummatory/feeding): top row is that epoch's
                         trajectory+spike overlay, bottom row its rate map.

Every rate map (both tabs) shares the whole-session rate map's color scale,
so they're directly comparable to each other even across tabs."""
import colorcet as cc
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import MultipleLocator
from mpl_toolkits.axes_grid1 import make_axes_locatable
from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import config

# Fixed colorbar width/padding, used for every panel (real colorbar or not) -
# see _colorbar/_reserve_colorbar_space.
_COLORBAR_SIZE = '4%'
_COLORBAR_PAD = 0.08


def _colorbar(fig, ax, im, label):
    """Attaches a colorbar of a fixed width via make_axes_locatable, rather
    than fig.colorbar's own auto-sizing, so every subplot in a column
    reserves identical horizontal space - whether or not it actually has a
    colorbar. Otherwise an aspect-equal panel without one (e.g. a trajectory
    scatter) ends up wider than its column-mates and visually misaligned
    with them. Pair with _reserve_colorbar_space on panels with no image."""
    cax = make_axes_locatable(ax).append_axes('right', size=_COLORBAR_SIZE, pad=_COLORBAR_PAD)
    fig.colorbar(im, cax=cax, label=label)


def _reserve_colorbar_space(ax):
    """Reserves the same width a real colorbar would take (see _colorbar)
    for a panel that has none, so it still aligns with its column-mates."""
    cax = make_axes_locatable(ax).append_axes('right', size=_COLORBAR_SIZE, pad=_COLORBAR_PAD)
    cax.axis('off')


def _style_axes(ax, col, fontsize):
    """Column-based tick/label tidy-up, shared by every panel in both tabs'
    2x3 grids: numeric tick labels (both axes) only appear in column 0 -
    every column keeps its tick marks, just not the numbers - the y-axis
    label only appears in column 0, and the x-axis label only in column 1
    (all three panels share the same fixed arena bounds, so repeating the
    numbers/labels on every column is redundant)."""
    ax.xaxis.set_major_locator(MultipleLocator(config.TICK_SPACING_PX))
    ax.yaxis.set_major_locator(MultipleLocator(config.TICK_SPACING_PX))
    ax.tick_params(labelsize=fontsize - 1, labelleft=(col == 0), labelbottom=(col == 0))
    ax.set_ylabel('Head Y' if col == 0 else '', fontsize=fontsize)
    ax.set_xlabel('Head X' if col == 1 else '', fontsize=fontsize)


def _draw_trajectory(ax, x, y, spike_x, spike_y, extent, fontsize, title, col):
    ax.plot(x, y, 'o', ms=1, alpha=config.TRAJECTORY_MARKER_ALPHA, color=config.TRAJECTORY_COLOR)
    ax.scatter(spike_x, spike_y, s=2, color=config.SPIKE_COLOR,
               alpha=config.SPIKE_MARKER_ALPHA, zorder=2)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect('equal', adjustable='box')
    ax.set_title(title, fontsize=fontsize, pad=8)
    _style_axes(ax, col, fontsize)
    _reserve_colorbar_space(ax)


def _draw_rate_map(fig, ax, rate_map_upsampled, extent, fontsize, title, vmin, vmax, col):
    im = ax.imshow(rate_map_upsampled, origin='lower', aspect='equal',
                    cmap=cc.cm[config.RATE_MAP_CMAP], extent=extent, interpolation='bilinear',
                    vmin=vmin, vmax=vmax)
    ax.set_title(title, fontsize=fontsize, pad=8)
    _style_axes(ax, col, fontsize)
    _colorbar(fig, ax, im, 'Spikes/Sec')


class _PlaceFieldPlotBase(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvasQTAgg(self.figure)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        self._draw_placeholder()

    def _new_grid(self):
        # The figure is cleared and rebuilt from scratch on every redraw
        # (rather than reusing persistent Axes) because matplotlib's
        # colorbar keeps its own companion Axes tied to the image's Axes -
        # manually tracking/removing it across repeated clear()+imshow()
        # calls on reused Axes is fragile (breaks on the 2nd+ redraw).
        self.figure.clear()
        return GridSpec(2, 3, figure=self.figure, hspace=0.5, wspace=0.5)

    def _draw_placeholder(self):
        gs = self._new_grid()
        ax = self.figure.add_subplot(gs[:, :])
        ax.set_axis_off()
        ax.text(0.5, 0.5, "Select a cluster", ha='center', va='center',
                 transform=ax.transAxes, color='gray')
        self.canvas.draw_idle()

    def _draw_rows(self, fig, gs, session, cluster, extent, fontsize, vmin, vmax):
        raise NotImplementedError

    def set_cluster(self, session, cluster, title: str = ""):
        if cluster is None or cluster.spike_hist is None:
            self._draw_placeholder()
            return

        fontsize = 9
        extent = [session.x_edges[0], session.x_edges[-1],
                  session.y_edges[0], session.y_edges[-1]]
        gs = self._new_grid()
        fig = self.figure

        # Every rate map (both tabs) shares the whole-session map's scale,
        # even though that panel itself is no longer drawn anywhere.
        vmin, vmax = 0.0, np.nanmax(cluster.rate_map_upsampled)
        self._draw_rows(fig, gs, session, cluster, extent, fontsize, vmin, vmax)

        if title:
            fig.suptitle(title, fontsize=13, fontweight='bold')
        self.canvas.draw_idle()


class PlaceFieldPlot(_PlaceFieldPlotBase):
    """Scoped to the appetitive epoch: top row is that epoch's pooled
    trajectory/occupancy/rate map, bottom row one rate map per flip state
    (also appetitive-only - see ClusterSessionData/PlaceFieldWorker)."""

    def _draw_rows(self, fig, gs, session, cluster, extent, fontsize, vmin, vmax):
        ax0 = fig.add_subplot(gs[0, 0])
        _draw_trajectory(ax0, session.x[session.appetitive_mask], session.y[session.appetitive_mask],
                          cluster.epoch_spike_x.get(0), cluster.epoch_spike_y.get(0),
                          extent, fontsize, 'Trajectory & Spike Positions (Appetitive)', col=0)

        ax1 = fig.add_subplot(gs[0, 1])
        im1 = ax1.imshow(session.appetitive_occupancy_time.T, origin='lower', aspect='equal',
                          cmap='viridis', extent=extent)
        ax1.set_title('Occupancy Histogram (Appetitive)', fontsize=fontsize, pad=8)
        _style_axes(ax1, col=1, fontsize=fontsize)
        _colorbar(fig, ax1, im1, 'Seconds')

        ax2 = fig.add_subplot(gs[0, 2])
        _draw_rate_map(fig, ax2, cluster.appetitive_rate_map_upsampled, extent, fontsize,
                        'Appetitive Rate Map', vmin, vmax, col=2)

        for col, state in enumerate(config.FLIP_STATES):
            stats = session.flip_state_stats[state]
            ax = fig.add_subplot(gs[1, col])
            _draw_rate_map(fig, ax, cluster.rate_maps_upsampled.get(state), extent, fontsize,
                            f'Flip State {state}\n{stats.duration_s:.1f}s, {stats.n_trials} trials',
                            vmin, vmax, col=col)


class EpochPlaceFieldPlot(_PlaceFieldPlotBase):
    """One column per behavioral epoch: top row that epoch's trajectory+spike
    overlay, bottom row its rate map."""

    def _draw_rows(self, fig, gs, session, cluster, extent, fontsize, vmin, vmax):
        for col, epoch_name in enumerate(config.EPOCHS):
            mask = session.epoch == col
            ax_top = fig.add_subplot(gs[0, col])
            _draw_trajectory(ax_top, session.x[mask], session.y[mask],
                              cluster.epoch_spike_x.get(col), cluster.epoch_spike_y.get(col),
                              extent, fontsize, f'{epoch_name.capitalize()}\nTrajectory & Spike Positions', col=col)

            stats = session.epoch_stats[col]
            ax_bottom = fig.add_subplot(gs[1, col])
            _draw_rate_map(fig, ax_bottom, cluster.epoch_rate_maps_upsampled.get(col), extent, fontsize,
                            f'{epoch_name.capitalize()}\n{stats.duration_s:.1f}s, {stats.n_trials} trials',
                            vmin, vmax, col=col)
