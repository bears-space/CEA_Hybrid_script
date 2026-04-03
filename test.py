import numpy as np
import cea

reac_names = ["C2H4", "N2O"]
T_reactant = np.array([293.15, 293.15])

fuel_weights = np.array([1.0, 0.0])
oxidizer_weights = np.array([0.0, 1.0])

of_ratio = 6.0
pc = 30.0
ae_at = 8.0

reac = cea.Mixture(reac_names)
prod = cea.Mixture(reac_names, products_from_reactants=True)

solver = cea.RocketSolver(prod, reactants=reac)
solution = cea.RocketSolution(solver)

weights = reac.of_ratio_to_weights(oxidizer_weights, fuel_weights, of_ratio)
hc = reac.calc_property(cea.ENTHALPY, weights, T_reactant) / cea.R

pi_p = [100.0]   # required by this CEA version, even when using supar
solver.solve(solution, weights, pc, pi_p, supar=[ae_at], hc=hc, iac=True)

EXIT = -1

print("Converged:", solution.converged)
print("num_pts:", solution.num_pts)
print("Ae/At [-]:", solution.ae_at[EXIT])
print("Isp [m/s]:", solution.Isp[EXIT])
print("Cf [-]:", solution.coefficient_of_thrust[EXIT])
print("Pe [bar]:", solution.P[EXIT])
print("Te [K]:", solution.T[EXIT])