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
