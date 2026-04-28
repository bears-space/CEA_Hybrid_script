# Canonical Sizing Formulas

This file keeps the governing sizing equations separate from the Python implementation.

All variable comments use full names.

## Shell, Liner, And Hot-Gas Radii

```text
# shell_inner_radius = shell inner radius [m]
# shell_wall_thickness = shell wall thickness [m]
# liner_thickness = inner phenolic liner thickness [m]
# shell_outer_radius = shell outer radius [m]
# hot_gas_radius = hot-gas radius [m]

shell_outer_radius = shell_inner_radius + shell_wall_thickness
hot_gas_radius = shell_inner_radius - liner_thickness

# shell_inner_diameter = shell inner diameter [m]
# shell_outer_diameter = shell outer diameter [m]
# hot_gas_diameter = hot-gas diameter [m]

shell_inner_diameter = 2 * shell_inner_radius
shell_outer_diameter = 2 * shell_outer_radius
hot_gas_diameter = 2 * hot_gas_radius
```

## Grain Geometry

```text
# radial_clearance = radial clearance between hot-gas wall and grain outer radius [m]
# grain_outer_radius = grain outer radius [m]
# grain_port_radius_initial = initial grain-port radius [m]
# grain_port_radius_final = final grain-port radius [m]
# grain_length = grain axial length [m]
# fuel_density = effective bulk fuel density [kg/m^3]
# loaded_fuel_mass = loaded fuel mass at ignition [kg]
# remaining_fuel_mass = remaining fuel mass at burn end [kg]

grain_outer_radius = hot_gas_radius - radial_clearance

loaded_fuel_volume =
    pi
    * grain_length
    * (grain_outer_radius - grain_port_radius_initial)^2

loaded_fuel_mass = fuel_density * loaded_fuel_volume

grain_port_radius_initial =
    sqrt(
        max(
            grain_outer_radius^2
            - loaded_fuel_mass / (fuel_density * pi * grain_length),
            0
        )
    )

grain_port_radius_final =
    sqrt(
        max(
            grain_outer_radius^2
            - remaining_fuel_mass / (fuel_density * pi * grain_length),
            0
        )
    )
```

## Web Thickness And Slenderness

```text
# initial_web_thickness = initial radial web thickness [m]
# final_web_thickness = final radial web thickness [m]
# grain_slenderness = grain length divided by grain diameter [-]
# web_slenderness = grain length divided by twice the initial web thickness [-]

initial_web_thickness = grain_outer_radius - grain_port_radius_initial
final_web_thickness = grain_outer_radius - grain_port_radius_final

grain_slenderness = grain_length / (2 * grain_outer_radius)
web_slenderness = grain_length / (2 * initial_web_thickness)
```

## Chamber Lengths

```text
# prechamber_length = pre-combustion chamber length [m]
# postchamber_length = post-combustion chamber length [m]
# total_internal_chamber_length = total internal chamber length [m]

total_internal_chamber_length =
    prechamber_length
    + grain_length
    + postchamber_length
```

## Characteristic Length

```text
# throat_radius = throat radius [m]
# throat_area = throat area [m^2]
# prechamber_free_volume = prechamber free volume [m^3]
# port_free_volume_initial = initial port free volume [m^3]
# postchamber_free_volume = postchamber free volume [m^3]
# chamber_free_volume_initial = ignition free volume [m^3]
# characteristic_length_initial = ignition characteristic length [m]

throat_area = pi * throat_radius^2

prechamber_free_volume = pi * hot_gas_radius^2 * prechamber_length
port_free_volume_initial = pi * grain_port_radius_initial^2 * grain_length
postchamber_free_volume = pi * hot_gas_radius^2 * postchamber_length

chamber_free_volume_initial =
    prechamber_free_volume
    + port_free_volume_initial
    + postchamber_free_volume

characteristic_length_initial = chamber_free_volume_initial / throat_area
```

## Minimum Grain Length From Required Fuel Mass

```text
# required_fuel_mass = required consumed fuel mass [kg]
# minimum_initial_web_thickness = minimum allowed initial web thickness [m]
# largest_allowed_initial_port_radius = largest allowed initial port radius at the minimum web [m]
# maximum_annulus_area_at_ignition = maximum annulus area at ignition while satisfying the minimum web [m^2]
# minimum_grain_length_from_required_fuel_mass = minimum possible grain length for the chosen radius [m]

largest_allowed_initial_port_radius = grain_outer_radius - minimum_initial_web_thickness

maximum_annulus_area_at_ignition =
    pi
    * (grain_outer_radius^2 - largest_allowed_initial_port_radius^2)

minimum_grain_length_from_required_fuel_mass =
    required_fuel_mass
    / (fuel_density * maximum_annulus_area_at_ignition)
```

## Conical Nozzle With Finite Throat Blend

```text
# exit_radius = exit radius [m]
# area_expansion_ratio = exit area divided by throat area [-]
# converging_half_angle = converging half-angle [rad]
# diverging_half_angle = diverging half-angle [rad]
# chamber_side_converging_entry_radius = chamber-side entry radius for the converging section [m]
# converging_length = conical converging axial length [m]
# diverging_length = conical diverging axial length [m]
# total_nozzle_length = total axial nozzle length [m]

area_expansion_ratio = (exit_radius / throat_radius)^2
exit_radius = throat_radius * sqrt(area_expansion_ratio)

converging_length =
    max(
        0,
        (chamber_side_converging_entry_radius - throat_radius)
        / tan(converging_half_angle)
    )

diverging_length =
    max(
        0,
        (exit_radius - throat_radius)
        / tan(diverging_half_angle)
    )

total_nozzle_length = converging_length + diverging_length
```

## Injector Hole Count And Total Area

```text
# oxidizer_mass_flow_rate = oxidizer mass flow rate [kg/s]
# injector_discharge_coefficient = injector discharge coefficient [-]
# oxidizer_density = upstream oxidizer density [kg/m^3]
# injector_pressure_drop = injector pressure drop [Pa]
# injector_hole_diameter = user-selected fixed injector-hole diameter [m]
# single_injector_hole_area = area of one injector hole [m^2]
# required_injector_total_area = required injector total flow area before integer rounding [m^2]
# injector_hole_count = integer injector hole count [-]
# actual_injector_total_area = realized total injector area after rounding [m^2]

single_injector_hole_area = pi * injector_hole_diameter^2 / 4

required_injector_total_area =
    oxidizer_mass_flow_rate
    /
    (
        injector_discharge_coefficient
        * sqrt(2 * oxidizer_density * injector_pressure_drop)
    )

injector_hole_count =
    ceil(required_injector_total_area / single_injector_hole_area)

actual_injector_total_area =
    injector_hole_count
    * single_injector_hole_area
```

## Thin-Wall Structural Sizing

```text
# chamber_pressure = chamber pressure [Pa]
# allowable_shell_stress = allowable shell stress [Pa]
# hoop_stress = thin-wall hoop stress [Pa]
# axial_stress = thin-wall axial stress [Pa]
# required_shell_thickness = required thin-wall shell thickness [m]

hoop_stress = chamber_pressure * shell_inner_radius / shell_wall_thickness
axial_stress = chamber_pressure * shell_inner_radius / (2 * shell_wall_thickness)

required_shell_thickness =
    chamber_pressure
    * shell_inner_radius
    / allowable_shell_stress
```

## Multilayer Cylindrical Thermal Resistance

```text
# gas_side_heat_transfer_coefficient = gas-side heat transfer coefficient [W/m^2/K]
# outer_side_heat_transfer_coefficient = outer-side heat transfer coefficient [W/m^2/K]
# liner_conductivity = liner thermal conductivity [W/m/K]
# shell_conductivity = shell thermal conductivity [W/m/K]
# gas_temperature = effective hot-gas temperature [K]
# ambient_temperature = outside sink temperature [K]
# shell_inner_interface_radius = radius at liner-shell interface [m]
# shell_outer_surface_radius = shell outer radius for thermal analysis [m]
# gas_side_convection_resistance = gas-side convection resistance [K/W]
# liner_conduction_resistance = liner conduction resistance [K/W]
# shell_conduction_resistance = shell conduction resistance [K/W]
# outer_side_convection_resistance = outer-side convection resistance [K/W]
# total_thermal_resistance = total thermal resistance [K/W]
# heat_flow_rate = total heat flow through the cylindrical segment [W]
# gas_side_heat_flux = gas-side heat flux [W/m^2]
# hot_wall_temperature = hot-wall temperature [K]
# liner_shell_interface_temperature = liner-shell interface temperature [K]
# outer_shell_temperature = outer shell temperature [K]

shell_inner_interface_radius = hot_gas_radius + liner_thickness
shell_outer_surface_radius = shell_inner_interface_radius + shell_wall_thickness

gas_side_convection_resistance =
    1
    /
    (gas_side_heat_transfer_coefficient * 2 * pi * hot_gas_radius * segment_length)

liner_conduction_resistance =
    ln(shell_inner_interface_radius / hot_gas_radius)
    /
    (2 * pi * liner_conductivity * segment_length)

shell_conduction_resistance =
    ln(shell_outer_surface_radius / shell_inner_interface_radius)
    /
    (2 * pi * shell_conductivity * segment_length)

outer_side_convection_resistance =
    1
    /
    (
        outer_side_heat_transfer_coefficient
        * 2
        * pi
        * shell_outer_surface_radius
        * segment_length
    )

total_thermal_resistance =
    gas_side_convection_resistance
    + liner_conduction_resistance
    + shell_conduction_resistance
    + outer_side_convection_resistance

heat_flow_rate = (gas_temperature - ambient_temperature) / total_thermal_resistance

gas_side_heat_flux =
    heat_flow_rate
    / (2 * pi * hot_gas_radius * segment_length)

hot_wall_temperature = gas_temperature - heat_flow_rate * gas_side_convection_resistance

liner_shell_interface_temperature =
    hot_wall_temperature
    - heat_flow_rate * liner_conduction_resistance

outer_shell_temperature =
    liner_shell_interface_temperature
    - heat_flow_rate * shell_conduction_resistance
```

## Requested Main Outputs

```text
# chamber diameter inner excluding liner = shell_inner_diameter
# chamber diameter outer excluding liner = shell_outer_diameter
# chamber diameter inner including liner = hot_gas_diameter
# chamber diameter outer including liner = shell_outer_diameter
# fuel diameter inner = 2 * grain_port_radius_initial
# fuel diameter outer = 2 * grain_outer_radius
# throat diameter = 2 * throat_radius
# exit diameter = 2 * exit_radius
# nozzle length = total_nozzle_length
# inner liner thickness = liner_thickness
# post combustion chamber length = postchamber_length
# pre combustion chamber length = prechamber_length
# converging throat section angle = converging half-angle
# injector hole count = injector_hole_count
# injector total hole area = actual_injector_total_area
```
