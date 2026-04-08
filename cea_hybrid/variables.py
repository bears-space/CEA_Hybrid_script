"""Documented result-variable selection for CEA sweeps.

This module is the single place to decide which values are exported or exposed
as plot metrics. Sources are tagged as input, CEA, or minimal sizing derived
from CEA outputs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultVariable:
    key: str
    label: str
    source: str
    description: str
    plot_metric: bool = False


CASE_VARIABLES = [
    ResultVariable(
        "abs_vol_frac",
        "ABS Volume Fraction [-]",
        "input",
        "ABS volume fraction passed into the CEA reactant mixture definition.",
    ),
    ResultVariable(
        "fuel_temp_k",
        "Fuel Temperature [K]",
        "input",
        "Fuel-side reactant temperature passed to CEA.",
    ),
    ResultVariable(
        "oxidizer_temp_k",
        "Oxidizer Temperature [K]",
        "input",
        "Oxidizer-side reactant temperature passed to CEA.",
    ),
    ResultVariable(
        "of",
        "O/F [-]",
        "input",
        "Oxidizer-to-fuel mass ratio passed to CEA.",
    ),
    ResultVariable(
        "pc_bar",
        "Target Chamber Pressure [bar]",
        "input",
        "Target combustion chamber pressure passed to CEA.",
    ),
    ResultVariable(
        "ae_at",
        "Ae/At [-]",
        "input",
        "Nozzle exit-to-throat area ratio passed to CEA.",
    ),
    ResultVariable(
        "target_thrust_n",
        "Target Thrust [N]",
        "input",
        "Requested thrust used only for post-CEA nozzle sizing.",
    ),
    ResultVariable(
        "max_exit_diameter_cm",
        "Max Exit Diameter [cm]",
        "input",
        "Maximum allowed nozzle exit diameter used to filter sized cases.",
    ),
    ResultVariable(
        "max_area_ratio",
        "Max Ae/At [-]",
        "input",
        "Maximum allowed area ratio when the simulation cap mode is area ratio.",
    ),
    ResultVariable(
        "ae_at_cap_mode",
        "Ae/At Cap Mode",
        "input",
        "Selected cap mode for the area-ratio sweep.",
    ),
    ResultVariable(
        "cf",
        "Thrust Coefficient [-]",
        "cea",
        "CEA nozzle-exit thrust coefficient.",
        True,
    ),
    ResultVariable(
        "isp_mps",
        "Isp [m/s]",
        "cea",
        "CEA nozzle-exit specific impulse.",
    ),
    ResultVariable(
        "isp_vac_mps",
        "Vacuum Isp [m/s]",
        "cea",
        "CEA nozzle-exit vacuum specific impulse.",
    ),
    ResultVariable(
        "cstar_mps",
        "c* [m/s]",
        "cea",
        "CEA chamber characteristic velocity.",
        True,
    ),
    ResultVariable(
        "tc_k",
        "Chamber Temperature [K]",
        "cea",
        "CEA chamber static temperature.",
        True,
    ),
    ResultVariable(
        "mach_t",
        "Throat Mach [-]",
        "cea",
        "CEA throat-station Mach number. This is the choked throat condition used by the sizing layer.",
        True,
    ),
    ResultVariable(
        "pe_bar",
        "Exit Pressure [bar]",
        "cea",
        "CEA nozzle-exit static pressure.",
    ),
    ResultVariable(
        "te_k",
        "Exit Temperature [K]",
        "cea",
        "CEA nozzle-exit static temperature.",
    ),
    ResultVariable(
        "mach_e",
        "Exit Mach [-]",
        "cea",
        "CEA nozzle-exit Mach number.",
        True,
    ),
    ResultVariable(
        "gamma_e",
        "Exit Gamma [-]",
        "cea",
        "CEA nozzle-exit isentropic exponent.",
    ),
    ResultVariable(
        "mw_e",
        "Exit Molecular Weight",
        "cea",
        "CEA nozzle-exit molecular weight.",
    ),
    ResultVariable(
        "abs_mass_frac",
        "ABS Mass Fraction [-]",
        "sizing",
        "ABS mass fraction converted from ABS volume fraction and material densities.",
    ),
    ResultVariable(
        "isp_s",
        "Isp [s]",
        "sizing",
        "CEA specific impulse converted from m/s to seconds.",
        True,
    ),
    ResultVariable(
        "isp_vac_s",
        "Vacuum Isp [s]",
        "sizing",
        "CEA vacuum specific impulse converted from m/s to seconds.",
        True,
    ),
    ResultVariable(
        "mdot_total_kg_s",
        "Mass Flow [kg/s]",
        "sizing",
        "Total propellant mass flow from target thrust divided by CEA Isp.",
        True,
    ),
    ResultVariable(
        "at_m2",
        "Throat Area [m^2]",
        "sizing",
        "Nozzle throat area from target mass flow, chamber pressure, and CEA c* so the throat is choked.",
        True,
    ),
    ResultVariable(
        "ae_m2",
        "Exit Area [m^2]",
        "sizing",
        "Nozzle exit area from throat area and Ae/At.",
        True,
    ),
    ResultVariable(
        "thrust_sl_n",
        "Actual Sea-Level Thrust [N]",
        "sizing",
        "Estimated sea-level thrust after applying the standard sea-level ambient-pressure correction to the sized nozzle exit area.",
        True,
    ),
    ResultVariable(
        "dt_mm",
        "Throat Diameter [mm]",
        "sizing",
        "Circular-equivalent throat diameter from throat area.",
        True,
    ),
    ResultVariable(
        "de_mm",
        "Exit Diameter [mm]",
        "sizing",
        "Circular-equivalent exit diameter from exit area.",
        True,
    ),
    ResultVariable(
        "de_cm",
        "Exit Diameter [cm]",
        "sizing",
        "Circular-equivalent exit diameter from exit area.",
        True,
    ),
    ResultVariable(
        "exit_diameter_margin_cm",
        "Exit Diameter Margin [cm]",
        "sizing",
        "Remaining diameter margin against the configured maximum exit diameter.",
        True,
    ),
    ResultVariable(
        "exit_diameter_within_limit",
        "Exit Diameter Within Limit",
        "sizing",
        "Boolean flag indicating whether the sized exit diameter is within the configured maximum.",
    ),
]

CASE_FIELDS = [variable.key for variable in CASE_VARIABLES]
FAILURE_FIELDS = ["abs_vol_frac", "fuel_temp_k", "oxidizer_temp_k", "of", "ae_at", "reason"]
VARIABLE_LABELS = {variable.key: variable.label for variable in CASE_VARIABLES}

METRIC_OPTIONS = [variable.key for variable in CASE_VARIABLES if variable.plot_metric]
