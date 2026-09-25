"""Plotly mesh helpers for volumetric three-dimensional phase trajectories."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import plotly.graph_objects as go


BACKGROUND_COLOR = "#ffffff"
PRIMARY_TEXT_COLOR = "#172033"
SECONDARY_TEXT_COLOR = "#536176"
START_ANCHOR_COLOR = "#c7783f"
TUBE_SIDES = 12
STANDARD_TUBE_RADIUS = 0.022
KNOCK_TUBE_RADIUS = 0.018
PERTURBATION_TUBE_RADIUS = 0.0105
SCENE_PADDING = 0.06
STANDARD_MAX_RINGS = 360
SINGLE_MAX_RINGS = 320
TOTAL_PERTURBATION_RING_BUDGET = 1_600

TUBE_LIGHTING = {
    "ambient": 0.4,
    "diffuse": 0.8,
    "specular": 0.5,
    "roughness": 0.2,
    "fresnel": 0.12,
}
LIGHT_POSITION = {"x": 80, "y": 120, "z": 160}

STANDARD_GRADIENT = ("#0a3d91", "#4deaff")
KNOCK_GRADIENT = ("#8f4b20", "#f2b66d")
PERTURBATION_GRADIENTS = (
    ("#071f4f", "#2678d8"),
    ("#07556b", "#32d5df"),
    ("#713915", "#d99655"),
    ("#102d68", "#54a7ff"),
    ("#0b4d57", "#65e0d2"),
    ("#8a4c25", "#efb77a"),
    ("#123b76", "#70c5ff"),
    ("#155b69", "#87e6e6"),
)


def _format_tick(value: float) -> str:
    """Format a real data value as a compact scientific-axis label."""
    if abs(value) < 1e-14:
        return "0"
    magnitude = abs(value)
    for threshold, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if magnitude >= threshold:
            return f"{value / threshold:.3g}{suffix}"
    if magnitude >= 1e-3:
        return f"{value:.4g}"
    return f"{value:.2e}"


@dataclass(frozen=True)
class SceneTransform:
    """Map real phase coordinates into a stable unit-cube display space."""

    origin: np.ndarray
    scale: np.ndarray
    data_min: np.ndarray
    data_max: np.ndarray
    constant_axes: np.ndarray

    @classmethod
    def from_point_sets(cls, point_sets: Iterable[np.ndarray]) -> SceneTransform:
        arrays = [np.asarray(points, dtype=float) for points in point_sets]
        arrays = [points for points in arrays if points.size]
        if not arrays:
            return cls(
                origin=np.zeros(3, dtype=float),
                scale=np.ones(3, dtype=float),
                data_min=np.zeros(3, dtype=float),
                data_max=np.zeros(3, dtype=float),
                constant_axes=np.ones(3, dtype=bool),
            )

        combined = np.vstack(arrays)
        if combined.ndim != 2 or combined.shape[1] != 3:
            raise ValueError("Phase trajectory coordinates must have shape (n, 3).")
        if not np.all(np.isfinite(combined)):
            raise ValueError("Phase trajectory coordinates must be finite.")

        data_min = np.min(combined, axis=0)
        data_max = np.max(combined, axis=0)
        spans = data_max - data_min
        reference = max(float(np.max(spans)), 1.0)
        constant_axes = spans <= reference * 1e-12
        fallback_scale = max(float(np.max(spans)), 1.0)
        scale = np.where(constant_axes, fallback_scale, spans)
        origin = np.where(constant_axes, data_min - scale * 0.5, data_min)
        return cls(origin, scale, data_min, data_max, constant_axes)

    def normalize(self, points: np.ndarray | Sequence[float]) -> np.ndarray:
        values = np.asarray(points, dtype=float)
        return (values - self.origin) / self.scale

    def denormalize(self, points: np.ndarray | Sequence[float]) -> np.ndarray:
        values = np.asarray(points, dtype=float)
        return self.origin + values * self.scale

    def axis_ticks(self, axis: int, *, count: int = 5) -> dict[str, object]:
        if self.constant_axes[axis]:
            values = np.array([float(self.data_min[axis])])
            positions = np.array([0.5])
        else:
            values = np.linspace(self.data_min[axis], self.data_max[axis], count)
            positions = (values - self.origin[axis]) / self.scale[axis]
        return {
            "tickmode": "array",
            "tickvals": positions.tolist(),
            "ticktext": [_format_tick(float(value)) for value in values],
        }


def _hex_to_rgb(color: str) -> np.ndarray:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected a six-digit hex color, received {color!r}.")
    return np.array([int(value[index:index + 2], 16) for index in (0, 2, 4)])


def _rgb_to_hex(rgb: np.ndarray) -> str:
    channels = np.clip(np.rint(rgb), 0, 255).astype(int)
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def color_gradient(start: str, end: str, count: int) -> list[str]:
    """Return ``count`` evenly interpolated RGB colors."""
    if count < 1:
        return []
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    return [
        _rgb_to_hex(start_rgb + fraction * (end_rgb - start_rgb))
        for fraction in np.linspace(0.0, 1.0, count)
    ]


def perturbation_gradient(trajectory_id: str) -> tuple[str, str]:
    """Return a deterministic neon gradient for a perturbation ID."""
    try:
        identifier = int(trajectory_id.removeprefix("P"))
    except ValueError:
        identifier = sum(ord(character) for character in trajectory_id)
    return PERTURBATION_GRADIENTS[(identifier - 1) % len(PERTURBATION_GRADIENTS)]


def perturbation_ring_limit(trajectory_count: int) -> int:
    """Allocate a bounded number of tube rings to each perturbation."""
    return max(
        72,
        min(
            SINGLE_MAX_RINGS,
            TOTAL_PERTURBATION_RING_BUDGET // max(1, trajectory_count),
        ),
    )


def _clean_and_resample(
    points: np.ndarray,
    times: np.ndarray,
    transform: SceneTransform,
    max_rings: int,
) -> tuple[np.ndarray, np.ndarray]:
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Phase trajectory coordinates must have shape (n, 3).")
    if len(points) != len(times) or not len(points):
        raise ValueError("Phase coordinates and times must have equal non-zero length.")
    if not np.all(np.isfinite(points)) or not np.all(np.isfinite(times)):
        raise ValueError("Phase coordinates and times must be finite.")

    normalized = transform.normalize(points)
    segment_lengths = np.linalg.norm(np.diff(normalized, axis=0), axis=1)
    keep = np.concatenate(([True], segment_lengths > 1e-12))
    clean_points = points[keep]
    clean_times = times[keep]
    if len(clean_points) < 2:
        return clean_points, clean_times

    if len(clean_points) <= max_rings:
        return clean_points, clean_times

    normalized = transform.normalize(clean_points)
    distance = np.concatenate(
        ([0.0], np.cumsum(np.linalg.norm(np.diff(normalized, axis=0), axis=1)))
    )
    samples = np.linspace(0.0, distance[-1], max_rings)
    resampled_points = np.column_stack(
        [np.interp(samples, distance, clean_points[:, axis]) for axis in range(3)]
    )
    resampled_times = np.interp(samples, distance, clean_times)
    return resampled_points, resampled_times


def _curve_frames(
    normalized_points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    tangents = np.empty_like(normalized_points)
    tangents[0] = normalized_points[1] - normalized_points[0]
    tangents[-1] = normalized_points[-1] - normalized_points[-2]
    if len(normalized_points) > 2:
        tangents[1:-1] = normalized_points[2:] - normalized_points[:-2]
    tangent_norms = np.linalg.norm(tangents, axis=1)
    for index in np.flatnonzero(tangent_norms <= 1e-12):
        if index < len(normalized_points) - 1:
            tangents[index] = normalized_points[index + 1] - normalized_points[index]
        if np.linalg.norm(tangents[index]) <= 1e-12 and index > 0:
            tangents[index] = normalized_points[index] - normalized_points[index - 1]
    tangent_norms = np.linalg.norm(tangents, axis=1)
    tangents /= tangent_norms[:, None]

    normals = np.empty_like(tangents)
    binormals = np.empty_like(tangents)
    reference = np.eye(3)[int(np.argmin(np.abs(tangents[0])))]
    normals[0] = np.cross(tangents[0], reference)
    normals[0] /= np.linalg.norm(normals[0])
    binormals[0] = np.cross(tangents[0], normals[0])

    for index in range(1, len(normalized_points)):
        projected = normals[index - 1] - tangents[index] * np.dot(
            normals[index - 1], tangents[index]
        )
        length = np.linalg.norm(projected)
        if length <= 1e-12:
            reference = np.eye(3)[int(np.argmin(np.abs(tangents[index])))]
            projected = np.cross(tangents[index], reference)
            length = np.linalg.norm(projected)
        normals[index] = projected / length
        binormals[index] = np.cross(tangents[index], normals[index])
    return normals, binormals


def tube_mesh_trace(
    points: np.ndarray,
    times: Sequence[float],
    *,
    transform: SceneTransform,
    name: str,
    gradient: tuple[str, str],
    radius: float,
    hovertemplate: str,
    max_rings: int,
    sides: int = TUBE_SIDES,
    opacity: float = 1.0,
    showlegend: bool = True,
    legendgroup: str | None = None,
) -> go.Mesh3d | None:
    """Create a capped, time-colored tube around a sampled 3D trajectory."""
    if sides < 3:
        raise ValueError("A tube requires at least three sides.")
    clean_points, clean_times = _clean_and_resample(
        np.asarray(points, dtype=float),
        np.asarray(times, dtype=float),
        transform,
        max_rings,
    )
    if len(clean_points) < 2:
        return None

    normalized_points = transform.normalize(clean_points)
    normals, binormals = _curve_frames(normalized_points)
    angles = np.linspace(0.0, 2.0 * np.pi, sides, endpoint=False)
    offsets = (
        np.cos(angles)[None, :, None] * normals[:, None, :]
        + np.sin(angles)[None, :, None] * binormals[:, None, :]
    )
    vertices = normalized_points[:, None, :] + radius * offsets
    vertices = vertices.reshape(-1, 3)

    ring_colors = color_gradient(gradient[0], gradient[1], len(clean_points))
    vertex_colors = [color for color in ring_colors for _ in range(sides)]
    center_data = [
        [*point.tolist(), float(time)]
        for point, time in zip(clean_points, clean_times, strict=True)
    ]
    customdata = [data for data in center_data for _ in range(sides)]

    face_i: list[int] = []
    face_j: list[int] = []
    face_k: list[int] = []
    for ring in range(len(clean_points) - 1):
        start = ring * sides
        next_start = (ring + 1) * sides
        for side in range(sides):
            following = (side + 1) % sides
            face_i.extend((start + side, start + side))
            face_j.extend((next_start + side, next_start + following))
            face_k.extend((next_start + following, start + following))

    start_center = len(vertices)
    end_center = start_center + 1
    vertices = np.vstack((vertices, normalized_points[0], normalized_points[-1]))
    vertex_colors.extend((ring_colors[0], ring_colors[-1]))
    customdata.extend((center_data[0], center_data[-1]))
    last_ring = (len(clean_points) - 1) * sides
    for side in range(sides):
        following = (side + 1) % sides
        face_i.extend((start_center, end_center))
        face_j.extend((following, last_ring + side))
        face_k.extend((side, last_ring + following))

    return go.Mesh3d(
        x=vertices[:, 0],
        y=vertices[:, 1],
        z=vertices[:, 2],
        i=face_i,
        j=face_j,
        k=face_k,
        customdata=customdata,
        vertexcolor=vertex_colors,
        name=name,
        legendgroup=legendgroup,
        showlegend=showlegend,
        opacity=opacity,
        flatshading=False,
        lighting=TUBE_LIGHTING,
        lightposition=LIGHT_POSITION,
        hovertemplate=hovertemplate,
        meta={
            "geometry": "tube",
            "radius": radius,
            "rings": len(clean_points),
            "sides": sides,
        },
    )


def sphere_mesh_trace(
    center: Sequence[float],
    *,
    transform: SceneTransform,
    radius: float,
    color: str,
    name: str,
    time: float,
    event: str,
    hovertemplate: str,
    legendgroup: str | None = None,
    latitude_steps: int = 7,
    longitude_steps: int = 12,
) -> go.Mesh3d:
    """Create a shaded ellipsoid that appears spherical in normalized scene space."""
    center_array = np.asarray(center, dtype=float)
    normalized_center = transform.normalize(center_array)
    vertices: list[np.ndarray] = [
        normalized_center + np.array([0.0, 0.0, radius])
    ]
    for latitude in range(1, latitude_steps):
        polar = np.pi * latitude / latitude_steps
        for longitude in range(longitude_steps):
            azimuth = 2.0 * np.pi * longitude / longitude_steps
            offset = np.array(
                [
                    np.sin(polar) * np.cos(azimuth),
                    np.sin(polar) * np.sin(azimuth),
                    np.cos(polar),
                ]
            )
            vertices.append(normalized_center + radius * offset)
    vertices.append(normalized_center - np.array([0.0, 0.0, radius]))
    coordinates = np.asarray(vertices)

    top = 0
    bottom = len(vertices) - 1
    face_i: list[int] = []
    face_j: list[int] = []
    face_k: list[int] = []
    first_ring = 1
    for longitude in range(longitude_steps):
        following = (longitude + 1) % longitude_steps
        face_i.append(top)
        face_j.append(first_ring + longitude)
        face_k.append(first_ring + following)

    ring_count = latitude_steps - 1
    for ring in range(ring_count - 1):
        start = first_ring + ring * longitude_steps
        next_start = start + longitude_steps
        for longitude in range(longitude_steps):
            following = (longitude + 1) % longitude_steps
            face_i.extend((start + longitude, start + longitude))
            face_j.extend((next_start + longitude, next_start + following))
            face_k.extend((next_start + following, start + following))

    last_ring = first_ring + (ring_count - 1) * longitude_steps
    for longitude in range(longitude_steps):
        following = (longitude + 1) % longitude_steps
        face_i.append(bottom)
        face_j.append(last_ring + following)
        face_k.append(last_ring + longitude)

    customdata = [[*center_array.tolist(), float(time), event]] * len(vertices)
    return go.Mesh3d(
        x=coordinates[:, 0],
        y=coordinates[:, 1],
        z=coordinates[:, 2],
        i=face_i,
        j=face_j,
        k=face_k,
        customdata=customdata,
        color=color,
        name=name,
        legendgroup=legendgroup,
        showlegend=False,
        flatshading=False,
        lighting=TUBE_LIGHTING,
        lightposition=LIGHT_POSITION,
        hovertemplate=hovertemplate,
        meta={"geometry": "endpoint-sphere", "radius": radius, "event": event},
    )


def apply_scientific_scene(
    figure: go.Figure,
    *,
    title: str,
    axis_titles: Sequence[str],
    transform: SceneTransform,
    legend_mode: Literal["hidden", "comparison"] = "hidden",
) -> None:
    """Apply the shared high-contrast scientific scene to a 3D phase figure."""
    axis_style = {
        "showgrid": False,
        "zeroline": False,
        "showspikes": False,
        "showbackground": False,
        "color": SECONDARY_TEXT_COLOR,
        "ticks": "outside",
        "tickcolor": "#94a3b8",
        "tickfont": {"color": SECONDARY_TEXT_COLOR, "size": 10},
        "title": {"font": {"color": PRIMARY_TEXT_COLOR, "size": 12}},
        "range": [-SCENE_PADDING, 1.0 + SCENE_PADDING],
    }
    legend = {
        "orientation": "v",
        "x": 0.99,
        "xanchor": "right",
        "y": 0.98,
        "yanchor": "top",
        "bgcolor": "rgba(255, 255, 255, 0.90)",
        "bordercolor": "rgba(83, 97, 118, 0.24)",
        "borderwidth": 1,
        "font": {"color": PRIMARY_TEXT_COLOR, "size": 10},
        "tracegroupgap": 3,
    }
    figure.update_layout(
        template="plotly_white",
        title={
            "text": title,
            "x": 0.02,
            "xanchor": "left",
            "font": {"color": PRIMARY_TEXT_COLOR, "size": 18},
        },
        font={"color": PRIMARY_TEXT_COLOR, "size": 12},
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        showlegend=legend_mode == "comparison",
        legend=legend,
        height=620,
        autosize=True,
        hovermode="closest",
        hoverlabel={
            "bgcolor": "#ffffff",
            "bordercolor": "#2678d8",
            "font": {"color": PRIMARY_TEXT_COLOR, "size": 12},
        },
        margin={"l": 30, "r": 30, "b": 35, "t": 70},
        uirevision="phase-plot-3d",
        scene={
            "xaxis": {
                **axis_style,
                **transform.axis_ticks(0),
                "title": {**axis_style["title"], "text": axis_titles[0]},
            },
            "yaxis": {
                **axis_style,
                **transform.axis_ticks(1),
                "title": {**axis_style["title"], "text": axis_titles[1]},
            },
            "zaxis": {
                **axis_style,
                **transform.axis_ticks(2),
                "title": {**axis_style["title"], "text": axis_titles[2]},
            },
            "bgcolor": BACKGROUND_COLOR,
            "dragmode": "orbit",
            "aspectmode": "cube",
            "aspectratio": {"x": 1.0, "y": 1.0, "z": 1.0},
            "camera": {
                "eye": {"x": 1.45, "y": 1.45, "z": 1.2},
                "projection": {"type": "perspective"},
            },
        },
    )
