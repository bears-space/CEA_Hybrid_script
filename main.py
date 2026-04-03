import math
import numpy as np
import cea

# ============================================================
# USER SETTINGS
# ============================================================
TARGET_THRUST_N = 3000.0
PC_BAR = 30.0
AE_AT_VALUES = [4, 6, 8, 10, 12, 15, 20]
OF_VALUES = np.linspace(2.0, 12.0, 41)

# Requested ABS volume fractions
ABS_VOL_FRACS = [0.10, 0.15, 0.20]

# First-cut reactant temperatures [K]
T_OX_K = 293.15
T_FUEL_K = 293.15

# Species names for stock NASA CEA thermo database
OX_NAME = "N2O"
FUEL_MAIN_NAME = "C2H4"              # paraffin surrogate
STYRENE_NAME = "C8H8,styrene"       # ABS surrogate part
BUTADIENE_NAME = "C4H6,butadiene"   # ABS surrogate part

# Representative densities [g/cm^3] for volume->mass conversion
RHO_PARAFFIN = 0.93
RHO_ABS = 1.05

# Rough ABS surrogate split, normalized over styrene + butadiene only
# This is a first-cut engineering surrogate, not full ABS chemistry.
STYRENE_SHARE = 55.0 / (55.0 + 20.0)
BUTADIENE_SHARE = 20.0 / (55.0 + 20.0)

IAC = True


# ============================================================
# HELPERS
# ============================================================
def abs_mass_fraction_from_volume_fraction(phi_abs, rho_abs=RHO_ABS, rho_paraffin=RHO_PARAFFIN):
    """
    Convert ABS volume fraction to ABS mass fraction using density.
    phi_abs: ABS volume fraction [0..1]
    """
    m_abs = rho_abs * phi_abs
    m_par = rho_paraffin * (1.0 - phi_abs)
    return m_abs / (m_abs + m_par)


def run_case(abs_vol_frac, of_ratio, ae_at, pc_bar):
    """
    Runs one equilibrium rocket case and back-solves the mdot and nozzle areas
    needed for the target thrust.
    """
    w_abs = abs_mass_fraction_from_volume_fraction(abs_vol_frac)
    w_par = 1.0 - w_abs

    # Split ABS surrogate into styrene + butadiene
    w_sty = w_abs * STYRENE_SHARE
    w_but = w_abs * BUTADIENE_SHARE

    reac_names = [FUEL_MAIN_NAME, STYRENE_NAME, BUTADIENE_NAME, OX_NAME]
    T_reactant = np.array([T_FUEL_K, T_FUEL_K, T_FUEL_K, T_OX_K], dtype=float)

    # Fuel-side weights define the relative composition of the total fuel mixture
    fuel_weights = np.array([w_par, w_sty, w_but, 0.0], dtype=float)
    oxidizer_weights = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

    reac = cea.Mixture(reac_names)
    prod = cea.Mixture(reac_names, products_from_reactants=True)

    solver = cea.RocketSolver(prod, reactants=reac)
    solution = cea.RocketSolution(solver)

    # Convert overall O/F into total reactant weights
    weights = reac.of_ratio_to_weights(oxidizer_weights, fuel_weights, of_ratio)

    # Chamber reactant enthalpy, following NASA sample pattern
    hc = reac.calc_property(cea.ENTHALPY, weights, T_reactant) / cea.R

    # This CEA version requires pi_p to be non-empty, even if supar is used
    pi_p = [100.0]

    solver.solve(
        solution,
        weights,
        pc_bar,
        pi_p,
        supar=[float(ae_at)],
        hc=hc,
        iac=IAC
    )

    if not solution.converged:
        return None

    CHAMBER = 0
    EXIT = -1

    cf = float(solution.coefficient_of_thrust[EXIT])
    isp_mps = float(solution.Isp[EXIT])
    isp_vac_mps = float(solution.Isp_vacuum[EXIT])
    cstar = float(solution.c_star[CHAMBER])

    pc_pa = pc_bar * 1e5

    # Back-solve from target thrust
    at_m2 = TARGET_THRUST_N / (cf * pc_pa)
    mdot_total = TARGET_THRUST_N / isp_mps
    ae_m2 = ae_at * at_m2

    dt_m = math.sqrt(4.0 * at_m2 / math.pi)
    de_m = math.sqrt(4.0 * ae_m2 / math.pi)

    return {
        "abs_vol_frac": abs_vol_frac,
        "abs_mass_frac": w_abs,
        "of": of_ratio,
        "pc_bar": pc_bar,
        "ae_at": ae_at,
        "cf": cf,
        "isp_mps": isp_mps,
        "isp_vac_mps": isp_vac_mps,
        "isp_s": isp_mps / 9.80665,
        "isp_vac_s": isp_vac_mps / 9.80665,
        "cstar_mps": cstar,
        "tc_k": float(solution.T[CHAMBER]),
        "pe_bar": float(solution.P[EXIT]),
        "te_k": float(solution.T[EXIT]),
        "mach_e": float(solution.Mach[EXIT]),
        "gamma_e": float(solution.gamma_s[EXIT]),
        "mw_e": float(solution.MW[EXIT]),
        "mdot_total_kg_s": mdot_total,
        "at_m2": at_m2,
        "ae_m2": ae_m2,
        "dt_mm": dt_m * 1e3,
        "de_mm": de_m * 1e3,
    }


# ============================================================
# MAIN
# ============================================================
print(f"Target thrust = {TARGET_THRUST_N:.1f} N")
print(f"Chamber pressure = {PC_BAR:.2f} bar")
print(f"Oxidizer = {OX_NAME}, Fuel = {FUEL_MAIN_NAME} + ABS surrogate")
print()

for abs_phi in ABS_VOL_FRACS:
    print("=" * 110)
    print(f"ABS volume fraction = {100 * abs_phi:.1f}%")
    print(f"ABS mass fraction   = {100 * abs_mass_fraction_from_volume_fraction(abs_phi):.2f}%")
    print("=" * 110)

    print(
        f"{'Ae/At':>6}  {'Best O/F':>8}  {'Isp [s]':>10}  {'Isp_vac [s]':>12}  "
        f"{'Cf':>8}  {'mdot [kg/s]':>12}  {'dt [mm]':>10}  {'de [mm]':>10}  "
        f"{'Tc [K]':>10}  {'Pe [bar]':>10}"
    )

    for ae_at in AE_AT_VALUES:
        best = None

        for of_ratio in OF_VALUES:
            try:
                r = run_case(abs_phi, of_ratio, ae_at, PC_BAR)
            except Exception as e:
                print(f"Ae/At={ae_at}, O/F={of_ratio:.2f} failed: {e}")
                r = None

            if r is None:
                continue

            # Pick the best point by vacuum Isp for each Ae/At
            if (best is None) or (r["isp_vac_mps"] > best["isp_vac_mps"]):
                best = r

        if best is None:
            print(f"{ae_at:6.1f}  {'NO CONV':>8}")
            continue

        print(
            f"{best['ae_at']:6.1f}  "
            f"{best['of']:8.3f}  "
            f"{best['isp_s']:10.2f}  "
            f"{best['isp_vac_s']:12.2f}  "
            f"{best['cf']:8.4f}  "
            f"{best['mdot_total_kg_s']:12.4f}  "
            f"{best['dt_mm']:10.2f}  "
            f"{best['de_mm']:10.2f}  "
            f"{best['tc_k']:10.1f}  "
            f"{best['pe_bar']:10.4f}"
        )

    print()