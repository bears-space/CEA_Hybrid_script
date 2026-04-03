import csv
import html
import json
import math
import os
import shutil
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import product
from pathlib import Path

import cea
import numpy as np


G0_MPS2 = 9.80665
INPUTS_PATH = Path(__file__).with_name("inputs.json")
DEFAULT_CPU_WORKERS = os.cpu_count() or 1
PLOT_COLORS = [
    "#0b7285",
    "#c92a2a",
    "#5f3dc4",
    "#2b8a3e",
    "#e67700",
    "#495057",
    "#1c7ed6",
    "#d6336c",
    "#5c940d",
    "#9c36b5",
]
CASE_FIELDS = [
    "abs_vol_frac",
    "abs_mass_frac",
    "fuel_temp_k",
    "oxidizer_temp_k",
    "of",
    "pc_bar",
    "ae_at",
    "cf",
    "isp_mps",
    "isp_vac_mps",
    "isp_s",
    "isp_vac_s",
    "cstar_mps",
    "tc_k",
    "pe_bar",
    "te_k",
    "mach_e",
    "gamma_e",
    "mw_e",
    "mdot_total_kg_s",
    "at_m2",
    "ae_m2",
    "dt_mm",
    "de_mm",
]
FAILURE_FIELDS = [
    "abs_vol_frac",
    "fuel_temp_k",
    "oxidizer_temp_k",
    "of",
    "ae_at",
    "reason",
]
_WORKER_CONFIG = None
_WORKER_REACTANTS = None
_WORKER_SOLVER = None


class SweepCancelled(Exception):
    pass


def ensure_finite(value, name):
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def expand_sweep_values(spec, name):
    if isinstance(spec, list):
        values = spec
    elif isinstance(spec, dict):
        if "values" in spec:
            values = spec["values"]
        elif {"start", "stop", "count"} <= spec.keys():
            values = np.linspace(
                float(spec["start"]),
                float(spec["stop"]),
                int(spec["count"]),
            ).tolist()
        elif {"start", "stop", "step"} <= spec.keys():
            start = float(spec["start"])
            stop = float(spec["stop"])
            step = float(spec["step"])
            if step == 0.0:
                raise ValueError(f"{name} step cannot be zero.")

            values = []
            current = start
            tolerance = abs(step) * 1e-9

            if step > 0.0:
                while current <= stop + tolerance:
                    values.append(current)
                    current += step
            else:
                while current >= stop - tolerance:
                    values.append(current)
                    current += step
        else:
            raise ValueError(
                f"{name} must be a list or an object with values, "
                "start/stop/count, or start/stop/step."
            )
    else:
        raise ValueError(f"{name} must be a list or object.")

    if not values:
        raise ValueError(f"{name} cannot be empty.")

    return [float(value) for value in values]


def build_config(raw):
    sweeps = raw["sweeps"]
    abs_surrogate = raw["abs_surrogate"]
    densities = raw["densities_g_cm3"]
    species = raw["species"]

    styrene_share = float(abs_surrogate["styrene_share"])
    butadiene_share = float(abs_surrogate["butadiene_share"])
    share_total = styrene_share + butadiene_share
    if share_total <= 0.0:
        raise ValueError("ABS surrogate shares must sum to a positive value.")

    config = {
        "target_thrust_n": float(raw["target_thrust_n"]),
        "pc_bar": float(raw["pc_bar"]),
        "iac": bool(raw.get("iac", True)),
        "cpu_workers": raw.get("cpu_workers", "auto"),
        "summary_metric": raw.get("summary_metric", "isp_vac_mps"),
        "output_dir": Path(raw.get("output_dir", "outputs")),
        "plots": {
            "enabled": bool(raw.get("plots", {}).get("enabled", True)),
            "metric": raw.get("plots", {}).get(
                "metric",
                raw.get("summary_metric", "isp_vac_mps"),
            ),
            "output_dir": Path(raw.get("plots", {}).get("output_dir", "plots")),
        },
        "ae_at_values": expand_sweep_values(sweeps["ae_at"], "sweeps.ae_at"),
        "of_values": expand_sweep_values(sweeps["of"], "sweeps.of"),
        "abs_volume_fractions": expand_sweep_values(
            sweeps["abs_volume_fractions"],
            "sweeps.abs_volume_fractions",
        ),
        "fuel_temperatures_k": expand_sweep_values(
            sweeps["fuel_temperatures_k"],
            "sweeps.fuel_temperatures_k",
        ),
        "oxidizer_temperatures_k": expand_sweep_values(
            sweeps["oxidizer_temperatures_k"],
            "sweeps.oxidizer_temperatures_k",
        ),
        "species": {
            "oxidizer": species["oxidizer"],
            "fuel_main": species["fuel_main"],
            "styrene": species["styrene"],
            "butadiene": species["butadiene"],
        },
        "rho_paraffin": float(densities["paraffin"]),
        "rho_abs": float(densities["abs"]),
        "styrene_weight": styrene_share / share_total,
        "butadiene_weight": butadiene_share / share_total,
    }

    validate_config(config)
    return config


def load_config(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    return build_config(raw)


def validate_config(config):
    ensure_finite(config["target_thrust_n"], "target_thrust_n")
    ensure_finite(config["pc_bar"], "pc_bar")
    if config["target_thrust_n"] <= 0.0:
        raise ValueError("target_thrust_n must be positive.")
    if config["pc_bar"] <= 0.0:
        raise ValueError("pc_bar must be positive.")
    if config["summary_metric"] not in CASE_FIELDS:
        raise ValueError(
            f"summary_metric must be one of: {', '.join(CASE_FIELDS)}"
        )
    if config["plots"]["metric"] not in CASE_FIELDS:
        raise ValueError(
            f"plots.metric must be one of: {', '.join(CASE_FIELDS)}"
        )

    for value in config["ae_at_values"]:
        ensure_finite(value, "Ae/At")
        if value <= 0.0:
            raise ValueError("All Ae/At values must be positive.")
    for value in config["of_values"]:
        ensure_finite(value, "O/F")
        if value <= 0.0:
            raise ValueError("All O/F values must be positive.")
    for value in config["abs_volume_fractions"]:
        ensure_finite(value, "ABS volume fraction")
        if not 0.0 <= value <= 1.0:
            raise ValueError("ABS volume fractions must be between 0.0 and 1.0.")
    for value in config["fuel_temperatures_k"] + config["oxidizer_temperatures_k"]:
        ensure_finite(value, "Temperature")
        if value <= 0.0:
            raise ValueError("All temperatures must be positive in Kelvin.")
    if config["cpu_workers"] != "auto":
        try:
            cpu_workers = int(config["cpu_workers"])
        except (TypeError, ValueError) as exc:
            raise ValueError("cpu_workers must be 'auto' or a positive integer.") from exc
        if cpu_workers <= 0:
            raise ValueError("cpu_workers must be positive.")


def abs_mass_fraction_from_volume_fraction(
    phi_abs,
    rho_abs,
    rho_paraffin,
):
    m_abs = rho_abs * phi_abs
    m_par = rho_paraffin * (1.0 - phi_abs)
    return m_abs / (m_abs + m_par)


def build_cea_objects(config):
    species = config["species"]
    reactant_names = [
        species["fuel_main"],
        species["styrene"],
        species["butadiene"],
        species["oxidizer"],
    ]
    reactants = cea.Mixture(reactant_names)
    products = cea.Mixture(reactant_names, products_from_reactants=True)
    solver = cea.RocketSolver(products, reactants=reactants)
    return reactant_names, reactants, solver


def resolve_cpu_workers(config):
    if config["cpu_workers"] == "auto":
        return DEFAULT_CPU_WORKERS
    return max(1, int(config["cpu_workers"]))


def iter_case_inputs(config):
    return product(
        config["abs_volume_fractions"],
        config["fuel_temperatures_k"],
        config["oxidizer_temperatures_k"],
        config["ae_at_values"],
        config["of_values"],
    )


def _init_worker(config):
    global _WORKER_CONFIG, _WORKER_REACTANTS, _WORKER_SOLVER
    _WORKER_CONFIG = config
    _, _WORKER_REACTANTS, _WORKER_SOLVER = build_cea_objects(config)


def _run_case_in_worker(case_input):
    abs_vol_frac, fuel_temp_k, oxidizer_temp_k, ae_at, of_ratio = case_input
    try:
        result = run_case(
            _WORKER_CONFIG,
            _WORKER_REACTANTS,
            _WORKER_SOLVER,
            abs_vol_frac,
            fuel_temp_k,
            oxidizer_temp_k,
            of_ratio,
            ae_at,
        )
    except Exception as exc:
        return {
            "kind": "failure",
            "payload": {
                "abs_vol_frac": abs_vol_frac,
                "fuel_temp_k": fuel_temp_k,
                "oxidizer_temp_k": oxidizer_temp_k,
                "of": of_ratio,
                "ae_at": ae_at,
                "reason": str(exc),
            },
        }

    if result is None:
        return {
            "kind": "failure",
            "payload": {
                "abs_vol_frac": abs_vol_frac,
                "fuel_temp_k": fuel_temp_k,
                "oxidizer_temp_k": oxidizer_temp_k,
                "of": of_ratio,
                "ae_at": ae_at,
                "reason": "CEA did not converge",
            },
        }

    return {"kind": "success", "payload": result}


def run_case(
    config,
    reactants,
    solver,
    abs_vol_frac,
    fuel_temp_k,
    oxidizer_temp_k,
    of_ratio,
    ae_at,
):
    w_abs = abs_mass_fraction_from_volume_fraction(
        abs_vol_frac,
        config["rho_abs"],
        config["rho_paraffin"],
    )
    w_par = 1.0 - w_abs
    w_sty = w_abs * config["styrene_weight"]
    w_but = w_abs * config["butadiene_weight"]

    reactant_temps = np.array(
        [fuel_temp_k, fuel_temp_k, fuel_temp_k, oxidizer_temp_k],
        dtype=float,
    )
    fuel_weights = np.array([w_par, w_sty, w_but, 0.0], dtype=float)
    oxidizer_weights = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

    weights = reactants.of_ratio_to_weights(oxidizer_weights, fuel_weights, of_ratio)
    hc = reactants.calc_property(cea.ENTHALPY, weights, reactant_temps) / cea.R

    solution = cea.RocketSolution(solver)
    solver.solve(
        solution,
        weights,
        config["pc_bar"],
        [100.0],
        supar=[float(ae_at)],
        hc=hc,
        iac=config["iac"],
    )

    if not solution.converged:
        return None

    chamber_index = 0
    exit_index = -1
    cf = float(solution.coefficient_of_thrust[exit_index])
    isp_mps = float(solution.Isp[exit_index])
    isp_vac_mps = float(solution.Isp_vacuum[exit_index])
    cstar = float(solution.c_star[chamber_index])
    for value, name in [
        (cf, "CEA thrust coefficient"),
        (isp_mps, "CEA sea-level Isp"),
        (isp_vac_mps, "CEA vacuum Isp"),
        (cstar, "CEA c*"),
    ]:
        ensure_finite(value, name)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
    pc_pa = config["pc_bar"] * 1e5

    at_m2 = config["target_thrust_n"] / (cf * pc_pa)
    mdot_total = config["target_thrust_n"] / isp_mps
    ae_m2 = ae_at * at_m2

    dt_m = math.sqrt(4.0 * at_m2 / math.pi)
    de_m = math.sqrt(4.0 * ae_m2 / math.pi)

    return {
        "abs_vol_frac": abs_vol_frac,
        "abs_mass_frac": w_abs,
        "fuel_temp_k": fuel_temp_k,
        "oxidizer_temp_k": oxidizer_temp_k,
        "of": of_ratio,
        "pc_bar": config["pc_bar"],
        "ae_at": ae_at,
        "cf": cf,
        "isp_mps": isp_mps,
        "isp_vac_mps": isp_vac_mps,
        "isp_s": isp_mps / G0_MPS2,
        "isp_vac_s": isp_vac_mps / G0_MPS2,
        "cstar_mps": cstar,
        "tc_k": float(solution.T[chamber_index]),
        "pe_bar": float(solution.P[exit_index]),
        "te_k": float(solution.T[exit_index]),
        "mach_e": float(solution.Mach[exit_index]),
        "gamma_e": float(solution.gamma_s[exit_index]),
        "mw_e": float(solution.MW[exit_index]),
        "mdot_total_kg_s": mdot_total,
        "at_m2": at_m2,
        "ae_m2": ae_m2,
        "dt_mm": dt_m * 1e3,
        "de_mm": de_m * 1e3,
    }


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def select_best_rows(rows, group_keys, metric):
    grouped = {}
    for row in rows:
        group_id = tuple(row[key] for key in group_keys)
        current_best = grouped.get(group_id)
        if current_best is None or row[metric] > current_best[metric]:
            grouped[group_id] = row

    best_rows = list(grouped.values())
    best_rows.sort(key=lambda row: tuple(row[key] for key in group_keys))
    return best_rows


def float_tag(value):
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", "p").replace("-", "m")


def metric_label(metric):
    labels = {
        "ae_at": "Ae/At [-]",
        "at_m2": "Throat Area [m^2]",
        "cf": "Thrust Coefficient [-]",
        "cstar_mps": "c* [m/s]",
        "de_mm": "Exit Diameter [mm]",
        "dt_mm": "Throat Diameter [mm]",
        "fuel_temp_k": "Fuel Temperature [K]",
        "gamma_e": "Exit Gamma [-]",
        "isp_mps": "Isp [m/s]",
        "isp_s": "Isp [s]",
        "isp_vac_mps": "Vacuum Isp [m/s]",
        "isp_vac_s": "Vacuum Isp [s]",
        "mach_e": "Exit Mach [-]",
        "mdot_total_kg_s": "Mass Flow [kg/s]",
        "mw_e": "Exit Molecular Weight",
        "of": "O/F [-]",
        "oxidizer_temp_k": "Oxidizer Temperature [K]",
        "pc_bar": "Chamber Pressure [bar]",
        "pe_bar": "Exit Pressure [bar]",
        "tc_k": "Chamber Temperature [K]",
        "te_k": "Exit Temperature [K]",
    }
    return labels.get(metric, metric.replace("_", " "))


def temperature_pair_label(fuel_temp_k, oxidizer_temp_k):
    return f"Fuel {fuel_temp_k:.0f} K | Ox {oxidizer_temp_k:.0f} K"


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
    render_line_chart_panel(body, 24, 24, width - 48, height - 48, series_map, x_key, y_key, title, x_label, y_label)
    write_svg(path, width, height, body)


def write_temperature_dashboard(
    path,
    temp_label,
    abs_values,
    cases_by_abs,
    best_by_ae_at_by_abs,
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
    top_margin = 28
    left_margin = 28
    heatmap_grid_height = heatmap_rows * heatmap_height + max(heatmap_rows - 1, 0) * gap
    lower_panel_y = header_height + heatmap_grid_height + 2 * gap
    lower_panel_height = 470
    height = lower_panel_y + lower_panel_height + 36
    body = []

    add_svg_text(body, width / 2, 34, f"Temperature Pair Dashboard | {temp_label}", size=26, weight="bold")
    add_svg_text(body, width / 2, 64, f"Heatmaps show {metric_label(plot_metric)} across O/F and Ae/At", size=15, fill="#495057")

    dashboard_metric_values = [
        row[plot_metric]
        for abs_rows in cases_by_abs.values()
        for row in abs_rows
    ]
    metric_min = min(dashboard_metric_values)
    metric_max = max(dashboard_metric_values)

    for index, abs_vol_frac in enumerate(abs_values):
        column = index % columns
        row = index // columns
        xx = left_margin + column * (heatmap_width + gap)
        yy = header_height + row * (heatmap_height + gap)
        rows = cases_by_abs.get(abs_vol_frac, [])
        title = f"ABS {abs_vol_frac:.2f}"
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
            title,
            metric_min,
            metric_max,
        )

    legend_x = left_margin + columns * (heatmap_width + gap) + 10
    legend_y = header_height + 30
    legend_height = heatmap_grid_height - 60
    render_heatmap_legend(body, legend_x, legend_y, legend_height, plot_metric, metric_min, metric_max)

    metric_series = {}
    of_series = {}
    for abs_vol_frac in abs_values:
        label = f"ABS {abs_vol_frac:.2f}"
        rows = best_by_ae_at_by_abs.get(abs_vol_frac, [])
        metric_series[label] = rows
        of_series[label] = rows

    lower_width = (width - 2 * left_margin - gap) / 2
    render_line_chart_panel(
        body,
        left_margin,
        lower_panel_y,
        lower_width,
        lower_panel_height,
        metric_series,
        "ae_at",
        plot_metric,
        f"Best {metric_label(plot_metric)} vs Ae/At",
        "Ae/At [-]",
        metric_label(plot_metric),
    )
    render_line_chart_panel(
        body,
        left_margin + lower_width + gap,
        lower_panel_y,
        lower_width,
        lower_panel_height,
        of_series,
        "ae_at",
        "of",
        "Best O/F vs Ae/At",
        "Ae/At [-]",
        metric_label("of"),
    )
    write_svg(path, width, height, body)


def prepare_output_dir(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for csv_path in output_dir.glob("cases_abs_*.csv"):
        csv_path.unlink()
    for filename in ["all_cases.csv", "best_by_ae_at.csv", "best_overall.csv", "failures.csv"]:
        path = output_dir / filename
        if path.exists():
            path.unlink()


def generate_plots(config, output_dir, cases, best_by_ae_at, best_overall):
    if not config["plots"]["enabled"] or not cases:
        return []

    plot_dir = output_dir / config["plots"]["output_dir"]
    overview_dir = plot_dir / "overview"
    temperature_dir = plot_dir / "temperature_pairs"
    plot_metric = config["plots"]["metric"]
    generated = []

    if plot_dir.exists():
        shutil.rmtree(plot_dir)
    overview_dir.mkdir(parents=True, exist_ok=True)
    temperature_dir.mkdir(parents=True, exist_ok=True)

    best_overall_series = build_group_map(best_overall, ["fuel_temp_k", "oxidizer_temp_k"])
    best_overall_metric_series = {
        temperature_pair_label(key[0], key[1]): rows
        for key, rows in best_overall_series.items()
    }

    summary_metric_path = overview_dir / f"best_{plot_metric}_vs_abs.svg"
    write_multi_series_plot(
        summary_metric_path,
        best_overall_metric_series,
        "abs_vol_frac",
        plot_metric,
        f"Best {metric_label(plot_metric)} vs ABS Fraction",
        "ABS Volume Fraction [-]",
        metric_label(plot_metric),
    )
    generated.append(summary_metric_path)

    summary_of_path = overview_dir / "best_of_vs_abs.svg"
    write_multi_series_plot(
        summary_of_path,
        best_overall_metric_series,
        "abs_vol_frac",
        "of",
        "Best O/F vs ABS Fraction",
        "ABS Volume Fraction [-]",
        metric_label("of"),
    )
    generated.append(summary_of_path)

    summary_ae_path = overview_dir / "best_ae_at_vs_abs.svg"
    write_multi_series_plot(
        summary_ae_path,
        best_overall_metric_series,
        "abs_vol_frac",
        "ae_at",
        "Best Ae/At vs ABS Fraction",
        "ABS Volume Fraction [-]",
        metric_label("ae_at"),
    )
    generated.append(summary_ae_path)

    cases_by_temp_abs = build_group_map(cases, ["fuel_temp_k", "oxidizer_temp_k", "abs_vol_frac"])
    best_by_temp_abs = build_group_map(best_by_ae_at, ["fuel_temp_k", "oxidizer_temp_k", "abs_vol_frac"])

    for fuel_temp_k in config["fuel_temperatures_k"]:
        for oxidizer_temp_k in config["oxidizer_temperatures_k"]:
            cases_for_temp = {
                abs_vol_frac: cases_by_temp_abs.get((fuel_temp_k, oxidizer_temp_k, abs_vol_frac), [])
                for abs_vol_frac in config["abs_volume_fractions"]
            }
            best_for_temp = {
                abs_vol_frac: best_by_temp_abs.get((fuel_temp_k, oxidizer_temp_k, abs_vol_frac), [])
                for abs_vol_frac in config["abs_volume_fractions"]
            }
            path = temperature_dir / (
                f"dashboard_fuel_{float_tag(fuel_temp_k)}_ox_{float_tag(oxidizer_temp_k)}.svg"
            )
            write_temperature_dashboard(
                path,
                temperature_pair_label(fuel_temp_k, oxidizer_temp_k),
                config["abs_volume_fractions"],
                cases_for_temp,
                best_for_temp,
                config["of_values"],
                config["ae_at_values"],
                plot_metric,
            )
            generated.append(path)

    return generated


def run_sweep(config, progress_callback=None, cancel_event=None):
    cases = []
    failures = []
    cpu_workers = resolve_cpu_workers(config)
    total_combinations = (
        len(config["abs_volume_fractions"])
        * len(config["fuel_temperatures_k"])
        * len(config["oxidizer_temperatures_k"])
        * len(config["ae_at_values"])
        * len(config["of_values"])
    )
    completed = 0

    def update_progress():
        if progress_callback is not None:
            progress_callback(completed, total_combinations)

    update_progress()

    if cpu_workers == 1:
        _init_worker(config)
        for case_input in iter_case_inputs(config):
            if cancel_event is not None and cancel_event.is_set():
                raise SweepCancelled("Sweep cancelled.")
            item = _run_case_in_worker(case_input)
            if item["kind"] == "success":
                cases.append(item["payload"])
            else:
                failures.append(item["payload"])
            completed += 1
            update_progress()
    else:
        executor = ProcessPoolExecutor(
            max_workers=cpu_workers,
            initializer=_init_worker,
            initargs=(config,),
        )
        case_iter = iter(iter_case_inputs(config))
        max_pending = max(cpu_workers * 4, cpu_workers)
        pending = {}

        def submit_next():
            try:
                case_input = next(case_iter)
            except StopIteration:
                return False
            future = executor.submit(_run_case_in_worker, case_input)
            pending[future] = case_input
            return True

        try:
            while len(pending) < max_pending and submit_next():
                pass

            while pending:
                if cancel_event is not None and cancel_event.is_set():
                    raise SweepCancelled("Sweep cancelled.")
                done, _ = wait(
                    tuple(pending.keys()),
                    timeout=0.2,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    continue
                for future in done:
                    pending.pop(future, None)
                    item = future.result()
                    if item["kind"] == "success":
                        cases.append(item["payload"])
                    else:
                        failures.append(item["payload"])
                    completed += 1
                    update_progress()
                while len(pending) < max_pending and submit_next():
                    pass
        except Exception:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown()

    cases.sort(
        key=lambda row: (
            row["abs_vol_frac"],
            row["fuel_temp_k"],
            row["oxidizer_temp_k"],
            row["ae_at"],
            row["of"],
        )
    )
    failures.sort(
        key=lambda row: (
            row["abs_vol_frac"],
            row["fuel_temp_k"],
            row["oxidizer_temp_k"],
            row["ae_at"],
            row["of"],
        )
    )

    best_by_ae_at = select_best_rows(
        cases,
        ["abs_vol_frac", "fuel_temp_k", "oxidizer_temp_k", "ae_at"],
        config["summary_metric"],
    )
    best_overall = select_best_rows(
        cases,
        ["abs_vol_frac", "fuel_temp_k", "oxidizer_temp_k"],
        config["summary_metric"],
    )

    return {
        "cases": cases,
        "failures": failures,
        "best_by_ae_at": best_by_ae_at,
        "best_overall": best_overall,
        "total_combinations": total_combinations,
        "cpu_workers": cpu_workers,
        "backend": "cpu-multiprocessing" if cpu_workers > 1 else "cpu-single-process",
        "gpu_enabled": False,
    }


def write_outputs(output_dir, config, sweep_results):
    cases = sweep_results["cases"]
    failures = sweep_results["failures"]
    best_by_ae_at = sweep_results["best_by_ae_at"]
    best_overall = sweep_results["best_overall"]

    prepare_output_dir(output_dir)
    write_csv(output_dir / "all_cases.csv", cases, CASE_FIELDS)
    write_csv(output_dir / "failures.csv", failures, FAILURE_FIELDS)
    write_csv(output_dir / "best_by_ae_at.csv", best_by_ae_at, CASE_FIELDS)
    write_csv(output_dir / "best_overall.csv", best_overall, CASE_FIELDS)

    for abs_vol_frac in config["abs_volume_fractions"]:
        abs_rows = [row for row in cases if row["abs_vol_frac"] == abs_vol_frac]
        write_csv(
            output_dir / f"cases_abs_{float_tag(abs_vol_frac)}.csv",
            abs_rows,
            CASE_FIELDS,
        )

    plot_paths = generate_plots(config, output_dir, cases, best_by_ae_at, best_overall)
    return plot_paths


def main():
    config = load_config(INPUTS_PATH)
    output_dir = INPUTS_PATH.parent / config["output_dir"]
    sweep_results = run_sweep(config)

    print(f"Loaded inputs from {INPUTS_PATH}")
    print(f"Writing CSV outputs to {output_dir}")
    print(
        "Sweep sizes: "
        f"ABS={len(config['abs_volume_fractions'])}, "
        f"fuel T={len(config['fuel_temperatures_k'])}, "
        f"oxidizer T={len(config['oxidizer_temperatures_k'])}, "
        f"Ae/At={len(config['ae_at_values'])}, "
        f"O/F={len(config['of_values'])}"
    )
    print(f"Total combinations: {sweep_results['total_combinations']}")
    print(f"Compute backend: {sweep_results['backend']} ({sweep_results['cpu_workers']} worker(s))")

    plot_paths = write_outputs(output_dir, config, sweep_results)

    print(f"Converged cases: {len(sweep_results['cases'])}")
    print(f"Failed or unconverged cases: {len(sweep_results['failures'])}")
    print(f"Wrote {output_dir / 'all_cases.csv'}")
    print(f"Wrote {output_dir / 'best_by_ae_at.csv'}")
    print(f"Wrote {output_dir / 'best_overall.csv'}")
    print(f"Wrote {output_dir / 'failures.csv'}")
    if plot_paths:
        print(f"Wrote {len(plot_paths)} plot files to {output_dir / config['plots']['output_dir']}")


if __name__ == "__main__":
    main()
