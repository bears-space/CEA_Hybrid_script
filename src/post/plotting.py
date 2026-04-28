"""Lightweight SVG plotting helpers that avoid external plotting dependencies."""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence

COLORS = [
    "#0f766e",
    "#b86a2d",
    "#345c7c",
    "#7c5aa6",
    "#a3475d",
    "#5c7f37",
    "#2d8d88",
    "#9a6742",
    "#536a7a",
]


def _write_svg(path: Path, width: int, height: int, body_lines: Sequence[str]) -> Path:
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *body_lines,
        "</svg>",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg), encoding="utf-8")
    return path


def _text(x: float, y: float, text: str, size: int = 12, anchor: str = "middle", weight: str = "normal", fill: str = "#111827") -> str:
    safe = html.escape(str(text))
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" '
        f'font-family="Segoe UI, Arial, sans-serif" font-weight="{weight}" fill="{fill}">{safe}</text>'
    )


def _scale(value: float, domain_min: float, domain_max: float, range_min: float, range_max: float) -> float:
    if math.isclose(domain_min, domain_max):
        return 0.5 * (range_min + range_max)
    ratio = (value - domain_min) / (domain_max - domain_min)
    return range_min + ratio * (range_max - range_min)


def _padded_range(values: Iterable[float]) -> tuple[float, float]:
    numeric = [float(value) for value in values]
    low = min(numeric)
    high = max(numeric)
    if math.isclose(low, high):
        padding = max(abs(low) * 0.05, 1.0)
        return low - padding, high + padding
    padding = 0.05 * (high - low)
    return low - padding, high + padding


def write_line_plot(path: str | Path, series: Sequence[Mapping[str, object]], title: str, x_label: str, y_label: str) -> Path:
    width = 1200
    height = 760
    plot_left = 90
    plot_right = 900
    plot_top = 70
    plot_bottom = 650
    body: list[str] = []

    all_x = [float(x) for item in series for x in item["x"]]
    all_y = [float(y) for item in series for y in item["y"]]
    x_min, x_max = _padded_range(all_x)
    y_min, y_max = _padded_range(all_y)

    body.append(f'<rect x="{plot_left}" y="{plot_top}" width="{plot_right - plot_left}" height="{plot_bottom - plot_top}" fill="#f8fafc" stroke="#cbd5e1"/>')
    body.append(_text(width / 2, 34, title, size=24, weight="bold"))
    body.append(_text(width / 2, height - 18, x_label, size=14, weight="bold"))
    body.append(_text(28, 44, y_label, size=14, weight="bold", anchor="start"))

    for tick in range(6):
        ratio = tick / 5.0
        y = plot_top + ratio * (plot_bottom - plot_top)
        value = y_max - ratio * (y_max - y_min)
        body.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_right}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        body.append(_text(plot_left - 10, y + 4, f"{value:.2f}", size=11, anchor="end"))

    for tick in range(6):
        ratio = tick / 5.0
        x = plot_left + ratio * (plot_right - plot_left)
        value = x_min + ratio * (x_max - x_min)
        body.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_bottom}" stroke="#f1f5f9"/>')
        body.append(_text(x, plot_bottom + 18, f"{value:.2f}", size=11))

    for index, item in enumerate(series):
        color = item.get("color", COLORS[index % len(COLORS)])
        points = []
        for x_value, y_value in zip(item["x"], item["y"]):
            x = _scale(float(x_value), x_min, x_max, plot_left, plot_right)
            y = _scale(float(y_value), y_min, y_max, plot_bottom, plot_top)
            points.append((x, y))
        point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        body.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="{point_text}"/>')
        legend_y = plot_top + 24 + index * 24
        body.append(f'<line x1="940" y1="{legend_y}" x2="970" y2="{legend_y}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        body.append(_text(980, legend_y + 4, str(item["label"]), size=12, anchor="start"))

    return _write_svg(Path(path), width, height, body)


def write_horizontal_bar_chart(path: str | Path, entries: Sequence[Mapping[str, object]], title: str, x_label: str) -> Path:
    width = 1200
    row_height = 36
    height = max(320, 120 + len(entries) * row_height)
    plot_left = 250
    plot_right = 1080
    plot_top = 60
    body: list[str] = [_text(width / 2, 30, title, size=24, weight="bold")]

    values = [abs(float(entry["value"])) for entry in entries] or [1.0]
    x_min = 0.0
    x_max = max(values) * 1.1

    for index, entry in enumerate(entries):
        y = plot_top + index * row_height
        value = abs(float(entry["value"]))
        label = str(entry["label"])
        bar_right = _scale(value, x_min, x_max, plot_left, plot_right)
        color = COLORS[index % len(COLORS)]
        body.append(_text(plot_left - 12, y + 18, label, size=12, anchor="end"))
        body.append(f'<rect x="{plot_left}" y="{y + 6}" width="{max(bar_right - plot_left, 1):.2f}" height="20" rx="8" ry="8" fill="{color}" opacity="0.85"/>')
        body.append(_text(bar_right + 8, y + 20, f"{value:.3f}", size=11, anchor="start"))

    body.append(_text(width / 2, height - 16, x_label, size=14, weight="bold"))
    return _write_svg(Path(path), width, height, body)


def write_grouped_horizontal_bar_chart(
    path: str | Path,
    entries: Sequence[Mapping[str, object]],
    series_labels: Sequence[str],
    title: str,
    x_label: str,
) -> Path:
    width = 1200
    row_group_height = max(52, 24 * max(len(series_labels), 1) + 14)
    height = max(340, 140 + len(entries) * row_group_height)
    plot_left = 260
    plot_right = 1080
    plot_top = 84
    body: list[str] = [_text(width / 2, 30, title, size=24, weight="bold")]

    values = [
        abs(float(entry.get("values", {}).get(series_label, 0.0)))
        for entry in entries
        for series_label in series_labels
    ] or [1.0]
    x_min = 0.0
    x_max = max(values) * 1.1

    for tick in range(6):
        ratio = tick / 5.0
        x = plot_left + ratio * (plot_right - plot_left)
        value = x_min + ratio * (x_max - x_min)
        body.append(f'<line x1="{x:.2f}" y1="{plot_top - 10}" x2="{x:.2f}" y2="{height - 44}" stroke="#e2e8f0"/>')
        body.append(_text(x, height - 22, f"{value:.4f}", size=11))

    for entry_index, entry in enumerate(entries):
        label = str(entry.get("label", f"Row {entry_index + 1}"))
        values_by_series = dict(entry.get("values", {}))
        group_y = plot_top + entry_index * row_group_height
        group_center_y = group_y + (len(series_labels) * 24) / 2.0
        body.append(_text(plot_left - 12, group_center_y + 4, label, size=12, anchor="end"))
        for series_index, series_label in enumerate(series_labels):
            value = abs(float(values_by_series.get(series_label, 0.0)))
            y = group_y + series_index * 24
            color = COLORS[series_index % len(COLORS)]
            bar_right = _scale(value, x_min, x_max, plot_left, plot_right)
            body.append(
                f'<rect x="{plot_left}" y="{y + 4}" width="{max(bar_right - plot_left, 1):.2f}" height="16" rx="7" ry="7" fill="{color}" opacity="0.85"/>'
            )
            body.append(_text(bar_right + 8, y + 17, f"{value:.4f}", size=10, anchor="start"))

    legend_y = 54
    for series_index, series_label in enumerate(series_labels):
        color = COLORS[series_index % len(COLORS)]
        x0 = 280 + series_index * 180
        body.append(f'<rect x="{x0}" y="{legend_y - 11}" width="18" height="10" rx="4" ry="4" fill="{color}" opacity="0.85"/>')
        body.append(_text(x0 + 26, legend_y - 2, str(series_label), size=12, anchor="start"))

    body.append(_text(width / 2, height - 8, x_label, size=14, weight="bold"))
    return _write_svg(Path(path), width, height, body)


def write_scatter_plot(
    path: str | Path,
    series: Sequence[Mapping[str, object]],
    title: str,
    x_label: str,
    y_label: str,
    *,
    reference_line: bool = False,
) -> Path:
    width = 1200
    height = 760
    plot_left = 90
    plot_right = 900
    plot_top = 70
    plot_bottom = 650
    body: list[str] = []

    all_x = [float(x) for item in series for x in item["x"]]
    all_y = [float(y) for item in series for y in item["y"]]
    if not all_x or not all_y:
        return _write_svg(
            Path(path),
            width,
            height,
            [
                _text(width / 2, 34, title, size=24, weight="bold"),
                _text(width / 2, height / 2, "No data available", size=18, weight="bold"),
            ],
        )
    x_min, x_max = _padded_range(all_x)
    y_min, y_max = _padded_range(all_y)
    if reference_line:
        common_min = min(x_min, y_min)
        common_max = max(x_max, y_max)
        x_min = y_min = common_min
        x_max = y_max = common_max

    body.append(f'<rect x="{plot_left}" y="{plot_top}" width="{plot_right - plot_left}" height="{plot_bottom - plot_top}" fill="#f8fafc" stroke="#cbd5e1"/>')
    body.append(_text(width / 2, 34, title, size=24, weight="bold"))
    body.append(_text(width / 2, height - 18, x_label, size=14, weight="bold"))
    body.append(_text(28, 44, y_label, size=14, weight="bold", anchor="start"))

    for tick in range(6):
        ratio = tick / 5.0
        y = plot_top + ratio * (plot_bottom - plot_top)
        value = y_max - ratio * (y_max - y_min)
        body.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_right}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        body.append(_text(plot_left - 10, y + 4, f"{value:.2f}", size=11, anchor="end"))

    for tick in range(6):
        ratio = tick / 5.0
        x = plot_left + ratio * (plot_right - plot_left)
        value = x_min + ratio * (x_max - x_min)
        body.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_bottom}" stroke="#f1f5f9"/>')
        body.append(_text(x, plot_bottom + 18, f"{value:.2f}", size=11))

    if reference_line:
        line_start_x = _scale(x_min, x_min, x_max, plot_left, plot_right)
        line_start_y = _scale(y_min, y_min, y_max, plot_bottom, plot_top)
        line_end_x = _scale(x_max, x_min, x_max, plot_left, plot_right)
        line_end_y = _scale(y_max, y_min, y_max, plot_bottom, plot_top)
        body.append(
            f'<line x1="{line_start_x:.2f}" y1="{line_start_y:.2f}" x2="{line_end_x:.2f}" y2="{line_end_y:.2f}" stroke="#9ca3af" stroke-width="2" stroke-dasharray="8 6"/>'
        )

    for index, item in enumerate(series):
        color = item.get("color", COLORS[index % len(COLORS)])
        for x_value, y_value in zip(item["x"], item["y"]):
            x = _scale(float(x_value), x_min, x_max, plot_left, plot_right)
            y = _scale(float(y_value), y_min, y_max, plot_bottom, plot_top)
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}" opacity="0.85"/>')
        legend_y = plot_top + 24 + index * 24
        body.append(f'<circle cx="955" cy="{legend_y - 4:.2f}" r="6" fill="{color}" opacity="0.85"/>')
        body.append(_text(970, legend_y, str(item["label"]), size=12, anchor="start"))

    return _write_svg(Path(path), width, height, body)
