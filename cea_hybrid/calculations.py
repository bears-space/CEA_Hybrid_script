"""Core NASA CEA thermochemical calculations."""

import cea
import numpy as np

from cea_hybrid.config import ensure_finite
from cea_hybrid.nozzle_sizing import add_nozzle_sizing


def abs_mass_fraction_from_volume_fraction(phi_abs, rho_abs, rho_paraffin):
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
    throat_index = 1
    exit_index = -1
    cf = float(solution.coefficient_of_thrust[exit_index])
    isp_mps = float(solution.Isp[exit_index])
    isp_vac_mps = float(solution.Isp_vacuum[exit_index])
    cstar = float(solution.c_star[chamber_index])
    cea_throat_mach = float(solution.Mach[throat_index])
    for value, name in [
        (cf, "CEA thrust coefficient"),
        (isp_mps, "CEA sea-level Isp"),
        (isp_vac_mps, "CEA vacuum Isp"),
        (cstar, "CEA c*"),
        (cea_throat_mach, "CEA throat Mach"),
    ]:
        ensure_finite(value, name)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
    if abs(cea_throat_mach - 1.0) > 1e-3:
        raise ValueError(f"CEA throat Mach is not choked: {cea_throat_mach}.")

    case = {
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
        "cstar_mps": cstar,
        "tc_k": float(solution.T[chamber_index]),
        "mach_t": 1.0,
        "pe_bar": float(solution.P[exit_index]),
        "te_k": float(solution.T[exit_index]),
        "mach_e": float(solution.Mach[exit_index]),
        "gamma_e": float(solution.gamma_s[exit_index]),
        "mw_e": float(solution.MW[exit_index]),
    }
    return add_nozzle_sizing(case, config)
