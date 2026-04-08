"""Shared constants and option keys for the blowdown model."""

G0_MPS2 = 9.80665
NITROUS_OXIDE_FLUID = "NitrousOxide"
N2O_T_MIN_K = 184.0
N2O_T_MAX_K = 309.0

SEED_CASE_HIGHEST_ISP = "highest_isp"

UI_MODE_BASIC = "basic"
UI_MODE_ADVANCED = "advanced"

INJECTOR_DELTA_P_MODE_EXPLICIT = "explicit"
INJECTOR_DELTA_P_MODE_FRACTION_OF_PC = "fraction_of_pc"

STOP_REASON_LABELS = {
    "burn_time_reached": "Burn time reached.",
    "tank_quality_limit_exceeded": "Tank quality limit exceeded; vapor ingestion is likely.",
    "port_radius_reached_outer_radius": "Port radius reached the configured outer radius.",
    "tank_depleted": "Tank mass reached zero.",
}

MODEL_ASSUMPTIONS = [
    "The highest-Isp converged CEA case is used as a single steady design seed for the transient 0D blowdown run.",
    "Tank thermodynamics assume a rigid, adiabatic, saturated two-phase nitrous tank in equilibrium.",
    "The tank model assumes liquid draw only and stops once vapor quality reaches the configured cutoff.",
    "Nitrous properties are taken from CoolProp saturation states within the hardcoded 184 K to 309 K search range.",
    "In basic mode, first-pass tank sizing estimates loaded oxidizer mass from target burn time and computes tank volume from liquid density and initial fill fraction.",
    "Feed losses are reduced to a lumped Darcy-plus-minor-loss model with fixed friction factor and fixed total K.",
    "Injector flow uses an incompressible single-phase orifice equation with fixed Cd and no flashing or two-phase correction.",
    "Injector total area is first estimated from oxidizer flow, liquid density, Cd, and either an explicit injector delta-p or a chosen fraction of chamber pressure.",
    "Fuel blend density is estimated from the seeded CEA ABS volume fraction and the configured ABS/paraffin material densities.",
    "Grain regression uses a fixed empirical law rdot = a * Gox^n with constant user-provided coefficients.",
    "Initial port radius is estimated from the target initial oxidizer flux and the seeded oxidizer design flow.",
    "Grain length is estimated from target fuel mass flow, blend density, initial port diameter, and the initial regression rate.",
    "Outer grain radius is estimated from loaded fuel mass, blend density, initial port radius, and grain length.",
    "Port growth is treated uniformly across all ports with no axial, circumferential, or erosive-burning nonuniformity model.",
    "Chamber pressure is inferred from mdot_total * c* / At using the CEA-seeded throat area and a constant c*.",
    "Thrust is inferred from Cf * Pc * At using a constant CEA-seeded Cf for the entire transient run.",
    "The ambient-pressure input is not currently used to recompute a time-varying nozzle correction during the transient thrust solve.",
    "No finite-rate chemistry, combustion-efficiency correction, heat-transfer model, structural response, or injector transient is resolved.",
    "The result is a preliminary 0D system model intended for first-pass sizing trends, not a high-fidelity flight prediction.",
]
