"""Live split-screen dashboard.

Two panels, driven by one :class:`~flysim.runner.SimulationRunner`:

* **Panel A - Spatial view.** The arena: the fly, the stalking predator, their trails, a
  threat halo whose opacity tracks the instantaneous looming drive, and the escape vector
  once the Giant Fiber fires.
* **Panel B - Neural telemetry.** A scrolling spike raster over scrolling membrane
  potential traces, so a spike and the voltage that produced it line up vertically.

The point of putting them side by side is causal: you watch the looming drive climb, watch
LC4 start firing, watch that propagate through the premotor pool to the Giant Fiber, and
then watch the fly leave. The escape vector in Panel A is drawn in the same colour as the
GF trace in Panel B because they are the same event.

Colour
------
Three categorical series (LC4, PMN, GF) drawn from validated palette slots 1-3, which
clear colour-vision-deficiency and normal-vision separation on all pairs against this
surface. Inhibition is deliberately *not* a fourth categorical series - it is context, so
it is drawn in recessive muted ink. Every trace also carries a distinct dash pattern, so
identity never depends on colour alone; the aqua PMN trace sits just below 3:1 contrast on
this surface, which the legend and dash pattern relieve.

This module may import from anywhere. Nothing may import it - that one-way rule is what
keeps the simulation runnable headless.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from flysim.config import SimConfig
from flysim.runner import SimulationRunner

# --- Palette ---------------------------------------------------------------------
# Categorical slots 1-3 (blue / orange / aqua) plus chrome ink. See the module docstring.
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

C_LC4 = "#2a78d6"   # slot 1, blue   - sensory input
C_GF = "#eb6834"    # slot 2, orange - the escape command
C_PMN = "#1baf7a"   # slot 3, aqua   - premotor relay
C_INH = INK_MUTED   # context, not a series
C_THREAT = "#d03b3b"  # status:critical - the predator, always paired with a label

# Per-population style: colour, dash pattern, line width, display name.
SERIES_STYLE: dict[str, tuple[str, object, float, str]] = {
    "LC4": (C_LC4, "solid", 2.0, "LC4 (visual)"),
    "PMN": (C_PMN, (0, (6, 2)), 2.0, "PMN (premotor)"),
    "INH": (C_INH, (0, (1, 2)), 1.4, "INH (inhibition)"),
    "GF": (C_GF, "solid", 2.6, "GF (giant fiber)"),
    # Only present on a CNS dataset, where the Giant Fiber actually reaches muscle.
    "MOTOR": ("#4a3aa7", (0, (3, 1, 1, 1)), 2.2, "MOTOR (muscle)"),
}

# Frames to hold on screen after the episode ends, so the final state is readable.
HOLD_FRAMES = 30

# The brain view is a FIXED front-on projection of the real 3-D coordinates.
#
# It used to rock gently for parallax. That cost 74 ms per frame -- more than four times
# the entire rest of the dashboard -- because any change of viewing angle moves every
# point, forcing Matplotlib to rebuild the geometry of a 46,000-point scatter on every
# frame. Holding the angle still lets the projection, the depth sort and the anatomical
# backdrop all be computed exactly once, leaving only per-neuron colour and size to update.
#
# Nothing is lost analytically: the front view is the one that shows both optic lobes and
# the Giant Fibers between them, which is the view worth looking at.
BRAIN_VIEW_YAW_RAD = 0.22   # slight turn off dead-on, so the volume reads as 3-D

# Cap on how many *sub-threshold* neurons the brain view draws.
#
# Matplotlib renders a scatter with per-point sizes as one path per point, so the cost is
# linear in point count: 15,452 of them cost ~64 ms per frame, four times the whole rest
# of the dashboard. The blue cloud is a density backdrop, so a representative sample
# conveys exactly the same thing.
#
# Spiking neurons are NEVER subsampled -- they are the signal, they are drawn from the
# full population in a separate overlay, and there are only ever a few hundred at once.
BRAIN_CLOUD_MAX_POINTS = 4000


class Dashboard:
    """Renders a :class:`SimulationRunner` as a live two-panel figure."""

    def __init__(
        self,
        runner: SimulationRunner,
        config: SimConfig,
        steps_per_frame: int = 1,
        show_brain: bool = True,
    ) -> None:
        self.runner = runner
        self.config = config
        self.steps_per_frame = max(int(steps_per_frame), 1)
        self._want_brain = show_brain
        self._done = False
        self._hold = 0
        self._last_result = runner.reset()

        # Duck-typed rather than isinstance-checked, so any environment that accepts a
        # pointer position gets the controls without this module importing it.
        self._interactive = hasattr(runner.env, "set_threat_position")

        self._build_figure()
        if self._interactive:
            self._connect_events()

    # ------------------------------------------------------------------
    # Figure construction
    # ------------------------------------------------------------------

    def _build_figure(self) -> None:
        plt.rcParams.update(
            {
                "figure.facecolor": PAGE,
                "axes.facecolor": SURFACE,
                "axes.edgecolor": BASELINE,
                "axes.labelcolor": INK_SECONDARY,
                "text.color": INK,
                "xtick.color": INK_MUTED,
                "ytick.color": INK_MUTED,
                "grid.color": GRIDLINE,
                "font.size": 9,
            }
        )

        self.fig = plt.figure(figsize=(16.0, 8.6))
        # The panel roughly triples frame cost on a 15k-neuron connectome (Matplotlib
        # draws one path per point), so it is worth being able to turn off.
        self._has_brain_view = self._want_brain and getattr(
            self.runner.brain.connectome, "positions", None
        ) is not None

        if self._has_brain_view:
            gs = self.fig.add_gridspec(
                2, 2, width_ratios=[1.05, 1.15], height_ratios=[1.0, 1.05],
                left=0.04, right=0.98, top=0.89, bottom=0.075,
                wspace=0.13, hspace=0.24,
            )
            self.ax_space = self.fig.add_subplot(gs[0, 0])
            self.ax_brain = self.fig.add_subplot(gs[1, 0])
            right = gs[:, 1].subgridspec(2, 1, height_ratios=[1.0, 3.4], hspace=0.06)
            self.ax_raster = self.fig.add_subplot(right[0])
            self.ax_volt = self.fig.add_subplot(right[1], sharex=self.ax_raster)
        else:
            gs = self.fig.add_gridspec(
                2, 2, width_ratios=[1.0, 1.3], height_ratios=[1.0, 3.4],
                left=0.05, right=0.975, top=0.90, bottom=0.09,
                wspace=0.16, hspace=0.06,
            )
            self.ax_space = self.fig.add_subplot(gs[:, 0])
            self.ax_brain = None
            self.ax_raster = self.fig.add_subplot(gs[0, 1])
            self.ax_volt = self.fig.add_subplot(gs[1, 1], sharex=self.ax_raster)

        self.fig.suptitle(
            "Drosophila looming-escape reflex  ·  LC4 → premotor → Giant Fiber",
            fontsize=13, fontweight="bold", color=INK, x=0.05, ha="left", y=0.965,
        )
        self.fig.text(
            0.05, 0.925,
            f"connectome: {self.runner.brain.connectome.name}   ·   "
            f"{self.runner.brain.size} neurons   ·   "
            f"brain dt {self.config.runner.brain_dt_ms} ms",
            fontsize=8.5, color=INK_MUTED, ha="left",
        )

        self._build_spatial_panel()
        if self._has_brain_view:
            self._build_brain_panel()
        self._build_telemetry_panels()
        self._collect_animated()

    def _collect_animated(self) -> None:
        """Every artist whose contents change between frames.

        Blitting redraws only these, reusing a cached rasterisation of everything else
        (axes, ticks, labels, legends, titles). Anything that changes but is missing from
        this list will appear frozen, so it is built explicitly rather than by scanning
        the axes.
        """
        self._animated: list = [
            self._halo, self._pred_trail, self._fly_trail,
            self._pred_dot, self._fly_dot,
            self._escape_vec, self._escape_head, self._status,
            *self._raster_lines.values(),
            *self._mean_lines.values(),
            *self._gf_marks,
        ]
        for low, high in self._band_lines.values():
            self._animated.extend((low, high))
        if self._has_brain_view:
            # The backdrop is static and lives in the cached blit background.
            self._animated.extend(
                [self._brain_cloud, self._brain_fired, self._brain_gf]
            )

    def _build_spatial_panel(self) -> None:
        ax = self.ax_space
        bounds = self.runner.env.bounds
        ax.set_xlim(bounds[0, 0], bounds[0, 1])
        ax.set_ylim(bounds[1, 0], bounds[1, 1])
        ax.set_aspect("equal")
        ax.set_title("A  ·  Spatial view", loc="left", fontsize=10.5,
                     fontweight="bold", color=INK, pad=8)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        ax.grid(True, linewidth=0.6, alpha=0.9)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

        # Threat halo: radius fixed, opacity tracks the looming drive. Encoding the drive
        # as opacity rather than radius keeps the predator's true size honest.
        self._halo = Circle((0, 0), 0.055, facecolor=C_THREAT, alpha=0.0,
                            edgecolor="none", zorder=2)
        ax.add_patch(self._halo)

        (self._pred_trail,) = ax.plot([], [], color=C_THREAT, lw=1.5, alpha=0.5, zorder=3)
        (self._fly_trail,) = ax.plot([], [], color=INK, lw=1.5, alpha=0.45, zorder=4)

        # 2px surface ring on the markers so they stay legible where the trails overlap.
        (self._pred_dot,) = ax.plot(
            [], [], marker="X", markersize=13, color=C_THREAT, linestyle="none",
            markeredgecolor=SURFACE, markeredgewidth=2.0, zorder=6,
        )
        (self._fly_dot,) = ax.plot(
            [], [], marker="o", markersize=10, color=INK, linestyle="none",
            markeredgecolor=SURFACE, markeredgewidth=2.0, zorder=7,
        )
        # Escape vector, in the GF colour: the same event as the orange spike in Panel B.
        (self._escape_vec,) = ax.plot(
            [], [], color=C_GF, lw=2.6, solid_capstyle="round", zorder=8,
        )
        (self._escape_head,) = ax.plot(
            [], [], marker="^", markersize=9, color=C_GF, linestyle="none", zorder=8,
        )

        ax.legend(
            handles=[
                Line2D([], [], marker="o", color=INK, linestyle="none",
                       markersize=8, label="fly"),
                Line2D([], [], marker="X", color=C_THREAT, linestyle="none",
                       markersize=9, label="predator"),
                Line2D([], [], color=C_GF, lw=2.4, label="escape vector"),
            ],
            loc="upper right", frameon=False, fontsize=8.5, labelcolor=INK_SECONDARY,
            handletextpad=0.6, borderpad=0.2,
        )

        self._status = ax.text(
            0.025, 0.025, "", transform=ax.transAxes, va="bottom", ha="left",
            fontsize=9, color=INK_SECONDARY, linespacing=1.55,
            bbox=dict(boxstyle="round,pad=0.45", facecolor=SURFACE,
                      edgecolor=GRIDLINE, linewidth=1.0),
        )

    def _build_brain_panel(self) -> None:
        """Panel C: the network drawn where it physically sits in the brain.

        A NumPy-projected point cloud rather than a Matplotlib 3-D axes. Real 3-D would
        depth-sort thousands of points in Python on every frame; projecting with a 3x3
        rotation matrix and drawing a flat scatter costs almost nothing, and with slow
        auto-rotation it still reads as a volume.
        """
        ax = self.ax_brain
        connectome = self.runner.brain.connectome
        positions = np.asarray(connectome.positions, dtype=np.float64)

        # Centre on the anatomical backdrop when there is one, so the model sits in its
        # true place inside the brain rather than being recentred on its own centroid.
        context = getattr(connectome, "context_positions", None)
        reference = np.asarray(context) if context is not None else positions
        origin = np.nanmedian(reference, axis=0)

        self._brain_xyz = positions - origin
        self._brain_has_pos = np.isfinite(self._brain_xyz[:, 0])
        self._brain_context_xyz = (
            np.asarray(context, dtype=np.float64) - origin if context is not None else None
        )
        # Which axis goes up the screen depends on what the dataset covers. A brain
        # volume is widest left-to-right and the conventional view is face-on, so y is
        # vertical. A whole CNS additionally spans the body axis from brain down to nerve
        # cord -- and that axis is the entire point, since it is what separates the Giant
        # Fiber from the motor neurons it drives. Choosing it by extent rather than
        # hard-coding keeps both correct: FlyWire's brain spans y 380 um against z 277,
        # while the male CNS spans z 120 against y 61.
        spans = np.nanmax(self._brain_xyz, axis=0) - np.nanmin(self._brain_xyz, axis=0)
        self._brain_vertical = 2 if spans[2] > spans[1] else 1
        depth_axis = 1 if self._brain_vertical == 2 else 2

        cos_a, sin_a = np.cos(BRAIN_VIEW_YAW_RAD), np.sin(BRAIN_VIEW_YAW_RAD)
        self._brain_px = (
            self._brain_xyz[:, 0] * cos_a + self._brain_xyz[:, depth_axis] * sin_a
        )
        self._brain_py = self._brain_xyz[:, self._brain_vertical]
        self._brain_depth = (
            -self._brain_xyz[:, 0] * sin_a + self._brain_xyz[:, depth_axis] * cos_a
        )

        measured = "flywire" in connectome.name or "neuprint" in connectome.name
        source = "measured coordinates" if measured else "schematic layout"
        ax.set_title(f"C  ·  Brain view  ({source})", loc="left", fontsize=10.5,
                     fontweight="bold", color=INK, pad=8)
        self._brain_subsampled = False

        # Bound the view over a FULL revolution, not just the current pose. Yaw mixes x
        # and z into the horizontal screen axis, so the widest the cloud can ever appear
        # is its maximum radius in the xz-plane; y is unaffected by yaw. Sizing from
        # max(|x|,|y|,|z|) instead leaves the cloud small and drifting off-centre as it
        # turns, which is what the first attempt did.
        extent = self._brain_xyz[self._brain_has_pos]
        if self._brain_context_xyz is not None:
            extent = np.vstack([extent, self._brain_context_xyz])
        # Horizontal extent of the fixed projection.
        depth_axis = 1 if self._brain_vertical == 2 else 2
        projected_x = np.abs(
            extent[:, 0] * np.cos(BRAIN_VIEW_YAW_RAD)
            + extent[:, depth_axis] * np.sin(BRAIN_VIEW_YAW_RAD)
        )
        horizontal = float(np.percentile(projected_x, 99.5))
        vertical = float(np.percentile(np.abs(extent[:, self._brain_vertical]), 99.5))
        radius = max(horizontal, vertical) * 1.08
        ax.set_xlim(-radius, radius)
        ax.set_ylim(radius, -radius)   # inverted: dorsal up, matching anatomical figures
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_color(GRIDLINE)

        # Sized to be readable rather than minimal: at s=0.5 a 31,000-point cloud
        # renders only its dense core and the brain outline disappears entirely.
        if self._brain_context_xyz is not None:
            ctx = self._brain_context_xyz
            ax.scatter(
                ctx[:, 0] * cos_a + ctx[:, 2] * sin_a, ctx[:, 1],
                s=1.6, color=BASELINE, alpha=0.7, linewidths=0, zorder=1,
            )

        # Three layers, drawn back to front: the resting population, the depolarising
        # ones, and the spikes. Separate collections rather than one, so the sizes and
        # colours of each can be set independently without re-sorting everything.
        # Painter's algorithm applied once: far neurons first so near ones land on top.
        visible = np.flatnonzero(self._brain_has_pos)
        if visible.size > BRAIN_CLOUD_MAX_POINTS:
            step = visible.size // BRAIN_CLOUD_MAX_POINTS + 1
            visible = visible[::step]
        self._brain_order = visible[np.argsort(self._brain_depth[visible])]
        self._brain_cloud = ax.scatter(
            self._brain_px[self._brain_order], self._brain_py[self._brain_order],
            s=4.0, c=np.zeros(self._brain_order.size), cmap="Blues",
            vmin=0.0, vmax=1.0, linewidths=0, zorder=3,
        )
        self._brain_subsampled = visible.size < int(self._brain_has_pos.sum())
        self._brain_fired = ax.scatter(
            [], [], s=22.0, color=C_GF, linewidths=0, zorder=5,
        )
        self._brain_gf = ax.scatter(
            [], [], s=210.0, marker="*", facecolor="none",
            edgecolors=C_GF, linewidths=1.7, zorder=7,
        )

        ax.text(0.5, -0.045,
                ("faint = rest of brain (not simulated)   ·   blue = depolarising"
                 + (f" ({BRAIN_CLOUD_MAX_POINTS:,} shown)" if self._brain_subsampled else "")
                 + "   ·   orange = spiking (all)   ·   ☆ = Giant Fiber"),
                transform=ax.transAxes, ha="center", va="top",
                fontsize=8, color=INK_MUTED)

    def _draw_brain(self) -> None:
        """Recolour the point cloud for this frame.

        Positions, depth order and the anatomical backdrop are all fixed, so the only
        per-frame work is the activation colour, the point sizes, and the handful of
        neurons that spiked. That is what keeps a 46,000-point panel affordable.
        """
        result = self._last_result
        spikes = result.frame_spikes
        if spikes is None:
            spikes = result.state.spikes

        # Depolarisation, 0 at rest and 1 at threshold. Uses the per-neuron threshold, so
        # a connectome with heterogeneous thresholds still normalises correctly.
        rest = self.config.neuron.v_rest_mv
        threshold = np.asarray(self.runner.brain.v_threshold)
        activation = np.clip(
            (result.state.voltages - rest) / np.maximum(threshold - rest, 1e-6), 0, 1
        )

        ordered = activation[self._brain_order]
        self._brain_cloud.set_array(ordered)
        # Depolarised cells grow as well as darken, so the cue survives colour-vision
        # deficiency and the small point size.
        self._brain_cloud.set_sizes(3.5 + 30.0 * ordered)

        fired = np.flatnonzero(self._brain_has_pos & spikes)
        self._brain_fired.set_offsets(
            np.column_stack([self._brain_px[fired], self._brain_py[fired]])
            if fired.size else np.empty((0, 2))
        )

        gf = np.asarray(self.runner.brain.populations.get("GF", []), dtype=np.int64)
        gf = gf[self._brain_has_pos[gf]] if gf.size else gf
        if gf.size:
            self._brain_gf.set_offsets(
                np.column_stack([self._brain_px[gf], self._brain_py[gf]])
            )
            self._brain_gf.set_facecolor(C_GF if spikes[gf].any() else "none")

    def _build_telemetry_panels(self) -> None:
        tracked = self.runner.tracked

        # --- Raster (top) -------------------------------------------------------
        ax = self.ax_raster
        ax.set_title("B  ·  Neural telemetry", loc="left", fontsize=10.5,
                     fontweight="bold", color=INK, pad=8)
        ax.set_ylim(-0.6, len(tracked) - 0.4)
        ax.set_yticks(range(len(tracked)))
        ax.set_yticklabels(list(tracked), fontsize=8.5, color=INK_SECONDARY)
        ax.tick_params(labelbottom=False, length=0)
        ax.grid(False)
        for spine in ("top", "right", "bottom"):
            ax.spines[spine].set_visible(False)
        ax.text(1.0, 1.06, "spikes", transform=ax.transAxes, ha="right",
                fontsize=8, color=INK_MUTED)

        self._raster_lines: dict[str, Line2D] = {}
        self._raster_row: dict[str, int] = {}
        for row, pop in enumerate(tracked):
            colour = SERIES_STYLE[pop][0]
            (line,) = ax.plot([], [], marker="|", markersize=9, markeredgewidth=1.6,
                              linestyle="none", color=colour)
            self._raster_lines[pop] = line
            self._raster_row[pop] = row

        # --- Voltage (bottom) ---------------------------------------------------
        ax = self.ax_volt
        ax.set_ylim(-66.0, -36.0)

        # Fixed x-axis, showing time RELATIVE to now. This is a performance decision, not
        # a cosmetic one. A scrolling absolute-time axis changes its limits every frame,
        # which makes Matplotlib recompute tick locations and re-lay out every tick label,
        # axis label, title and legend in the figure -- measured at 141 ms per frame, or
        # 95% of the total, while the actual data is only ~1,500 points. Holding the
        # limits still costs nothing to read (the newest sample is always at 0 on the
        # right) and additionally makes blitting valid, since a cached axes background is
        # only reusable when the axes do not move.
        ax.set_xlim(-self.config.viz.window_ms, 0.0)
        ax.set_xlabel("time before now (ms)")
        ax.set_ylabel("membrane potential (mV)")
        ax.grid(True, linewidth=0.6, alpha=0.9)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

        # Threshold references. Two values because the GF is deliberately harder to
        # drive than the neurons feeding it.
        ax.axhline(self.config.neuron.v_threshold_mv, color=BASELINE, lw=1.0,
                   linestyle=(0, (4, 3)), zorder=1)
        ax.text(0.995, self.config.neuron.v_threshold_mv + 0.4, "threshold",
                transform=ax.get_yaxis_transform(), ha="right", va="bottom",
                fontsize=7.5, color=INK_MUTED)

        gf_threshold = float(
            self.runner.brain.v_threshold[self.runner.brain.populations["GF"]][0]
        )
        ax.axhline(gf_threshold, color=C_GF, lw=1.0, linestyle=(0, (4, 3)),
                   alpha=0.55, zorder=1)
        ax.text(0.995, gf_threshold + 0.4, "GF threshold",
                transform=ax.get_yaxis_transform(), ha="right", va="bottom",
                fontsize=7.5, color=C_GF)

        self._mean_lines: dict[str, Line2D] = {}
        self._band_lines: dict[str, tuple[Line2D, Line2D]] = {}
        handles: list[Line2D] = []
        for pop in tracked:
            colour, dashes, width, label = SERIES_STYLE[pop]
            (mean_line,) = ax.plot([], [], color=colour, lw=width, linestyle=dashes,
                                   solid_capstyle="round", zorder=5)
            self._mean_lines[pop] = mean_line
            handles.append(Line2D([], [], color=colour, lw=width, linestyle=dashes,
                                  label=label))

            # Population spread, drawn only where there is a population to spread.
            if len(self.runner.brain.populations[pop]) > 1:
                (lo,) = ax.plot([], [], color=colour, lw=0.7, alpha=0.18, zorder=4)
                (hi,) = ax.plot([], [], color=colour, lw=0.7, alpha=0.18, zorder=4)
                self._band_lines[pop] = (lo, hi)

        # Legend carries identity in dark ink beside a coloured sample, which is what
        # relieves the sub-3:1 contrast of the aqua trace.
        ax.legend(handles=handles, loc="upper left", ncol=4, frameon=False,
                  fontsize=8.5, labelcolor=INK_SECONDARY, columnspacing=1.4,
                  handletextpad=0.6, borderpad=0.2)

        # Marker for the GF spike, drawn across both telemetry panels once it happens.
        self._gf_marks = [
            self.ax_raster.axvline(0, color=C_GF, lw=1.4, linestyle=(0, (2, 2)),
                                   alpha=0.0, zorder=2),
            self.ax_volt.axvline(0, color=C_GF, lw=1.4, linestyle=(0, (2, 2)),
                                 alpha=0.0, zorder=2),
        ]

    # ------------------------------------------------------------------
    # Interactive controls
    # ------------------------------------------------------------------

    def _connect_events(self) -> None:
        """Route mouse and keyboard input to the environment.

        Note what is *not* here: any path from user input to the brain. Input reaches the
        environment, the environment produces an observation, and the encoder turns that
        into current exactly as it does for a scripted predator. The neurons cannot tell
        that a human is driving.
        """
        canvas = self.fig.canvas
        canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        canvas.mpl_connect("scroll_event", self._on_scroll)
        canvas.mpl_connect("key_press_event", self._on_key)

    def _on_mouse_move(self, event) -> None:
        # xdata/ydata are None whenever the pointer is outside the axes; moving away
        # should leave the threat where it was rather than snapping it to the origin.
        if event.inaxes is self.ax_space and event.xdata is not None:
            self.runner.env.set_threat_position(float(event.xdata), float(event.ydata))

    def _on_scroll(self, event) -> None:
        if event.inaxes is self.ax_space:
            self.runner.env.scale_threat(int(event.step))

    def _on_key(self, event) -> None:
        if event.key == "r":
            self.runner.env.reset_agent()

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def _update(self, _frame: int):
        if not self._done:
            # Several simulation frames per rendered frame, so simulated time keeps up
            # with wall-clock time. At one env frame per render the world advances 4 ms
            # per frame, which even at 60 fps is a quarter-speed slow motion — a fly
            # walking 18 mm/s then appears to move about 4 mm per real second and reads
            # as frozen.
            for _ in range(self.steps_per_frame):
                self._last_result = self.runner.step()
                if self._last_result.done:
                    self._done = True
                    break
        elif self._hold < HOLD_FRAMES:
            self._hold += 1

        self._draw_spatial()
        if self._has_brain_view:
            self._draw_brain()
        self._draw_telemetry()
        return self._animated

    def _draw_spatial(self) -> None:
        result = self._last_result
        obs = result.observation
        trail = self.config.viz.trail_frames

        fly_hist, pred_hist = self._trail_history(trail)
        self._fly_trail.set_data(fly_hist[:, 0], fly_hist[:, 1])
        self._pred_trail.set_data(pred_hist[:, 0], pred_hist[:, 1])

        self._fly_dot.set_data([obs.agent_position[0]], [obs.agent_position[1]])
        self._pred_dot.set_data([obs.threat_position[0]], [obs.threat_position[1]])

        drive = float(result.packet.raw.get("drive_pa", 0.0))
        self._halo.center = (obs.threat_position[0], obs.threat_position[1])
        # Radius tracks the object's true physical size, so the scroll wheel visibly
        # changes it, with a floor so the default 2 cm threat is still findable on screen.
        self._halo.set_radius(max(obs.threat_size, 0.025) * 1.6)
        self._halo.set_alpha(
            float(np.clip(drive / self.config.encoder.max_current_pa, 0.0, 1.0)) * 0.55
        )

        # Draw the escape vector from the fly's *actual* velocity rather than from the
        # motor command. The command is a brief pulse (a 20 ms window around the GF
        # spike) and is gone within a couple of frames, whereas the flight it caused
        # lasts hundreds of milliseconds — the velocity is what the viewer needs to see.
        # Its length tracks speed, so the arrow visibly decays as the fly slows.
        speed = float(np.linalg.norm(obs.agent_velocity))
        if obs.escaped and speed > 1e-6:
            start = np.asarray(obs.agent_position, dtype=float)
            tip = start + np.asarray(obs.agent_velocity, dtype=float) * 0.11
            self._escape_vec.set_data([start[0], tip[0]], [start[1], tip[1]])
            self._escape_head.set_data([tip[0]], [tip[1]])
        else:
            self._escape_vec.set_data([], [])
            self._escape_head.set_data([], [])

        gf_ms = self.runner.decoder.gf_spike_time_ms
        if gf_ms is None:
            gf_line = "GF: silent"
        else:
            gf_line = f"GF: FIRED at {gf_ms:6.1f} ms"

        if self._interactive:
            takeoffs = int(obs.raw.get("takeoffs", 0))
            self._status.set_text(
                f"t          {obs.t:5.3f} s\n"
                f"distance   {obs.distance * 1000:6.1f} mm\n"
                f"object     {obs.threat_size * 1000:6.1f} mm  (scroll to resize)\n"
                f"closing    {obs.closing_speed:6.2f} m/s\n"
                f"loom drive {drive:6.1f} pA\n"
                f"{gf_line}\n"
                f"escapes    {takeoffs}\n"
                f"\nmove mouse = threat   ·   r = reset fly"
            )
        else:
            outcome = self.runner.outcome().replace("_", " ")
            self._status.set_text(
                f"t          {obs.t:5.3f} s\n"
                f"distance   {obs.distance * 1000:6.1f} mm\n"
                f"loom drive {drive:6.1f} pA\n"
                f"{gf_line}\n"
                f"outcome:   {outcome}"
            )

    def _trail_history(self, length: int) -> tuple[np.ndarray, np.ndarray]:
        """Accumulate position history for the trails."""
        if not hasattr(self, "_fly_hist"):
            self._fly_hist: list[np.ndarray] = []
            self._pred_hist: list[np.ndarray] = []
        obs = self._last_result.observation
        self._fly_hist.append(np.asarray(obs.agent_position, dtype=float))
        self._pred_hist.append(np.asarray(obs.threat_position, dtype=float))
        return (
            np.asarray(self._fly_hist[-length:]),
            np.asarray(self._pred_hist[-length:]),
        )

    def _draw_telemetry(self) -> None:
        telemetry = self.runner.telemetry
        if not telemetry.t_ms:
            return

        now = telemetry.t_ms[-1]
        width = self.config.viz.window_ms
        window = telemetry.window(now, width)
        times = np.asarray(telemetry.t_ms[window])
        if times.size == 0:
            return

        # Everything is plotted relative to the newest sample, which sits at x = 0.
        relative = times - now

        for pop, line in self._mean_lines.items():
            line.set_data(relative, np.asarray(telemetry.mean[pop][window]))
            band = self._band_lines.get(pop)
            if band is not None:
                band[0].set_data(relative, np.asarray(telemetry.low[pop][window]))
                band[1].set_data(relative, np.asarray(telemetry.high[pop][window]))

        left = now - width
        for pop, line in self._raster_lines.items():
            spikes = np.asarray(telemetry.spike_times[pop])
            if spikes.size:
                spikes = spikes[spikes >= left] - now
            line.set_data(spikes, np.full(spikes.size, self._raster_row[pop]))

        gf_ms = self.runner.decoder.gf_spike_time_ms
        if gf_ms is not None and gf_ms >= left:
            offset = gf_ms - now
            for mark in self._gf_marks:
                mark.set_xdata([offset, offset])
                mark.set_alpha(0.8)
        else:
            for mark in self._gf_marks:
                mark.set_alpha(0.0)

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def run(self, save_path: str | None = None, show: bool = True) -> None:
        """Animate the simulation, optionally writing it to a file."""
        # An interactive session has no natural length -- it runs until the window closes.
        if self._interactive:
            if save_path:
                raise ValueError(
                    "Cannot --save an interactive session: it has no end. Record the "
                    "window with a screen recorder, or drop --interactive."
                )
            frames: object = itertools.count()
        else:
            frames = range(
                self.runner._default_frame_limit() // self.steps_per_frame + HOLD_FRAMES
            )

        # Blitting is valid because every axes now has fixed limits (the telemetry panel
        # plots time relative to now). Without it, Matplotlib re-lays out and re-rasterises
        # all ~87 text objects in the figure every frame: measured at 141 ms per frame,
        # against ~2-7 ms for the simulation itself.
        #
        # Saving to a file goes through writers that do not support blitting, so that path
        # keeps a full redraw. It is offline, so its cost does not matter.
        self._anim = FuncAnimation(
            self.fig,
            self._update,
            frames=frames,
            interval=self.config.viz.interval_ms,
            blit=not save_path,
            repeat=False,
            cache_frame_data=False,
        )

        if save_path:
            self._save(save_path)
        if show:
            plt.show()
        elif not save_path:
            plt.close(self.fig)

    def _save(self, save_path: str) -> None:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fps = max(int(round(1000 / self.config.viz.interval_ms)), 1)

        if path.suffix.lower() == ".gif":
            writer: object = PillowWriter(fps=fps)
        else:
            try:
                writer = FFMpegWriter(fps=fps, bitrate=2400)
                # Instantiating does not prove ffmpeg exists; matplotlib only discovers
                # that when it tries to spawn it. Check before committing to the format.
                if not FFMpegWriter.isAvailable():
                    raise RuntimeError
            except (RuntimeError, FileNotFoundError):
                path = path.with_suffix(".gif")
                writer = PillowWriter(fps=fps)
                print(
                    "ffmpeg not found on PATH; falling back to GIF. "
                    f"Writing {path} instead."
                )

        print(f"Rendering {path} ...")
        self._anim.save(str(path), writer=writer, dpi=110)
        print(f"Saved {path}")
