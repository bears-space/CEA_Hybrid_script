"""CSV and SVG output generation for command-line sweep runs."""

import csv
import html
import math
import shutil

from .constants import PLOT_COLORS
from .labels import float_tag, metric_label, temperature_pair_label
from .variables import CASE_FIELDS, FAILURE_FIELDS


def _resolved_fieldnames(rows, fieldnames):
    ordered = list(fieldnames)
    for row in rows:
        for key in row.keys():
            if key not in ordered:
                ordered.append(key)
    return ordered


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    resolved_fieldnames = _resolved_fieldnames(materialized, fieldnames)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=resolved_fieldnames)
        writer.writeheader()
        writer.writerows(materialized)


def write_svg(path, width, height, body_lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *body_lines,
        "</svg>",
    ]
    path.write_text("\n".join(svg), encoding="utf-8")


def add_svg_text(lines, x, y, text, size=14, anchor="middle", fill="#111111", weight="normal"):
    safe_text = html.escape(str(text))
    lines.append(
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}" font-family="Segoe UI, Arial, sans-serif" font-weight="{weight}">{safe_text}</text>'
    )


def add_svg_polyline(lines, points, stroke, stroke_width=3):
    if len(points) < 2:
        return
    point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    lines.append(
        f'<polyline points="{point_text}" fill="none" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def scale_linear(value, domain_min, domain_max, range_min, range_max):
    if domain_max == domain_min:
        return (range_min + range_max) / 2.0
    ratio = (value - domain_min) / (domain_max - domain_min)
    return range_min + ratio * (range_max - range_min)


def padded_range(values):
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        padding = max(abs(low) * 0.05, 1.0)
        return low - padding, high + padding
    padding = (high - low) * 0.05
    return low - padding, high + padding


def interpolate_color(color_a, color_b, ratio):
    ratio = max(0.0, min(1.0, ratio))
    channels = []
    for start, end in zip(color_a, color_b):
        channels.append(int(round(start + (end - start) * ratio)))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def color_for_value(value, min_value, max_value):
    low_color = (12, 91, 132)
    mid_color = (247, 247, 247)
    high_color = (197, 44, 66)
    if math.isclose(min_value, max_value):
        return "#{:02x}{:02x}{:02x}".format(*mid_color)

    ratio = (value - min_value) / (max_value - min_value)
    if ratio <= 0.5:
        return interpolate_color(low_color, mid_color, ratio * 2.0)
    return interpolate_color(mid_color, high_color, (ratio - 0.5) * 2.0)


def tick_indices(count, max_ticks=8):
    if count <= max_ticks:
        return list(range(count))
    step = (count - 1) / (max_ticks - 1)
    indices = {0, count - 1}
    for tick in range(1, max_ticks - 1):
        indices.add(int(round(tick * step)))
    return sorted(indices)


def build_group_map(rows, group_keys):
    grouped = {}
    for row in rows:
        key = tuple(row[group_key] for group_key in group_keys)
        grouped.setdefault(key, []).append(row)
    return grouped


def draw_panel_frame(body, x, y, width, height, title):
    body.append(
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'fill="#ffffff" stroke="#d0d7de" rx="12" ry="12"/>'
    )
    add_svg_text(body, x + width / 2, y + 28, title, size=18, weight="bold")


def render_heatmap_legend(body, x, y, height, metric, metric_min, metric_max):
    legend_steps = 100
    for step in range(legend_steps):
        ratio = step / max(legend_steps - 1, 1)
        value = metric_max - ratio * (metric_max - metric_min)
        color = color_for_value(value, metric_min, metric_max)
        yy = y + ratio * height
        body.append(
            f'<rect x="{x:.2f}" y="{yy:.2f}" width="24" height="{height / legend_steps + 1:.2f}" '
            f'fill="{color}" stroke="{color}"/>'
        )

    body.append(
        f'<rect x="{x:.2f}" y="{y:.2f}" width="24" height="{height:.2f}" '
        f'fill="none" stroke="#495057"/>'
    )
    add_svg_text(body, x + 12, y - 10, metric_label(metric), size=12)
    add_svg_text(body, x + 34, y + 4, f"{metric_max:.2f}", size=11, anchor="start")
    add_svg_text(body, x + 34, y + height + 4, f"{metric_min:.2f}", size=11, anchor="start")


def render_heatmap_panel(
    body,
    x,
    y,
    width,
    height,
    rows,
    of_values,
    ae_at_values,
    metric,
    title,
    metric_min,
    metric_max,
):
    draw_panel_frame(body, x, y, width, height, title)
    inner_left = x + 50
    inner_right = x + width - 18
    inner_top = y + 44
    inner_bottom = y + height - 34
    plot_width = inner_right - inner_left
    plot_height = inner_bottom - inner_top
    sorted_of = sorted(of_values)
    sorted_ae = sorted(ae_at_values)
    cell_width = plot_width / len(sorted_of)
    cell_height = plot_height / len(sorted_ae)
    lookup = {(row["ae_at"], row["of"]): row[metric] for row in rows}

    body.append(
        f'<rect x="{inner_left:.2f}" y="{inner_top:.2f}" width="{plot_width:.2f}" '
        f'height="{plot_height:.2f}" fill="#f8f9fa" stroke="#dee2e6"/>'
    )

    for row_index, ae_at in enumerate(sorted_ae):
        yy = inner_top + plot_height - (row_index + 1) * cell_height
        for col_index, of_value in enumerate(sorted_of):
            xx = inner_left + col_index * cell_width
            value = lookup.get((ae_at, of_value))
            fill = "#dee2e6" if value is None else color_for_value(value, metric_min, metric_max)
            body.append(
                f'<rect x="{xx:.2f}" y="{yy:.2f}" width="{cell_width:.2f}" height="{cell_height:.2f}" '
                f'fill="{fill}" stroke="#ffffff" stroke-width="0.6"/>'
            )

    for index in tick_indices(len(sorted_of), max_ticks=5):
        of_value = sorted_of[index]
        xx = inner_left + (index + 0.5) * cell_width
        add_svg_text(body, xx, inner_bottom + 15, f"{of_value:.1f}", size=10)

    for index in tick_indices(len(sorted_ae), max_ticks=5):
        ae_at = sorted_ae[index]
        yy = inner_top + plot_height - (index + 0.5) * cell_height
        add_svg_text(body, inner_left - 8, yy + 3, f"{ae_at:.0f}", size=10, anchor="end")

    add_svg_text(body, x + width / 2, y + height - 8, "O/F", size=11, weight="bold")
    add_svg_text(body, x + 18, y + 60, "Ae/At", size=11, anchor="start", weight="bold")


def render_line_chart_panel(
    body,
    x,
    y,
    width,
    height,
    series_map,
    x_key,
    y_key,
    title,
    x_label,
    y_label,
):
    draw_panel_frame(body, x, y, width, height, title)
    inner_left = x + 62
    inner_right = x + width - 170
    inner_top = y + 50
    inner_bottom = y + height - 52
    plot_width = inner_right - inner_left
    plot_height = inner_bottom - inner_top
    all_x_values = []
    all_y_values = []

    for rows in series_map.values():
        for row in rows:
            all_x_values.append(row[x_key])
            all_y_values.append(row[y_key])
    if not all_x_values or not all_y_values:
        return

    x_min, x_max = padded_range(all_x_values)
    y_min, y_max = padded_range(all_y_values)
    body.append(
        f'<rect x="{inner_left:.2f}" y="{inner_top:.2f}" width="{plot_width:.2f}" '
        f'height="{plot_height:.2f}" fill="#ffffff" stroke="#e9ecef"/>'
    )

    for grid_step in range(6):
        ratio = grid_step / 5
        yy = inner_top + ratio * plot_height
        value = y_max - ratio * (y_max - y_min)
        body.append(
            f'<line x1="{inner_left:.2f}" y1="{yy:.2f}" x2="{inner_left + plot_width:.2f}" '
            f'y2="{yy:.2f}" stroke="#edf2f7"/>'
        )
        add_svg_text(body, inner_left - 10, yy + 4, f"{value:.2f}", size=11, anchor="end")

    x_ticks = sorted(set(all_x_values))
    for index in tick_indices(len(x_ticks), max_ticks=8):
        x_value = x_ticks[index]
        xx = scale_linear(x_value, x_min, x_max, inner_left, inner_left + plot_width)
        body.append(
            f'<line x1="{xx:.2f}" y1="{inner_top:.2f}" x2="{xx:.2f}" '
            f'y2="{inner_top + plot_height:.2f}" stroke="#f8f9fa"/>'
        )
        add_svg_text(body, xx, inner_bottom + 18, f"{x_value:.3f}".rstrip("0").rstrip("."), size=11)

    for index, (label, rows) in enumerate(series_map.items()):
        color = PLOT_COLORS[index % len(PLOT_COLORS)]
        sorted_rows = sorted(rows, key=lambda row: row[x_key])
        points = []
        for row in sorted_rows:
            xx = scale_linear(row[x_key], x_min, x_max, inner_left, inner_left + plot_width)
            yy = scale_linear(row[y_key], y_min, y_max, inner_top + plot_height, inner_top)
            points.append((xx, yy))

        add_svg_polyline(body, points, color, stroke_width=3)
        for xx, yy in points:
            body.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="4.0" fill="{color}"/>')

        legend_y = inner_top + 14 + index * 22
        legend_x = inner_right + 18
        body.append(
            f'<line x1="{legend_x:.2f}" y1="{legend_y:.2f}" x2="{legend_x + 28:.2f}" '
            f'y2="{legend_y:.2f}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
        )
        add_svg_text(body, legend_x + 38, legend_y + 4, label, size=12, anchor="start")

    add_svg_text(body, x + width / 2, y + height - 12, x_label, size=13, weight="bold")
    add_svg_text(body, x + 12, y + 46, y_label, size=13, anchor="start", weight="bold")


def write_multi_series_plot(path, series_map, x_key, y_key, title, x_label, y_label):
    width = 1280
    height = 820
    body = []
    render_line_chart_panel(
        body,
        24,
        24,
        width - 48,
        height - 48,
        series_map,
        x_key,
        y_key,
        title,
        x_label,
        y_label,
    )
    write_svg(path, width, height, body)


def write_temperature_dashboard(
    path,
    temp_label,
    abs_values,
    cases_by_abs,
    of_values,
    ae_at_values,
    plot_metric,
):
    width = 1760
    gap = 24
    columns = 3
    heatmap_width = 500
    heatmap_height = 255
    heatmap_rows = math.ceil(len(abs_values) / columns)
    header_height = 90
    left_margin = 28
    heatmap_grid_height = heatmap_rows * heatmap_height + max(heatmap_rows - 1, 0) * gap
    height = header_height + heatmap_grid_height + 36
    body = []

    add_svg_text(body, width / 2, 34, f"Temperature Pair Dashboard | {temp_label}", size=26, weight="bold")
    add_svg_text(
        body,
        width / 2,
        64,
        f"Heatmaps show {metric_label(plot_metric)} across O/F and Ae/At",
        size=15,
        fill="#495057",
    )

    dashboard_metric_values = [row[plot_metric] for abs_rows in cases_by_abs.values() for row in abs_rows]
    metric_min = min(dashboard_metric_values)
    metric_max = max(dashboard_metric_values)

    for index, abs_vol_frac in enumerate(abs_values):
        column = index % columns
        row = index // columns
        xx = left_margin + column * (heatmap_width + gap)
        yy = header_height + row * (heatmap_height + gap)
        rows = cases_by_abs.get(abs_vol_frac, [])
        render_heatmap_panel(
            body,
            xx,
            yy,
            heatmap_width,
            heatmap_height,
            rows,
            of_values,
            ae_at_values,
            plot_metric,
            f"ABS {abs_vol_frac:.2f}",
            metric_min,
            metric_max,
        )

    legend_x = left_margin + columns * (heatmap_width + gap) + 10
    legend_y = header_height + 30
    legend_height = heatmap_grid_height - 60
    render_heatmap_legend(body, legend_x, legend_y, legend_height, plot_metric, metric_min, metric_max)

    write_svg(path, width, height, body)


def prepare_output_dir(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for csv_path in output_dir.glob("cases_abs_*.csv"):
        csv_path.unlink()
    for filename in ["all_cases.csv", "best_by_ae_at.csv", "best_overall.csv", "failures.csv"]:
        path = output_dir / filename
        if path.exists():
            path.unlink()


def generate_plots(config, output_dir, cases):
    if not config["plots"]["enabled"] or not cases:
        return []

    plot_dir = output_dir / config["plots"]["output_dir"]
    temperature_dir = plot_dir / "temperature_pairs"
    plot_metric = config["plots"]["metric"]
    generated = []

    if plot_dir.exists():
        shutil.rmtree(plot_dir)
    temperature_dir.mkdir(parents=True, exist_ok=True)

    cases_by_temp_abs = build_group_map(cases, ["fuel_temp_k", "oxidizer_temp_k", "abs_vol_frac"])

    for fuel_temp_k in config["fuel_temperatures_k"]:
        for oxidizer_temp_k in config["oxidizer_temperatures_k"]:
            cases_for_temp = {
                abs_vol_frac: cases_by_temp_abs.get((fuel_temp_k, oxidizer_temp_k, abs_vol_frac), [])
                for abs_vol_frac in config["abs_volume_fractions"]
            }
            if not any(cases_for_temp.values()):
                continue
            path = temperature_dir / (
                f"dashboard_fuel_{float_tag(fuel_temp_k)}_ox_{float_tag(oxidizer_temp_k)}.svg"
            )
            write_temperature_dashboard(
                path,
                temperature_pair_label(fuel_temp_k, oxidizer_temp_k),
                config["abs_volume_fractions"],
                cases_for_temp,
                config["of_values"],
                config["ae_at_values"],
                plot_metric,
            )
            generated.append(path)

    return generated


def write_outputs(output_dir, config, sweep_results):
    cases = sweep_results["cases"]
    failures = sweep_results["failures"]

    prepare_output_dir(output_dir)
    write_csv(output_dir / "all_cases.csv", cases, CASE_FIELDS)
    write_csv(output_dir / "failures.csv", failures, FAILURE_FIELDS)

    for abs_vol_frac in config["abs_volume_fractions"]:
        abs_rows = [row for row in cases if row["abs_vol_frac"] == abs_vol_frac]
        write_csv(output_dir / f"cases_abs_{float_tag(abs_vol_frac)}.csv", abs_rows, CASE_FIELDS)

    return generate_plots(config, output_dir, cases)

