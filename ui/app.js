const palette = ["#0f766e", "#b86a2d", "#345c7c", "#7c5aa6", "#a3475d", "#5c7f37", "#2d8d88", "#9a6742", "#536a7a"];
const THEME_STORAGE_KEY = "ceaHybridTheme";
const state = {
  defaults: null,
  results: null,
  blowdownPreview: null,
  pollTimer: null,
  previewTimer: null,
  renderedJobId: null,
  renderedResultKey: null,
  lastStatusKey: null,
  downloadUrls: [],
  chartConfigs: {},
  activeMetric: null,
};

const BLOWDOWN_FORMULA_HINTS = {
  seed_target_thrust_n: "From the latest highest-Isp CEA case target thrust input.",
  seed_isp_s: "From the latest highest-Isp CEA case specific impulse.",
  seed_of_ratio: "From the latest highest-Isp CEA case O/F ratio.",
  seed_pc_bar: "From the latest highest-Isp CEA case chamber pressure.",
  seed_oxidizer_temp_k: "From the latest highest-Isp CEA case oxidizer temperature. The blowdown tank temperature follows the main oxidizer temperature input.",
  seed_fuel_temp_k: "From the latest highest-Isp CEA case fuel temperature.",
  seed_abs_volume_fraction: "From the latest highest-Isp CEA case ABS volume fraction.",
  seed_abs_mass_fraction: "ABS mass fraction = (phi_abs * rho_abs) / (phi_abs * rho_abs + (1 - phi_abs) * rho_paraffin).",
  target_mdot_total_kg_s: "mdot_total = target_thrust / (g0 * Isp).",
  target_mdot_ox_kg_s: "mdot_ox = (O/F) / (1 + O/F) * mdot_total.",
  target_mdot_f_kg_s: "mdot_f = mdot_total / (1 + O/F).",
  required_oxidizer_mass_kg: "m_ox_required = mdot_ox * burn_time.",
  loaded_oxidizer_mass_kg: "m_ox_loaded = m_ox_required / usable_oxidizer_fraction.",
  required_fuel_mass_kg: "m_f_required = mdot_f * burn_time.",
  loaded_fuel_mass_kg: "m_f_loaded = m_f_required / fuel_usable_fraction.",
  fuel_density_kg_m3: "rho_fuel = 1 / (phi_abs / rho_abs + (1 - phi_abs) / rho_paraffin).",
  tank_oxidizer_liquid_volume_l: "V_ox_liquid = m_ox_loaded / rho_ox_liq(T_ox).",
  tank_volume_l: "V_tank = m_ox_loaded / (rho_ox_liq(T_ox) * initial_fill_fraction).",
  tank_initial_mass_kg: "Loaded oxidizer mass from burn time, O/F, Isp, and usable oxidizer fraction unless a manual tank override is active.",
  tank_initial_temp_k: "Uses the main oxidizer temperature input. Saturated N2O pressure and liquid density are evaluated at this temperature.",
  tank_initial_pressure_bar: "p_tank,0 = p_sat_n2o(T_ox).",
  tank_usable_fraction_source: "Basic mode uses a project-default usable oxidizer fraction. Advanced mode uses the expert-entered value.",
  regression_preset: "Basic mode selects a project regression preset. Custom uses the advanced a and n values.",
  regression_a_si: "Regression coefficient used by the first-pass grain estimate. In basic mode this usually comes from the selected preset.",
  regression_n: "Regression exponent used by the first-pass grain estimate. In basic mode this usually comes from the selected preset.",
  regression_source: "Shows whether regression coefficients came from a preset or from advanced manual inputs.",
  port_count: "Port count used by the first-pass grain estimate. Basic mode uses a project default unless advanced mode is active.",
  port_count_source: "Shows whether port count came from the basic project default or advanced manual input.",
  initial_port_area_mm2: "A_port,0 = mdot_ox / target_initial_gox.",
  initial_port_radius_mm: "R_port,0 = 0.5 * sqrt(4 * mdot_ox / (pi * N_ports * Gox_0)).",
  initial_regression_rate_mm_s: "rdot_0 = a * Gox_0^n.",
  grain_length_m: "Lg = mdot_f / (rho_f * N_ports * pi * D_port,0 * rdot_0).",
  grain_outer_radius_mm: "R_outer = sqrt(R_port,0^2 + V_fuel / (N_ports * pi * Lg)).",
  fuel_usable_fraction_source: "Basic mode uses a project-default fuel usable fraction. Advanced mode uses the expert-entered value.",
  injector_pressure_drop_policy: "Basic mode uses a simple project pressure-drop policy that maps to a fraction of chamber pressure.",
  injector_delta_p_bar: "Either explicit injector delta-p or injector_delta_p_fraction_of_pc * Pc.",
  injector_delta_p_source: "Shows whether injector delta-p came from the simple policy or from advanced manual settings.",
  injector_cd_source: "Basic mode uses a project-default injector Cd. Advanced mode uses the expert-entered value.",
  injector_hole_count_source: "Basic mode uses a project-default injector hole count. Advanced mode uses the expert-entered value.",
  injector_total_area_mm2: "A_inj = mdot_ox / (Cd * sqrt(2 * rho_ox_liq(T_ox) * dP_inj)).",
  injector_area_per_hole_mm2: "Injector total area divided evenly by hole count.",
  injector_hole_diameter_mm: "Equivalent hole diameter = sqrt(4 * A_inj_total / (pi * N_holes)).",
  tank_mass_volume_source: "Shows whether tank mass/volume are auto-derived or manually overridden.",
  injector_total_area_source: "Shows whether injector total area is auto-derived or manually overridden.",
  initial_port_source: "Shows whether initial port radius is auto-derived or manually overridden.",
  grain_length_source: "Shows whether grain length is auto-derived or manually overridden.",
  outer_radius_source: "Shows whether outer grain radius is auto-derived or manually overridden.",
};

const INPUT_FIELD_HINTS = {
  target_thrust_n: "Requested thrust used for post-CEA nozzle sizing and blowdown first-pass sizing.",
  max_exit_diameter_cm: "Maximum allowed nozzle exit diameter when the sweep is capped by exit size.",
  pc_bar: "Chamber pressure passed directly into the NASA CEA rocket calculation.",
  desired_infill_percent: "ABS infill percentage mapped into the ABS volume-fraction input for the propellant model.",
  ae_at_cap_mode: "Chooses whether the Ae/At sweep stops at an exit-diameter limit or a direct area-ratio limit.",
  max_area_ratio: "Maximum nozzle expansion ratio allowed when cap mode is set to area ratio.",
  ae_at_custom_enabled: "Enables a manually defined Ae/At sweep instead of the default start, stop, and step behavior.",
  ae_at_start: "First Ae/At value included in the custom area-ratio sweep.",
  ae_at_stop: "Last Ae/At value included in the custom area-ratio sweep.",
  ae_at_step: "Increment between consecutive Ae/At samples in the custom sweep.",
  of_start: "Lowest oxidizer-to-fuel mass ratio evaluated in the sweep.",
  of_stop: "Highest oxidizer-to-fuel mass ratio evaluated in the sweep.",
  of_count: "Number of O/F sample points generated between the start and stop values.",
  fuel_temperature_k: "Fuel temperature supplied to CEA for the paraffin and ABS mixture.",
  oxidizer_temperature_k: "Oxidizer temperature supplied to CEA and reused as the blowdown tank temperature basis.",
  blowdown_tank_usable_oxidizer_fraction: "Fraction of loaded oxidizer assumed usable before the run is considered depleted.",
  blowdown_grain_fuel_usable_fraction: "Fraction of loaded fuel assumed available for the first-pass grain estimate.",
  blowdown_grain_a_reg_si: "Empirical regression coefficient used in the initial hybrid regression-rate estimate.",
  blowdown_grain_n_reg: "Empirical regression exponent used with oxidizer mass flux in the first-pass estimate.",
  blowdown_grain_port_count: "Number of fuel ports assumed in the preliminary grain geometry estimate.",
  blowdown_injector_cd: "Injector discharge coefficient used to convert required flow into injector area.",
  blowdown_injector_hole_count: "Number of injector holes used to split total injector area into per-hole size.",
  blowdown_injector_delta_p_mode: "Defines injector sizing pressure drop as either an explicit value or a fraction of chamber pressure.",
  blowdown_injector_delta_p_pa: "Explicit injector pressure-drop target used when delta-p mode is set to explicit.",
  blowdown_injector_delta_p_fraction_of_pc: "Injector pressure-drop fraction multiplied by chamber pressure when using fraction mode.",
  blowdown_tank_volume_l: "Manual oxidizer tank volume override for the preliminary blowdown model.",
  blowdown_tank_initial_mass_kg: "Manual initial oxidizer mass override for the preliminary blowdown model.",
  blowdown_tank_override_mass_volume: "When enabled, the solver uses the manually entered tank mass and volume instead of auto-derived values.",
  blowdown_injector_total_area_mm2: "Manual total injector flow area override used instead of the first-pass estimate.",
  blowdown_injector_override_total_area: "When enabled, the solver uses the manual injector total area.",
  blowdown_grain_initial_port_radius_mm: "Manual initial port radius override for the grain geometry.",
  blowdown_grain_length_m: "Manual grain length override for the fuel geometry.",
  blowdown_grain_outer_radius_mm: "Manual outer grain radius override for the fuel geometry.",
  blowdown_grain_override_initial_port_radius: "When enabled, the solver uses the manual initial port radius.",
  blowdown_grain_override_grain_length: "When enabled, the solver uses the manual grain length.",
  blowdown_grain_override_outer_radius: "When enabled, the solver uses the manual outer grain radius.",
  blowdown_feed_line_id_mm: "Equivalent feed-line inner diameter used for lumped line-loss calculations.",
  blowdown_feed_line_length_m: "Equivalent feed-line length used for transient pressure-loss calculations.",
  blowdown_feed_friction_factor: "Lumped Darcy friction factor used across the equivalent feed line.",
  blowdown_feed_minor_loss_k_total: "Total minor-loss coefficient representing valves, bends, and fittings in the feed path.",
  blowdown_sim_dt_s: "Time step used by the transient blowdown integrator.",
  blowdown_sim_ambient_pressure_bar: "Ambient pressure used to estimate delivered thrust from the transient chamber state.",
  blowdown_sim_max_inner_iterations: "Maximum solver iterations allowed per time step before moving on or failing convergence.",
  blowdown_sim_relaxation: "Relaxation factor applied to stabilize the transient inner iteration updates.",
  blowdown_sim_relative_tolerance: "Relative convergence tolerance used inside each blowdown time step.",
  blowdown_sim_stop_quality: "Tank vapor-quality cutoff used as an end condition for the blowdown run.",
  blowdown_ui_mode: "Switches between basic high-level sizing and advanced manual override controls.",
  blowdown_auto_run_after_cea: "Automatically starts the preliminary blowdown run after a CEA sweep completes.",
  blowdown_sim_burn_time_s: "Requested burn duration used to size required oxidizer and fuel loading.",
  blowdown_tank_initial_fill_fraction: "Initial liquid fill fraction assumed for the oxidizer tank sizing estimate.",
  blowdown_grain_target_initial_gox_kg_m2_s: "Target initial oxidizer mass flux used to back out the starting port area.",
  blowdown_injector_pressure_drop_policy: "Basic-mode policy that selects a project-default injector pressure-drop level.",
  blowdown_grain_regression_preset: "Selects the baseline fuel/regression model preset used in basic mode.",
  selected_metric: "Chooses which preloaded sweep metric is shown in the main O/F chart without rerunning CEA.",
};

const CASE_FIELD_HINTS = {
  target_thrust_n: "Target engine thrust for the selected case. The workflow uses it to back out the required total mass flow and then size the throat and first-pass propellant loading around that demand.",
  pc_bar: "Chamber pressure for the selected case. In this project it is a chosen system-level design input that is passed into CEA and then reused by the sizing logic; it is not automatically optimized by CEA.",
  abs_vol_frac: "ABS structural fraction expressed as a volume fraction within the paraffin-based fuel grain model. This changes the effective fuel density and the surrogate chemistry passed into CEA.",
  fuel_temp_k: "Fuel-side reactant temperature used in the CEA evaluation for this case. It influences the thermochemical state and is separate from the oxidizer tank temperature input.",
  oxidizer_temp_k: "Oxidizer-side reactant temperature used in CEA. In the coupled workflow this also serves as the basis for the preliminary blowdown tank temperature when the 0D model is seeded from CEA.",
  of: "Oxidizer-to-fuel mass ratio for the case. It sets how the total propellant flow is split between oxidizer and fuel and strongly affects c*, Isp, flame temperature, and the first-pass grain sizing.",
  ae_at: "Nozzle expansion ratio, equal to exit area divided by throat area. Larger values generally increase vacuum performance but also increase exit diameter and can over-expand at sea level.",
  isp_s: "Specific impulse in seconds for the selected CEA rocket solution at the reported operating condition. This is the thrust-normalized performance number used directly in the first-pass mass-flow sizing.",
  isp_vac_s: "Vacuum specific impulse in seconds for the same case. It shows the idealized performance if the nozzle expanded into vacuum instead of sea-level ambient conditions.",
  cf: "Thrust coefficient from the CEA rocket solution. It converts chamber pressure and throat area into thrust and captures the nozzle expansion contribution separately from c*.",
  cstar_mps: "Characteristic velocity predicted by CEA in meters per second. This is the combustion-performance term used in the project’s chamber-pressure closure and throat sizing logic.",
  tc_k: "Predicted chamber temperature from the equilibrium CEA solution. This is a useful first-pass indicator for thermal loading and gas-property trends.",
  mach_t: "Mach number at the throat station from the CEA nozzle solution. For a healthy choked nozzle this should be near unity.",
  pe_bar: "Predicted nozzle exit static pressure. Comparing this with ambient pressure helps judge under-expansion or over-expansion for the chosen area ratio.",
  te_k: "Predicted nozzle exit static temperature from CEA. It is lower than chamber temperature because the flow expands through the nozzle.",
  mach_e: "Predicted nozzle exit Mach number. Higher values indicate stronger expansion through the nozzle.",
  gamma_e: "Ratio of specific heats at the nozzle exit. This is one of the gas-property outputs later useful for higher-fidelity nozzle or internal-ballistics work.",
  mw_e: "Effective molecular weight of the exhaust at the nozzle exit. Lower molecular weight generally supports higher exhaust velocity and Isp.",
  isp_mps: "Specific impulse converted into effective exhaust velocity in meters per second. It is the same performance quantity as Isp, just expressed in velocity form.",
  isp_vac_mps: "Vacuum specific impulse converted into effective exhaust velocity in meters per second.",
  abs_mass_frac: "ABS structural fraction expressed as a mass fraction after converting from the chosen volume fraction and component densities.",
  mdot_total_kg_s: "Total propellant mass flow required to hit the target thrust at the reported Isp. This is the combined oxidizer-plus-fuel flow through the engine.",
  at_m2: "Required nozzle throat area for the selected mass flow, chamber pressure, and c*. This is the choked-flow sizing quantity used to freeze the throat dimension.",
  ae_m2: "Nozzle exit area implied by the throat area and the selected expansion ratio Ae/At.",
  thrust_sl_n: "Estimated delivered thrust at standard sea-level ambient pressure for this case after applying the current nozzle sizing assumptions.",
  dt_mm: "Circular-equivalent throat diameter computed from the throat area. This is the first-pass geometric throat dimension rather than a detailed contour.",
  de_mm: "Circular-equivalent nozzle exit diameter computed from the exit area.",
  de_cm: "Same nozzle exit diameter as above, reported in centimeters for quick comparison against packaging limits.",
  exit_diameter_margin_cm: "Margin between the configured maximum exit diameter and the current case’s nozzle exit diameter. Positive values mean the case still fits inside the limit.",
  exit_diameter_within_limit: "Boolean packaging check showing whether the current nozzle exit diameter stays within the configured exit-diameter cap.",
};

const STATIC_LABEL_HINTS = {
  "Regression Preset": "This label explains how the selected regression preset supplies the baseline regression coefficients used by the first-pass hybrid grain estimate. If you switch the preset to Custom, the advanced a and n inputs become the active source instead.",
  "Injector Policy": "This label explains that the basic-mode injector policy is the high-level control for preliminary injector pressure-drop sizing. In advanced mode you can replace that shortcut with explicit injector delta-p settings.",
  "Tank State Basis": "This label explains that oxidizer tank temperature sets the saturated nitrous starting state, including initial tank pressure and liquid density. Manual tank mass or volume overrides do not change that thermodynamic basis.",
  "CEA Seed": "This label explains which values are inherited from the currently selected highest-Isp converged CEA case when the preliminary blowdown model is seeded automatically.",
  "Hidden Basic Defaults": "This label groups lower-level parameters that remain on project defaults while the UI is in basic mode. They still affect the first-pass sizing, but they are intentionally hidden until advanced mode is enabled.",
};

function $(id) {
  return document.getElementById(id);
}

const INTEGER_INPUT_IDS = new Set([
  "of_count",
  "blowdown_injector_hole_count",
  "blowdown_grain_port_count",
  "blowdown_sim_max_inner_iterations",
]);

function configureNumericInputs() {
  document.querySelectorAll("#sweepForm input[type='number']").forEach((node) => {
    const isInteger = INTEGER_INPUT_IDS.has(node.id);
    node.dataset.numericInput = "true";
    if (isInteger) {
      node.dataset.integerInput = "true";
    }
    node.type = "text";
    node.inputMode = isInteger ? "numeric" : "decimal";
    node.autocomplete = "off";
    node.spellcheck = false;
  });
}

function normalizeNumericText(value) {
  return String(value ?? "")
    .trim()
    .replace(/\s+/g, "")
    .replace(/,/g, ".");
}

function parseNumericInput(id, label, { integer = false, allowBlank = false } = {}) {
  const raw = $(id).value;
  const normalized = normalizeNumericText(raw);

  if (!normalized) {
    if (allowBlank) {
      return null;
    }
    throw new Error(`${label} is required.`);
  }

  const value = Number(normalized);
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be a valid number.`);
  }
  if (integer && !Number.isInteger(value)) {
    throw new Error(`${label} must be an integer.`);
  }
  return value;
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  const text = Number(value).toFixed(digits);
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function prettyBlowdownString(key, value) {
  const mappings = {
    regression_preset: {
      project_default_paraffin_abs: "Paraffin + ABS baseline (Project Default)",
      custom: "Custom",
    },
    injector_pressure_drop_policy: {
      low: "Low",
      nominal: "Nominal",
      conservative: "Conservative",
    },
    injector_delta_p_mode: {
      explicit: "Explicit",
      fraction_of_pc: "Fraction of Pc",
      policy_fraction_of_pc: "Policy fraction of Pc",
    },
  };
  if (mappings[key]?.[value]) {
    return mappings[key][value];
  }
  if (key.endsWith("_source")) {
    return String(value).replaceAll("_", " ");
  }
  return value;
}

function infoDot(text, label = "More information") {
  return `<button class="info-dot" type="button" data-tip="${escapeHtml(text)}" aria-label="${escapeHtml(label)}">i</button>`;
}

function labelWithTip(label, tipText, labelText) {
  return `${escapeHtml(label)} ${infoDot(tipText, labelText || `Explain ${label}`)}`;
}

function humanizeFieldKey(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .replace(/\bkg\b/g, "kg")
    .replace(/\bm2\b/g, "m^2")
    .replace(/\bmm2\b/g, "mm^2")
    .replace(/\bsi\b/g, "SI")
    .replace(/\bpc\b/gi, "chamber pressure")
    .trim();
}

function genericFieldHint(key, label = "") {
  const name = label.replace(/\s+/g, " ").trim() || humanizeFieldKey(key);
  return `This value reports ${name.toLowerCase()} for the current case. It is exposed by the active CEA or blowdown workflow output and is shown here for inspection and comparison, not as a manually entered design input.`;
}

function hintForCaseField(key, label = "") {
  return BLOWDOWN_FORMULA_HINTS[key] || CASE_FIELD_HINTS[key] || genericFieldHint(key, label);
}

function tooltipTextForInput(id, labelText = "") {
  const cleanLabel = labelText.replace(/\s+/g, " ").trim();
  if (INPUT_FIELD_HINTS[id]) {
    return `This input controls ${cleanLabel.toLowerCase()} for the current analysis. ${INPUT_FIELD_HINTS[id]}`;
  }
  if (!cleanLabel) {
    return "";
  }
  return `This input controls ${cleanLabel.toLowerCase()} for the current analysis. Change it here to alter the next CEA sweep or preliminary blowdown run.`;
}

function applyHoverHint(node, hintText) {
  if (!node || !hintText) {
    return;
  }
  node.classList.add("hover-hint");
  node.setAttribute("title", hintText);
  node.dataset.tip = hintText;
}

function hoverHintTarget(labelNode) {
  if (!labelNode?.querySelector(".info-dot")) {
    return labelNode;
  }
  let textSpan = labelNode.querySelector(".field-label-text");
  if (textSpan) {
    return textSpan;
  }
  textSpan = document.createElement("span");
  textSpan.className = "field-label-text";
  while (labelNode.firstChild && !labelNode.firstChild.classList?.contains?.("info-dot")) {
    textSpan.appendChild(labelNode.firstChild);
  }
  labelNode.insertBefore(textSpan, labelNode.querySelector(".info-dot"));
  return textSpan;
}

function attachFieldLabelTooltips() {
  document.querySelectorAll(".field").forEach((field) => {
    const labelNode = field.querySelector(".field-label");
    if (!labelNode) {
      return;
    }
    const control = field.querySelector("input, select, textarea");
    const labelText = labelNode.textContent || "";
    const hintText = control?.id
      ? tooltipTextForInput(control.id, labelText)
      : STATIC_LABEL_HINTS[labelText.replace(/\s+/g, " ").trim()] || "";
    applyHoverHint(hoverHintTarget(labelNode), hintText);
  });

  document.querySelectorAll(".checkbox-field").forEach((field) => {
    const control = field.querySelector("input");
    const labelNode = [...field.querySelectorAll("span")].find((node) => !node.classList.contains("field-label"));
    if (!control || !labelNode) {
      return;
    }
    applyHoverHint(labelNode, tooltipTextForInput(control.id, labelNode.textContent || ""));
  });
}

function getMetricOptions() {
  return state.defaults?.metric_options || state.results?.meta?.metric_options || [];
}

function metricOptionFor(key) {
  return getMetricOptions().find((option) => option.key === key);
}

function activeMetricLabel(results = state.results) {
  const key = state.activeMetric || results?.meta?.selected_metric || state.defaults?.selected_metric;
  return metricOptionFor(key)?.label || results?.meta?.selected_metric_label || key || "selected metric";
}

function safeFileName(value) {
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "") || "chart";
}

function decimalPlacesForStep(stepValue, fallback = 6) {
  const step = Math.abs(Number(stepValue));
  if (!Number.isFinite(step) || step === 0) {
    return fallback;
  }
  for (let digits = 0; digits <= 8; digits += 1) {
    if (Math.abs(step - Number(step.toFixed(digits))) < 1e-9) {
      return digits;
    }
  }
  return 8;
}

function normalizeSweepValue(value, digits) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return Number.NaN;
  }
  const factor = 10 ** Math.max(0, digits);
  return Math.round((numeric + Number.EPSILON) * factor) / factor;
}

function formatSweepValue(value, digits) {
  const normalized = normalizeSweepValue(value, digits);
  if (!Number.isFinite(normalized)) {
    return "-";
  }
  return normalized.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: Math.max(0, digits),
  });
}

function applyTheme(theme) {
  const normalizedTheme = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = normalizedTheme;
  const isDark = normalizedTheme === "dark";
  $("themeToggle").setAttribute("aria-pressed", String(isDark));
  $("themeToggleValue").textContent = isDark ? "On" : "Off";
  localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
}

function initializeTheme() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(savedTheme || document.body.dataset.theme || "dark");
}

function toggleTheme() {
  applyTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
}

function renderCalculationArticle(results = null) {
  const metricLabel = activeMetricLabel(results);
  const fuelTemperature = results?.controls?.fuel_temperature_k ?? state.defaults?.fuel_temperature_k;
  const oxidizerTemperature = results?.controls?.oxidizer_temperature_k ?? state.defaults?.oxidizer_temperature_k;
  const infill = results?.controls?.desired_infill_percent ?? state.defaults?.desired_infill_percent;

  $("calculationArticle").innerHTML = `
    <div class="calc-article-shell">
      <nav class="calc-article-nav">
        <h3>Contents</h3>
        <a href="#calc-thermo">1. Thermochemical core</a>
        <a href="#calc-selection">2. Variable selection</a>
        <a href="#calc-blowdown">3. Blowdown first-pass sizing</a>
        <a href="#calc-limits">4. Model limits</a>
        <a href="#calc-references">5. References</a>
      </nav>
      <div class="calc-article-body">
        <div class="calc-callout">
          The current UI state is configured around <strong>${escapeHtml(String(metricLabel))}</strong>,
          fuel temperature <strong>${fuelTemperature !== undefined ? `${fmt(fuelTemperature, 2)} K` : "not yet loaded"}</strong>,
          oxidizer temperature <strong>${oxidizerTemperature !== undefined ? `${fmt(oxidizerTemperature, 2)} K` : "not yet loaded"}</strong>,
          and infill <strong>${infill !== undefined ? `${fmt(infill, 1)}%` : "not yet loaded"}</strong>.
          This NASA CEA setup is specifically for an N2O and paraffin engine with ABS structure. The backend reports CEA outputs, minimal thrust-normalized nozzle sizing derived from those CEA outputs, and a separate preliminary 0D blowdown model seeded from the highest-Isp converged CEA case.
        </div>

        <section class="calc-section" id="calc-thermo">
          <h3>1. Thermochemical core</h3>
          <p>
            The backend evaluates each N2O/paraffin/ABS-structure sweep point with NASA CEA in rocket mode. Chamber equilibrium, nozzle expansion,
            <code>Isp</code>, <code>Isp_vac</code>, <code>c*</code>, exit pressure, exit temperature, Mach number,
            molecular weight, gamma, and thrust coefficient come from the CEA solution object.
          </p>
          <p>
            Hybrid grain, chamber, injector, and regression sizing remain removed. The only project-side sizing now
            derives nozzle throat area from CEA <code>c*</code>, target mass flow, and chamber pressure so the throat is choked.
          </p>
        </section>

        <section class="calc-section" id="calc-selection">
          <h3>2. Variable selection</h3>
          <p>
            The output columns and selectable plot metrics are defined in <code>cea_hybrid/variables.py</code>.
            Each variable is tagged as input, CEA, or minimal sizing, with a short description.
          </p>
          <div class="calc-equation">input: abs_vol_frac, fuel_temp_k, oxidizer_temp_k, of, pc_bar, ae_at
CEA: cf, isp_mps, isp_vac_mps, cstar_mps, tc_k, mach_t, pe_bar, te_k, mach_e, gamma_e, mw_e
sizing: mdot_total_kg_s, at_m2, ae_m2, thrust_sl_n, dt_mm, de_mm, de_cm</div>
          <p>
            To add or remove reported values later, change that file first. The CSV writer, plot metric selector,
            labels, and UI payloads all consume the same selection.
          </p>
        </section>

        <section class="calc-section" id="calc-blowdown">
          <h3>3. Blowdown first-pass sizing</h3>
          <p>
            The preliminary 0D blowdown setup now includes optional helper relations from the project sizing notes so fewer manual inputs are required.
            In basic mode, the main oxidizer temperature input also sets the oxidizer tank state, and the backend derives required oxidizer mass, loaded oxidizer mass,
            liquid oxidizer volume, tank volume, and initial tank pressure from the requested burn time and fill policy.
          </p>
          <div class="calc-equation">mdot_total = F / (g0 * Isp)
mdot_ox = (O/F) / (1 + O/F) * mdot_total
mdot_f = mdot_total / (1 + O/F)
m_required = mdot * t_b
m_loaded = m_required / usable_fraction</div>
          <div class="calc-equation">p_tank,0 = p_sat_n2o(T_ox)
rho_ox_liq = rho_liquid_n2o(T_ox)
V_ox_liquid = m_ox_loaded / rho_ox_liq
V_tank = V_ox_liquid / fill_fraction
rho_blend = 1 / (phi_abs/rho_abs + (1-phi_abs)/rho_paraffin)</div>
          <div class="calc-equation">r_port,0 = sqrt(mdot_ox / (pi * N_ports * Gox_0))
rdot_0 = a * Gox_0^n
Lg = mdot_f / (rho_f * N_ports * 2 * pi * r_port,0 * rdot_0)</div>
          <div class="calc-equation">R_outer = sqrt(r_port,0^2 + V_f_loaded / (N_ports * pi * Lg))
A_inj = mdot_ox / (Cd * sqrt(2 * rho_ox * dP_inj))</div>
          <p>
            In the UI, basic mode keeps the high-level sizing inputs and shows the first-pass estimates live. Advanced mode exposes manual overrides for tank mass and volume,
            injector area, initial port radius, grain length, and outer radius whenever you need to replace the derived values.
          </p>
        </section>

        <section class="calc-section" id="calc-limits">
          <h3>4. Model limits</h3>
          <ul>
            <li>It does not resolve finite-rate combustion, droplet breakup, or injector spray physics. NASA CEA assumes chemical equilibrium for the solved state.</li>
            <li>It does not perform hybrid regression, injector, grain, chamber, or structural sizing.</li>
            <li>Nozzle sizing assumes circular-equivalent throat and exit areas and uses CEA <code>c*</code> and <code>Isp</code>.</li>
          </ul>
        </section>

        <section class="calc-section calc-reference" id="calc-references">
          <h3>5. References</h3>
          <ol>
            <li><a href="https://www.nasa.gov/glenn/research/chemical-equilibrium-with-applications/" target="_blank" rel="noreferrer">NASA Glenn Research Center, Chemical Equilibrium with Applications (CEA)</a>. Official overview of the CEA code family used by the backend.</li>
            <li><a href="https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/19960044559.pdf" target="_blank" rel="noreferrer">McBride, B. J., and Gordon, S., NASA RP-1311, CEA Users Manual</a>. Primary NASA documentation for the equilibrium rocket solver.</li>
            <li><a href="https://ntrs.nasa.gov/api/citations/20030060681/downloads/20030060681.pdf" target="_blank" rel="noreferrer">Gordon, S., and McBride, B. J., NASA/TM-2003-212145</a>. Reference manual covering rocket variables including thrust coefficient and characteristic velocity relations.</li>
          </ol>
        </section>
      </div>
    </div>
  `;
}

function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.remove("hidden");
  node.style.background = isError ? "#b42318" : "#17232d";
  window.clearTimeout(toast._timer);
  toast._timer = window.setTimeout(() => node.classList.add("hidden"), 3200);
}

function setFormBusy(isBusy, isStopping = false) {
  document.querySelectorAll("#sweepForm input, #sweepForm select").forEach((node) => {
    node.disabled = isBusy;
  });
  if (!isBusy && state.defaults) {
    updateAdvancedControls();
  }
  const button = $("runButton");
  button.disabled = isStopping;
  button.classList.toggle("is-stop", isBusy);
  if (isStopping) {
    button.textContent = "Stopping...";
  } else if (isBusy) {
    button.textContent = "Stop Analysis";
  } else {
    button.textContent = "Run CEA Sweep";
  }
  updateBlowdownButtonState(isBusy);
}

function showSweepStatus(status) {
  const panel = $("sweepStatus");
  const spinner = $("sweepSpinner");
  const title = $("sweepStatusTitle");
  const text = $("sweepStatusText");
  const percent = $("sweepStatusPercent");
  const bar = $("sweepProgressBar");
  const progressRatio = Math.max(0, Math.min(1, Number(status.progress_ratio || 0)));
  const progressPercent = Math.round(progressRatio * 100);
  const isRunning = status.status === "running";
  const isStopping = status.status === "stopping";

  if (status.status === "idle" && !status.result) {
    panel.classList.add("hidden");
    setFormBusy(false, false);
    return;
  }

  panel.classList.remove("hidden");
  spinner.classList.toggle("hidden", !(isRunning || isStopping));
  title.textContent = {
    running: status.phase === "blowdown" ? "0D blowdown running" : "CEA sweep running",
    stopping: "Stopping analysis",
    completed: status.message?.includes("blowdown") || status.message?.includes("Blowdown")
      ? "Analysis complete"
      : "CEA sweep complete",
    cancelled: "Analysis cancelled",
    error: status.phase === "blowdown" || status.job_type === "blowdown"
      ? "0D blowdown failed"
      : "CEA sweep failed",
    idle: "Ready to run",
  }[status.status] || "Sweep status";
  text.textContent = status.error || status.message || "No sweep is active.";
  percent.textContent = `${progressPercent}%`;
  bar.style.width = `${progressPercent}%`;
  setFormBusy(isRunning || isStopping, isStopping);
}

function closeModal() {
  $("chartModal").classList.add("hidden");
  $("chartModal").setAttribute("aria-hidden", "true");
  $("chartModalBody").innerHTML = "";
}

function isBlowdownAdvancedMode() {
  return $("blowdown_ui_mode").value === "advanced";
}

function activeRegressionPreset() {
  return $("blowdown_grain_regression_preset").value;
}

function activeInjectorPressureDropPolicy() {
  return $("blowdown_injector_pressure_drop_policy").value;
}

function populateForm(defaults) {
  $("target_thrust_n").value = defaults.target_thrust_n;
  $("max_exit_diameter_cm").value = defaults.max_exit_diameter_cm;
  $("max_area_ratio").value = defaults.max_area_ratio;
  $("ae_at_cap_mode").value = defaults.ae_at_cap_mode;
  $("pc_bar").value = defaults.pc_bar;
  $("ae_at_custom_enabled").checked = defaults.ae_at.custom_enabled;
  $("ae_at_start").value = defaults.ae_at.start;
  $("ae_at_stop").value = defaults.ae_at.stop;
  $("ae_at_step").value = defaults.ae_at.step;
  $("of_start").value = defaults.of.start;
  $("of_stop").value = defaults.of.stop;
  $("of_count").value = defaults.of.count;
  $("desired_infill_percent").value = defaults.desired_infill_percent;

  $("fuel_temperature_k").value = defaults.fuel_temperature_k;
  $("oxidizer_temperature_k").value = defaults.oxidizer_temperature_k;

  const metricSelect = $("selected_metric");
  metricSelect.innerHTML = "";
  defaults.metric_options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.key;
    node.textContent = option.label;
    if (option.key === defaults.selected_metric) {
      node.selected = true;
    }
    metricSelect.appendChild(node);
  });
  metricSelect.disabled = true;

  const blowdown = defaults.blowdown;
  $("blowdown_auto_run_after_cea").checked = blowdown.auto_run_after_cea;
  $("blowdown_ui_mode").value = blowdown.ui_mode;
  $("blowdown_tank_volume_l").value = blowdown.tank.volume_l;
  $("blowdown_tank_initial_mass_kg").value = blowdown.tank.initial_mass_kg;
  $("blowdown_tank_usable_oxidizer_fraction").value = blowdown.tank.usable_oxidizer_fraction;
  $("blowdown_tank_initial_fill_fraction").value = blowdown.tank.initial_fill_fraction;
  $("blowdown_tank_override_mass_volume").checked = blowdown.tank.override_mass_volume;
  $("blowdown_feed_line_id_mm").value = blowdown.feed.line_id_mm;
  $("blowdown_feed_line_length_m").value = blowdown.feed.line_length_m;
  $("blowdown_feed_friction_factor").value = blowdown.feed.friction_factor;
  $("blowdown_feed_minor_loss_k_total").value = blowdown.feed.minor_loss_k_total;
  $("blowdown_injector_cd").value = blowdown.injector.cd;
  $("blowdown_injector_hole_count").value = blowdown.injector.hole_count;
  $("blowdown_injector_total_area_mm2").value = blowdown.injector.total_area_mm2;
  $("blowdown_injector_override_total_area").checked = blowdown.injector.override_total_area;
  $("blowdown_injector_pressure_drop_policy").value = blowdown.injector.pressure_drop_policy;
  $("blowdown_injector_delta_p_mode").value = blowdown.injector.delta_p_mode;
  $("blowdown_injector_delta_p_pa").value = blowdown.injector.delta_p_pa / 1e5;
  $("blowdown_injector_delta_p_fraction_of_pc").value = blowdown.injector.delta_p_fraction_of_pc;
  $("blowdown_grain_regression_preset").value = blowdown.grain.regression_preset;
  $("blowdown_grain_a_reg_si").value = blowdown.grain.a_reg_si;
  $("blowdown_grain_n_reg").value = blowdown.grain.n_reg;
  $("blowdown_grain_port_count").value = blowdown.grain.port_count;
  $("blowdown_grain_override_initial_port_radius").checked = blowdown.grain.override_initial_port_radius;
  $("blowdown_grain_target_initial_gox_kg_m2_s").value = blowdown.grain.target_initial_gox_kg_m2_s;
  $("blowdown_grain_initial_port_radius_mm").value = blowdown.grain.initial_port_radius_mm;
  $("blowdown_grain_override_grain_length").checked = blowdown.grain.override_grain_length;
  $("blowdown_grain_length_m").value = blowdown.grain.grain_length_m;
  $("blowdown_grain_override_outer_radius").checked = blowdown.grain.override_outer_radius;
  $("blowdown_grain_fuel_usable_fraction").value = blowdown.grain.fuel_usable_fraction;
  $("blowdown_grain_outer_radius_mm").value = blowdown.grain.outer_radius_mm ?? "";
  $("blowdown_sim_dt_s").value = blowdown.simulation.dt_s;
  $("blowdown_sim_burn_time_s").value = blowdown.simulation.burn_time_s;
  $("blowdown_sim_ambient_pressure_bar").value = blowdown.simulation.ambient_pressure_bar;
  $("blowdown_sim_max_inner_iterations").value = blowdown.simulation.max_inner_iterations;
  $("blowdown_sim_relaxation").value = blowdown.simulation.relaxation;
  $("blowdown_sim_relative_tolerance").value = blowdown.simulation.relative_tolerance;
  $("blowdown_sim_stop_quality").value = blowdown.simulation.stop_when_tank_quality_exceeds;
  updateAdvancedControls();
}

function updateAdvancedControls() {
  const customEnabled = $("ae_at_custom_enabled").checked;
  $("aeAtCustomFields").disabled = !customEnabled;
  const capMode = $("ae_at_cap_mode").value;
  $("max_exit_diameter_cm").disabled = capMode !== "exit_diameter";
  $("max_area_ratio").disabled = capMode !== "area_ratio";
  const isAdvanced = isBlowdownAdvancedMode();
  $("blowdownAdvancedControls").classList.toggle("hidden", !isAdvanced);
  $("blowdownFeedSection").classList.toggle("hidden", !isAdvanced);
  $("blowdownSolverSection").classList.toggle("hidden", !isAdvanced);
  const tankOverride = isAdvanced && $("blowdown_tank_override_mass_volume").checked;
  const injectorOverride = isAdvanced && $("blowdown_injector_override_total_area").checked;
  const portOverride = isAdvanced && $("blowdown_grain_override_initial_port_radius").checked;
  const lengthOverride = isAdvanced && $("blowdown_grain_override_grain_length").checked;
  const outerOverride = isAdvanced && $("blowdown_grain_override_outer_radius").checked;
  $("blowdown_tank_volume_l").disabled = !tankOverride;
  $("blowdown_tank_initial_mass_kg").disabled = !tankOverride;
  $("blowdown_injector_total_area_mm2").disabled = !injectorOverride;
  $("blowdown_grain_initial_port_radius_mm").disabled = !portOverride;
  $("blowdown_grain_length_m").disabled = !lengthOverride;
  $("blowdown_grain_outer_radius_mm").disabled = !outerOverride;
  $("blowdown_tank_usable_oxidizer_fraction").disabled = !isAdvanced;
  $("blowdown_grain_fuel_usable_fraction").disabled = !isAdvanced;
  $("blowdown_grain_port_count").disabled = !isAdvanced;
  $("blowdown_injector_cd").disabled = !isAdvanced;
  $("blowdown_injector_hole_count").disabled = !isAdvanced;
  const regressionPreset = activeRegressionPreset();
  const customRegression = isAdvanced && regressionPreset === "custom";
  $("blowdown_grain_a_reg_si").disabled = !customRegression;
  $("blowdown_grain_n_reg").disabled = !customRegression;
  const explicitDeltaP = $("blowdown_injector_delta_p_mode").value === "explicit";
  $("blowdown_injector_delta_p_mode").disabled = !isAdvanced;
  $("blowdown_injector_delta_p_pa").disabled = !isAdvanced || !explicitDeltaP;
  $("blowdown_injector_delta_p_fraction_of_pc").disabled = !isAdvanced || explicitDeltaP;
  updateBlowdownButtonState(false);
}

function buildBlowdownPayload() {
  const isAdvanced = isBlowdownAdvancedMode();
  const defaults = state.defaults?.blowdown || {};
  const tankDefaults = defaults.tank || {};
  const injectorDefaults = defaults.injector || {};
  const grainDefaults = defaults.grain || {};
  const regressionPreset = activeRegressionPreset();
  const customRegression = regressionPreset === "custom";
  const injectorPressureDropPolicy = activeInjectorPressureDropPolicy();
  const oxidizerTemperatureK = parseNumericInput("oxidizer_temperature_k", "Oxidizer temperature");

  return {
    auto_run_after_cea: $("blowdown_auto_run_after_cea").checked,
    oxidizer_temperature_k: oxidizerTemperatureK,
    ui_mode: $("blowdown_ui_mode").value,
    seed_case: "highest_isp",
    tank: {
      volume_l: isAdvanced
        ? parseNumericInput("blowdown_tank_volume_l", "Blowdown tank volume")
        : Number(tankDefaults.volume_l ?? 28.0),
      initial_mass_kg: isAdvanced
        ? parseNumericInput("blowdown_tank_initial_mass_kg", "Blowdown initial tank mass")
        : Number(tankDefaults.initial_mass_kg ?? 18.0),
      initial_temp_k: oxidizerTemperatureK,
      usable_oxidizer_fraction: isAdvanced
        ? parseNumericInput("blowdown_tank_usable_oxidizer_fraction", "Blowdown usable oxidizer fraction")
        : Number(tankDefaults.usable_oxidizer_fraction ?? 0.95),
      initial_fill_fraction: parseNumericInput("blowdown_tank_initial_fill_fraction", "Blowdown initial fill fraction"),
      override_mass_volume: $("blowdown_tank_override_mass_volume").checked,
    },
    feed: {
      line_id_mm: parseNumericInput("blowdown_feed_line_id_mm", "Blowdown feed line inner diameter"),
      line_length_m: parseNumericInput("blowdown_feed_line_length_m", "Blowdown feed line length"),
      friction_factor: parseNumericInput("blowdown_feed_friction_factor", "Blowdown feed friction factor"),
      minor_loss_k_total: parseNumericInput("blowdown_feed_minor_loss_k_total", "Blowdown feed minor loss K"),
    },
    injector: {
      cd: isAdvanced
        ? parseNumericInput("blowdown_injector_cd", "Blowdown injector Cd")
        : Number(injectorDefaults.cd ?? 0.8),
      hole_count: isAdvanced
        ? parseNumericInput("blowdown_injector_hole_count", "Blowdown injector hole count", { integer: true })
        : Number(injectorDefaults.hole_count ?? 24),
      total_area_mm2: isAdvanced
        ? parseNumericInput("blowdown_injector_total_area_mm2", "Blowdown injector total area")
        : Number(injectorDefaults.total_area_mm2 ?? 75.0),
      override_total_area: $("blowdown_injector_override_total_area").checked,
      pressure_drop_policy: injectorPressureDropPolicy,
      delta_p_mode: isAdvanced ? $("blowdown_injector_delta_p_mode").value : (injectorDefaults.delta_p_mode || "fraction_of_pc"),
      delta_p_pa: isAdvanced
        ? parseNumericInput("blowdown_injector_delta_p_pa", "Blowdown injector delta-p") * 1e5
        : Number(injectorDefaults.delta_p_pa ?? 600000.0),
      delta_p_fraction_of_pc: isAdvanced
        ? parseNumericInput("blowdown_injector_delta_p_fraction_of_pc", "Blowdown injector delta-p fraction of chamber pressure")
        : Number(injectorDefaults.delta_p_fraction_of_pc ?? 0.2),
    },
    grain: {
      abs_density_kg_m3: state.defaults?.blowdown?.grain?.abs_density_kg_m3 ?? 1050.0,
      paraffin_density_kg_m3: state.defaults?.blowdown?.grain?.paraffin_density_kg_m3 ?? 930.0,
      regression_preset: regressionPreset,
      a_reg_si: (isAdvanced || customRegression)
        ? parseNumericInput("blowdown_grain_a_reg_si", "Blowdown regression coefficient a")
        : Number(grainDefaults.a_reg_si ?? 0.00005),
      n_reg: (isAdvanced || customRegression)
        ? parseNumericInput("blowdown_grain_n_reg", "Blowdown regression exponent n")
        : Number(grainDefaults.n_reg ?? 0.5),
      port_count: isAdvanced
        ? parseNumericInput("blowdown_grain_port_count", "Blowdown grain port count", { integer: true })
        : Number(grainDefaults.port_count ?? 1),
      target_initial_gox_kg_m2_s: parseNumericInput("blowdown_grain_target_initial_gox_kg_m2_s", "Blowdown target initial oxidizer flux"),
      initial_port_radius_mm: isAdvanced
        ? parseNumericInput("blowdown_grain_initial_port_radius_mm", "Blowdown initial port radius")
        : Number(grainDefaults.initial_port_radius_mm ?? 22.0),
      grain_length_m: isAdvanced
        ? parseNumericInput("blowdown_grain_length_m", "Blowdown grain length")
        : Number(grainDefaults.grain_length_m ?? 0.45),
      fuel_usable_fraction: isAdvanced
        ? parseNumericInput("blowdown_grain_fuel_usable_fraction", "Blowdown fuel usable fraction")
        : Number(grainDefaults.fuel_usable_fraction ?? 0.98),
      outer_radius_mm: isAdvanced
        ? parseNumericInput("blowdown_grain_outer_radius_mm", "Blowdown outer grain radius", { allowBlank: true })
        : (grainDefaults.outer_radius_mm ?? null),
      override_initial_port_radius: $("blowdown_grain_override_initial_port_radius").checked,
      override_grain_length: $("blowdown_grain_override_grain_length").checked,
      override_outer_radius: $("blowdown_grain_override_outer_radius").checked,
    },
    simulation: {
      dt_s: parseNumericInput("blowdown_sim_dt_s", "Blowdown simulation time step"),
      burn_time_s: parseNumericInput("blowdown_sim_burn_time_s", "Blowdown burn time"),
      ambient_pressure_bar: parseNumericInput("blowdown_sim_ambient_pressure_bar", "Blowdown ambient pressure"),
      max_inner_iterations: parseNumericInput("blowdown_sim_max_inner_iterations", "Blowdown max inner iterations", { integer: true }),
      relaxation: parseNumericInput("blowdown_sim_relaxation", "Blowdown relaxation"),
      relative_tolerance: parseNumericInput("blowdown_sim_relative_tolerance", "Blowdown relative tolerance"),
      stop_when_tank_quality_exceeds: parseNumericInput("blowdown_sim_stop_quality", "Blowdown tank quality cutoff"),
    },
  };
}

function buildPayload() {
  return {
    target_thrust_n: parseNumericInput("target_thrust_n", "Target thrust"),
    max_exit_diameter_cm: parseNumericInput("max_exit_diameter_cm", "Max exit diameter"),
    max_area_ratio: parseNumericInput("max_area_ratio", "Max area ratio"),
    ae_at_cap_mode: $("ae_at_cap_mode").value,
    pc_bar: parseNumericInput("pc_bar", "Target chamber pressure"),
    selected_metric: $("selected_metric").value || state.defaults?.selected_metric || "isp_s",
    fuel_temperature_k: parseNumericInput("fuel_temperature_k", "Fuel temperature"),
    oxidizer_temperature_k: parseNumericInput("oxidizer_temperature_k", "Oxidizer temperature"),
    desired_infill_percent: parseNumericInput("desired_infill_percent", "Desired infill"),
    ae_at: {
      custom_enabled: $("ae_at_custom_enabled").checked,
      start: parseNumericInput("ae_at_start", "Ae/At sweep start"),
      stop: parseNumericInput("ae_at_stop", "Ae/At sweep end"),
      step: parseNumericInput("ae_at_step", "Ae/At sweep step"),
      cf_search_upper_bound: state.defaults?.ae_at?.cf_search_upper_bound ?? 3.0,
    },
    of: {
      start: parseNumericInput("of_start", "O/F sweep start"),
      stop: parseNumericInput("of_stop", "O/F sweep stop"),
      count: parseNumericInput("of_count", "O/F sweep count", { integer: true }),
    },
    blowdown: buildBlowdownPayload(),
  };
}

function previewCardsFromFields(fields) {
  return (fields || []).map((field) => ({
    label: field.label,
    value: formatCaseField(field.key, field.value),
    hint: hintForCaseField(field.key, field.label),
  }));
}

function renderBlowdownPreview(preview) {
  state.blowdownPreview = preview;
  if (!preview) {
    $("blowdownLivePreview").innerHTML = chartEmptyState("Run a CEA sweep to unlock live blowdown sizing estimates.");
    renderEstimationsPanel();
    return;
  }
  if (preview.status !== "ready") {
    const text = preview.error ? `${preview.message} ${preview.error}` : preview.message;
    $("blowdownLivePreview").innerHTML = `<div class="empty-state">${escapeHtml(text || "Live sizing preview is unavailable.")}</div>`;
    renderEstimationsPanel();
    return;
  }

  const seedCards = previewCardsFromFields(preview.seed_case_fields);
  const previewCards = previewCardsFromFields(preview.preview_fields);
  const overrideCards = previewCardsFromFields(preview.override_fields);
  $("blowdownLivePreview").innerHTML = `
    <article class="best-isp-card best-isp-card-compact">
      <p class="best-isp-note">${escapeHtml(preview.message)}</p>
      ${renderBestIspSection("Seeded CEA Inputs", seedCards)}
      ${renderBestIspSection("First-Pass Estimates", previewCards)}
      ${renderBestIspSection("Override Sources", overrideCards)}
    </article>
  `;
  renderEstimationsPanel();
}

function clearBlowdownPreview(message) {
  renderBlowdownPreview({
    status: "error",
    message,
    error: null,
  });
}

async function refreshBlowdownPreview() {
  try {
    const preview = await requestJson("/api/blowdown-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBlowdownPayload()),
    });
    renderBlowdownPreview(preview);
  } catch (error) {
    renderBlowdownPreview({
      status: "error",
      message: "Live sizing preview needs input.",
      error: error.message,
    });
  }
}

function scheduleBlowdownPreview(delayMs = 180) {
  if (state.previewTimer !== null) {
    window.clearTimeout(state.previewTimer);
  }
  state.previewTimer = window.setTimeout(() => {
    state.previewTimer = null;
    refreshBlowdownPreview().catch(() => {
      clearBlowdownPreview("Live sizing preview is unavailable.");
    });
  }, delayMs);
}

function updateBlowdownButtonState(isBusy = false) {
  const button = $("runBlowdownButton");
  if (!button) {
    return;
  }
  button.disabled = isBusy || !(state.results?.best_isp_case || state.blowdownPreview?.status === "ready");
}

function chartEmptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function paddedRange(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (Math.abs(max - min) < 1e-9) {
    const pad = Math.max(Math.abs(min) * 0.08, 1);
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

function clampRange(range, initial) {
  const width = range.max - range.min;
  const initialWidth = initial.max - initial.min;
  if (width <= 0) {
    return { ...initial };
  }
  if (width >= initialWidth) {
    return { ...initial };
  }
  if (range.min < initial.min) {
    return { min: initial.min, max: initial.min + width };
  }
  if (range.max > initial.max) {
    return { min: initial.max - width, max: initial.max };
  }
  return range;
}

function buildTicks(min, max, count = 6) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [];
  }
  if (Math.abs(max - min) < 1e-9) {
    return [min];
  }
  const step = (max - min) / Math.max(count - 1, 1);
  return Array.from({ length: count }, (_, index) => min + index * step);
}

function createLineChartConfig(series, options) {
  return {
    title: options.title,
    xLabel: options.xLabel,
    yLabel: options.yLabel,
    metricKey: options.metricKey,
    metricLabel: options.metricLabel,
    filename: options.filename,
    height: options.height || 620,
    xDigits: options.xDigits ?? 2,
    yDigits: options.yDigits ?? 2,
    series: series.map((item, index) => ({
      label: item.label,
      color: palette[index % palette.length],
      points: item.points.slice().sort((a, b) => a.x - b.x),
    })),
  };
}

function mountInteractiveChart(host, config, { expandable = true } = {}) {
  if (!config.series.length || !config.series.some((series) => series.points.length)) {
    host.innerHTML = chartEmptyState("No converged data for this chart.");
    return;
  }

  host.innerHTML = `
    <div class="chart-shell">
      <div class="chart-tools">
        <span class="chart-hint">Wheel to zoom. Drag to pan. Hover points and use the legend to focus curves.</span>
        <div class="chart-tool-group">
          <button type="button" class="chart-tool-button" data-chart-action="download">Download PNG</button>
          <button type="button" class="chart-tool-button" data-chart-action="reset">Reset</button>
          ${expandable ? '<button type="button" class="chart-tool-button chart-tool-accent" data-chart-action="expand">Expand</button>' : ""}
        </div>
      </div>
      <div class="chart-layout">
        <div class="chart-canvas-wrap">
          <canvas class="chart-canvas"></canvas>
          <div class="chart-tooltip hidden"></div>
        </div>
        <div class="chart-legend"></div>
      </div>
    </div>
  `;

  const canvasWrap = host.querySelector(".chart-canvas-wrap");
  const canvas = host.querySelector(".chart-canvas");
  const tooltip = host.querySelector(".chart-tooltip");
  const legend = host.querySelector(".chart-legend");
  legend.style.maxHeight = `${Math.max(240, config.height - 8)}px`;
  const context = canvas.getContext("2d");
  const series = config.series.map((item) => ({ ...item }));
  const visible = series.map(() => true);
  let legendHighlightIndex = null;
  let pointerState = null;
  let hoveredPoint = null;

  const allX = series.flatMap((item) => item.points.map((point) => point.x));
  const initialX = (() => {
    const [min, max] = paddedRange(allX);
    return { min, max };
  })();

  function getHighlightIndex() {
    if (hoveredPoint) {
      return hoveredPoint.seriesIndex;
    }
    return legendHighlightIndex;
  }

  function currentYRange(xRange) {
    const values = [];
    series.forEach((item, index) => {
      if (!visible[index]) {
        return;
      }
      item.points.forEach((point) => {
        if (point.x >= xRange.min && point.x <= xRange.max) {
          values.push(point.y);
        }
      });
    });
    if (!values.length) {
      series.forEach((item, index) => {
        if (!visible[index]) {
          return;
        }
        item.points.forEach((point) => values.push(point.y));
      });
    }
    const [min, max] = paddedRange(values);
    return { min, max };
  }

  let viewX = { ...initialX };
  let viewY = currentYRange(viewX);

  function updateLegend() {
    legend.innerHTML = "";
    const activeIndex = getHighlightIndex();
    series.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chart-legend-item";
      if (!visible[index]) {
        button.classList.add("is-muted");
      }
      if (activeIndex === index) {
        button.classList.add("is-highlighted");
      }
      button.innerHTML = `
        <span class="chart-legend-swatch" style="background:${item.color}"></span>
        <span class="chart-legend-label">${escapeHtml(item.label)}</span>
      `;
      button.addEventListener("mouseenter", () => {
        legendHighlightIndex = index;
        draw();
        updateLegend();
      });
      button.addEventListener("mouseleave", () => {
        legendHighlightIndex = null;
        draw();
        updateLegend();
      });
      button.addEventListener("click", () => {
        if (visible.filter(Boolean).length === 1 && visible[index]) {
          return;
        }
        visible[index] = !visible[index];
        hoveredPoint = null;
        hideTooltip();
        viewY = currentYRange(viewX);
        draw();
        updateLegend();
      });
      legend.appendChild(button);
    });
  }

  function getPlotGeometry(dpr) {
    const margins = { left: 76, right: 24, top: 26, bottom: 54 };
    return {
      plotLeft: margins.left * dpr,
      plotTop: margins.top * dpr,
      plotWidth: canvas.width - (margins.left + margins.right) * dpr,
      plotHeight: canvas.height - (margins.top + margins.bottom) * dpr,
    };
  }

  function projectPoint(point, geometry) {
    return {
      x: geometry.plotLeft + ((point.x - viewX.min) / (viewX.max - viewX.min)) * geometry.plotWidth,
      y: geometry.plotTop + ((viewY.max - point.y) / (viewY.max - viewY.min)) * geometry.plotHeight,
    };
  }

  function findNearestPoint(clientX, clientY) {
    const dpr = window.devicePixelRatio || 1;
    const bounds = canvas.getBoundingClientRect();
    const geometry = getPlotGeometry(dpr);
    const canvasX = (clientX - bounds.left) * dpr;
    const canvasY = (clientY - bounds.top) * dpr;
    const threshold = 20 * dpr;
    let best = null;

    series.forEach((item, seriesIndex) => {
      if (!visible[seriesIndex]) {
        return;
      }
      item.points.forEach((point) => {
        if (point.x < viewX.min || point.x > viewX.max) {
          return;
        }
        const screenPoint = projectPoint(point, geometry);
        const distance = Math.hypot(screenPoint.x - canvasX, screenPoint.y - canvasY);
        if (!best || distance < best.distance) {
          best = { point, seriesIndex, screenPoint, distance };
        }
      });
    });

    if (!best || best.distance > threshold) {
      return null;
    }
    return best;
  }

  function showTooltip(found, clientX, clientY) {
    tooltip.innerHTML = `
      <strong>${escapeHtml(series[found.seriesIndex].label)}</strong><br>
      ${escapeHtml(config.xLabel)}: ${fmt(found.point.x, config.xDigits)}<br>
      ${escapeHtml(config.yLabel)}: ${fmt(found.point.y, config.yDigits)}
    `;
    const bounds = canvasWrap.getBoundingClientRect();
    tooltip.style.left = `${Math.min(Math.max(clientX - bounds.left + 12, 12), bounds.width - 180)}px`;
    tooltip.style.top = `${Math.min(Math.max(clientY - bounds.top + 12, 12), bounds.height - 74)}px`;
    tooltip.classList.remove("hidden");
  }

  function hideTooltip() {
    tooltip.classList.add("hidden");
  }

  function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const bounds = canvasWrap.getBoundingClientRect();
    canvas.width = Math.floor(bounds.width * dpr);
    canvas.height = Math.floor(config.height * dpr);
    canvas.style.height = `${config.height}px`;
    draw();
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.width;
    const height = canvas.height;
    const geometry = getPlotGeometry(dpr);
    const activeIndex = getHighlightIndex();

    context.clearRect(0, 0, width, height);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.fillStyle = "#f7f9fb";
    context.fillRect(geometry.plotLeft, geometry.plotTop, geometry.plotWidth, geometry.plotHeight);
    context.strokeStyle = "#cad4dc";
    context.lineWidth = 1 * dpr;
    context.strokeRect(geometry.plotLeft, geometry.plotTop, geometry.plotWidth, geometry.plotHeight);

    const yTicks = buildTicks(viewY.min, viewY.max, 6);
    context.font = `${13 * dpr}px "Aptos", "Segoe UI Variable Text", sans-serif`;
    context.fillStyle = "#556a79";
    context.textAlign = "right";
    yTicks.forEach((value) => {
      const ratio = (viewY.max - value) / (viewY.max - viewY.min);
      const y = geometry.plotTop + ratio * geometry.plotHeight;
      context.strokeStyle = "#e3e9ee";
      context.beginPath();
      context.moveTo(geometry.plotLeft, y);
      context.lineTo(geometry.plotLeft + geometry.plotWidth, y);
      context.stroke();
      context.fillText(fmt(value, config.yDigits), geometry.plotLeft - 10 * dpr, y + 4 * dpr);
    });

    const xTicks = buildTicks(viewX.min, viewX.max, 7);
    context.textAlign = "center";
    xTicks.forEach((value) => {
      const x = geometry.plotLeft + ((value - viewX.min) / (viewX.max - viewX.min)) * geometry.plotWidth;
      context.strokeStyle = "#eef2f5";
      context.beginPath();
      context.moveTo(x, geometry.plotTop);
      context.lineTo(x, geometry.plotTop + geometry.plotHeight);
      context.stroke();
      context.fillText(fmt(value, config.xDigits), x, height - 18 * dpr);
    });

    context.save();
    context.beginPath();
    context.rect(geometry.plotLeft, geometry.plotTop, geometry.plotWidth, geometry.plotHeight);
    context.clip();

    series.forEach((item, index) => {
      if (!visible[index]) {
        return;
      }
      const opacity = activeIndex === null || activeIndex === index ? 1 : 0.18;
      context.strokeStyle = item.color;
      context.globalAlpha = opacity;
      context.lineWidth = 3.4 * dpr;
      context.beginPath();
      let started = false;
      item.points.forEach((point) => {
        const screenPoint = projectPoint(point, geometry);
        if (!started) {
          context.moveTo(screenPoint.x, screenPoint.y);
          started = true;
        } else {
          context.lineTo(screenPoint.x, screenPoint.y);
        }
      });
      context.stroke();

      item.points.forEach((point) => {
        const screenPoint = projectPoint(point, geometry);
        context.fillStyle = item.color;
        context.beginPath();
        context.arc(screenPoint.x, screenPoint.y, 4.2 * dpr, 0, Math.PI * 2);
        context.fill();
      });
      context.globalAlpha = 1;
    });

    if (hoveredPoint) {
      const item = series[hoveredPoint.seriesIndex];
      context.strokeStyle = "#ffffff";
      context.lineWidth = 2.4 * dpr;
      context.fillStyle = item.color;
      context.beginPath();
      context.arc(hoveredPoint.screenPoint.x, hoveredPoint.screenPoint.y, 7.4 * dpr, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }
    context.restore();

    context.fillStyle = "#16222b";
    context.textAlign = "center";
    context.font = `${14 * dpr}px "Aptos", "Segoe UI Variable Text", sans-serif`;
    context.fillText(config.xLabel, width / 2, height - 4 * dpr);
    context.textAlign = "left";
    context.fillText(config.yLabel, 18 * dpr, 20 * dpr);
  }

  function resetView() {
    viewX = { ...initialX };
    viewY = currentYRange(viewX);
    hoveredPoint = null;
    hideTooltip();
    draw();
  }

  function downloadChart() {
    const link = document.createElement("a");
    link.download = config.filename || `${safeFileName(config.title)}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }

  function expandChart() {
    $("chartModalTitle").textContent = config.title;
    $("chartModalBody").innerHTML = "";
    const modalHost = document.createElement("div");
    modalHost.className = "chart-modal-host";
    $("chartModalBody").appendChild(modalHost);
    mountInteractiveChart(modalHost, { ...config, height: Math.max(config.height + 160, 920) }, { expandable: false });
    $("chartModal").classList.remove("hidden");
    $("chartModal").setAttribute("aria-hidden", "false");
  }

  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const dpr = window.devicePixelRatio || 1;
    const bounds = canvas.getBoundingClientRect();
    const geometry = getPlotGeometry(dpr);
    const x = (event.clientX - bounds.left) * dpr;
    const relative = (x - geometry.plotLeft) / geometry.plotWidth;
    if (relative < 0 || relative > 1) {
      return;
    }
    const pointerX = viewX.min + relative * (viewX.max - viewX.min);
    const zoom = event.deltaY < 0 ? 0.88 : 1.14;
    const nextX = {
      min: pointerX - (pointerX - viewX.min) * zoom,
      max: pointerX + (viewX.max - pointerX) * zoom,
    };
    viewX = clampRange(nextX, initialX);
    viewY = currentYRange(viewX);
    hoveredPoint = null;
    hideTooltip();
    draw();
  }, { passive: false });

  canvas.addEventListener("pointerdown", (event) => {
    const dpr = window.devicePixelRatio || 1;
    pointerState = {
      startX: event.clientX,
      startY: event.clientY,
      xRange: { ...viewX },
      yRange: { ...viewY },
      dpr,
    };
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (pointerState) {
      const geometry = getPlotGeometry(pointerState.dpr);
      const dx = (event.clientX - pointerState.startX) * pointerState.dpr;
      const dy = (event.clientY - pointerState.startY) * pointerState.dpr;
      const xShift = (dx / geometry.plotWidth) * (pointerState.xRange.max - pointerState.xRange.min);
      const yShift = (dy / geometry.plotHeight) * (pointerState.yRange.max - pointerState.yRange.min);
      viewX = clampRange(
        {
          min: pointerState.xRange.min - xShift,
          max: pointerState.xRange.max - xShift,
        },
        initialX,
      );
      viewY = {
        min: pointerState.yRange.min + yShift,
        max: pointerState.yRange.max + yShift,
      };
      hoveredPoint = null;
      hideTooltip();
      draw();
      return;
    }

    const found = findNearestPoint(event.clientX, event.clientY);
    hoveredPoint = found;
    if (found) {
      showTooltip(found, event.clientX, event.clientY);
    } else {
      hideTooltip();
    }
    draw();
    updateLegend();
  });

  const stopDrag = (event) => {
    if (!pointerState) {
      return;
    }
    try {
      canvas.releasePointerCapture(event.pointerId);
    } catch (_) {
    }
    pointerState = null;
  };

  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointerleave", (event) => {
    stopDrag(event);
    hoveredPoint = null;
    hideTooltip();
    draw();
    updateLegend();
  });

  host.querySelector("[data-chart-action='reset']").addEventListener("click", resetView);
  host.querySelector("[data-chart-action='download']").addEventListener("click", downloadChart);
  const expandButton = host.querySelector("[data-chart-action='expand']");
  if (expandButton) {
    expandButton.addEventListener("click", expandChart);
  }

  updateLegend();
  resizeCanvas();
  new ResizeObserver(resizeCanvas).observe(canvasWrap);
}

function renderChartInto(hostId, config) {
  mountInteractiveChart($(hostId), config, { expandable: true });
}

function renderCompactCards(cards) {
  return cards.map((card) => `
    <article class="compact-output-card">
      <div class="compact-output-label hover-hint" title="${escapeHtml(card.hint)}" data-tip="${escapeHtml(card.hint)}">${escapeHtml(card.label)}</div>
      <div class="compact-output-value">${escapeHtml(card.value)}</div>
      <div class="compact-output-hint">${escapeHtml(card.hint)}</div>
    </article>
  `).join("");
}

function fieldMap(fields) {
  return Object.fromEntries(fields.map((field) => [field.key, field]));
}

function fieldCard(field) {
  return {
    label: field.label,
    value: formatCaseField(field.key, field.value),
    hint: hintForCaseField(field.key, field.label),
  };
}

function renderBestIspSection(title, cards) {
  return `
    <section class="best-isp-section">
      <h4>${escapeHtml(title)}</h4>
      <div class="best-isp-card-grid">
        ${renderCompactCards(cards)}
      </div>
    </section>
  `;
}

function renderTextListSection(title, items) {
  if (!items?.length) {
    return "";
  }
  return `
    <section class="best-isp-section">
      <h4>${escapeHtml(title)}</h4>
      <ul class="blowdown-assumption-list">
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

function formatCaseField(key, value) {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value !== "number") {
    return value === null || value === undefined ? "-" : prettyBlowdownString(key, value);
  }
  if (key === "step_count" || key.endsWith("_count")) {
    return Math.round(value).toString();
  }
  if (key.endsWith("_frac") || key.endsWith("_fraction") || key === "cf" || key === "gamma_e") {
    return fmt(value, 4);
  }
  if (key.endsWith("_mm2")) {
    return fmt(value, 3);
  }
  if (key === "ae_at" || key === "of" || key.endsWith("_cm") || key.endsWith("_mm")) {
    return fmt(value, 2);
  }
  if (key.endsWith("_l")) {
    return fmt(value, 2);
  }
  if (key.endsWith("_kg_m3")) {
    return fmt(value, 2);
  }
  if (key.endsWith("_kg_m2_s")) {
    return fmt(value, 2);
  }
  if (key.endsWith("_si")) {
    return Number(value).toExponential(3);
  }
  if (key.includes("tolerance")) {
    return Number(value).toExponential(3);
  }
  if (key.endsWith("_mm_s")) {
    return fmt(value, 4);
  }
  if (key.endsWith("_bar")) {
    return fmt(value, 3);
  }
  if (key.endsWith("_n")) {
    return fmt(value, 1);
  }
  if (key.endsWith("_k")) {
    return fmt(value, 1);
  }
  if (key === "mach_t" || key === "mach_e") {
    return fmt(value, 6);
  }
  if (key.endsWith("_m2")) {
    return fmt(value, 7);
  }
  if (key.endsWith("_kg_s")) {
    return fmt(value, 4);
  }
  return fmt(value, 3);
}

function renderBestIspOutput(results) {
  const item = results.best_isp_case;
  if (!item || !item.fields?.length) {
    $("bestIspOutput").innerHTML = chartEmptyState("No Isp-optimized output is available.");
    return;
  }
  const fields = fieldMap(item.fields);
  const simulationCards = [
    {
      label: "Plot Metric",
      value: activeMetricLabel(results),
      hint: "Metric shown on the preloaded raw O/F chart",
    },
    {
      label: "Sweep Density",
      value: `${results.controls.ae_at_values.length} x ${results.controls.of_values.length}`,
      hint: "Ae/At samples x O/F samples",
    },
    {
      label: "Case Count",
      value: results.meta.case_count.toLocaleString(),
      hint: `${results.meta.failure_count.toLocaleString()} failed or unconverged cases`,
    },
  ];
  if (fields["thrust_sl_n"]) {
    simulationCards.push({
      label: "Sea-Level Thrust",
      value: formatCaseField("thrust_sl_n", fields["thrust_sl_n"].value),
      hint: "Estimated actual thrust at standard sea-level ambient pressure",
    });
  }
  const capCards = [
    {
      label: "Cap Mode",
      value: results.controls.ae_at_cap_mode === "exit_diameter" ? "Exit Diameter" : "Area Ratio",
      hint: results.controls.ae_at_cap_mode === "exit_diameter"
        ? `${fmt(results.controls.max_exit_diameter_cm, 1)} cm maximum exit diameter`
        : `${fmt(results.controls.max_area_ratio, 1)} maximum Ae/At`,
    },
  ];
  const capInputKey = results.controls.ae_at_cap_mode === "exit_diameter"
    ? "max_exit_diameter_cm"
    : "max_area_ratio";
  const inputKeys = [
    "target_thrust_n",
    "pc_bar",
    "abs_vol_frac",
    "fuel_temp_k",
    "oxidizer_temp_k",
    "of",
    "ae_at",
    capInputKey,
    "ae_at_cap_mode",
  ];
  const ceaKeys = [
    "isp_s",
    "isp_vac_s",
    "cf",
    "cstar_mps",
    "tc_k",
    "mach_t",
    "pe_bar",
    "te_k",
    "mach_e",
    "gamma_e",
    "mw_e",
    "isp_mps",
    "isp_vac_mps",
  ];
  const sizingKeys = [
    "abs_mass_frac",
    "mdot_total_kg_s",
    "at_m2",
    "ae_m2",
    "thrust_sl_n",
    "dt_mm",
    "de_mm",
    "de_cm",
    "exit_diameter_margin_cm",
    "exit_diameter_within_limit",
  ];
  const cardsForKeys = (keys) => keys.filter((key) => fields[key]).map((key) => fieldCard(fields[key]));

  $("bestIspOutput").innerHTML = `
    <article class="best-isp-card">
      <div class="best-isp-card-head">
        <div>
          <p class="eyebrow">Isp Optimized</p>
          <h3>Highest ${escapeHtml(item.metric_label)}</h3>
        </div>
        <div class="best-isp-metric">${fmt(item.case.isp_s, 2)} <span>s</span></div>
      </div>
      <p class="best-isp-note">${escapeHtml(item.message)}</p>
      ${renderBestIspSection("Simulation Parameters", [...simulationCards, ...capCards])}
      ${renderBestIspSection("Inputs", cardsForKeys(inputKeys))}
      ${renderBestIspSection("CEA Outputs", cardsForKeys(ceaKeys))}
      ${renderBestIspSection("Derived Sizing Outputs", cardsForKeys(sizingKeys))}
    </article>
  `;
}

function cardsFromFields(fields, hintPrefix = "Field") {
  void hintPrefix;
  return (fields || []).map((field) => ({
    label: field.label,
    value: formatCaseField(field.key, field.value),
    hint: hintForCaseField(field.key, field.label),
  }));
}

function buildTransientChartConfig(series, options) {
  return createLineChartConfig(series, {
    title: options.title,
    xLabel: "Time [s]",
    yLabel: options.yLabel,
    metricKey: options.metricKey,
    metricLabel: options.yLabel,
    filename: options.filename,
    height: options.height || 620,
    xDigits: 2,
    yDigits: options.yDigits ?? 2,
  });
}

function clearBlowdownCharts(message) {
  ["blowdownPressureChart", "blowdownMassFlowChart", "blowdownThrustChart", "blowdownStateChart"].forEach((hostId) => {
    $(hostId).innerHTML = chartEmptyState(message);
  });
}

function activeEstimationSource(results = state.results) {
  if (state.blowdownPreview?.status === "ready" && state.blowdownPreview.estimation_fields?.length) {
    return state.blowdownPreview;
  }
  if (results?.blowdown?.estimation_fields?.length) {
    return results.blowdown;
  }
  return null;
}

function renderEstimationsPanel(results = state.results) {
  const item = activeEstimationSource(results);
  if (!item) {
    $("estimationsOutput").innerHTML = chartEmptyState("Run a CEA sweep to populate the blowdown estimations and active calculation values.");
    return;
  }

  const estimationCards = cardsFromFields(item.estimation_fields, "Estimation field");
  const noteText = item.status === "ready"
    ? item.message
    : item.message || "Specific calculation values used by the preliminary 0D blowdown model.";

  $("estimationsOutput").innerHTML = `
    <article class="best-isp-card best-isp-card-compact">
      <p class="best-isp-note">${escapeHtml(noteText)}</p>
      ${renderTextListSection("Derived Basis", item.estimation_notes || [])}
      ${renderBestIspSection("Specific Values Used", estimationCards)}
      ${renderTextListSection("Model Assumptions", item.assumptions || [])}
    </article>
  `;
}

function renderBlowdownOutput(results) {
  const item = results?.blowdown;
  if (!item) {
    $("blowdownOutput").innerHTML = chartEmptyState("Run a CEA sweep to seed the preliminary 0D blowdown model.");
    clearBlowdownCharts("Run the 0D blowdown model to populate this chart.");
    return;
  }

  const seedCards = cardsFromFields(item.seed_case_fields, "CEA seed field");
  const derivedCards = cardsFromFields(item.derived_fields, "Derived field");
  const injectorEstimateCards = cardsFromFields(item.injector_estimate_fields, "Injector estimate field");
  const overrideCards = cardsFromFields(item.override_fields, "Override field");
  const initialStateCards = cardsFromFields(item.initial_state_fields, "Initial-state field");
  const finalStateCards = cardsFromFields(item.final_state_fields, "Final-state field");
  const controlCards = item.controls ? [
    {
      label: "Auto Run After CEA",
      value: item.auto_run_after_cea ? "Yes" : "No",
      hint: "Whether the blowdown solver starts automatically after a CEA sweep finishes",
    },
    {
      label: "UI Mode",
      value: item.controls.ui_mode === "advanced" ? "Advanced" : "Basic",
      hint: "Basic mode auto-derives low-level fields; advanced mode exposes manual overrides",
    },
    {
      label: "Tank Override",
      value: item.controls.tank.override_mass_volume ? "Enabled" : "Auto-derived",
      hint: "Whether tank mass and volume are manually overridden",
    },
    {
      label: "Regression Preset",
      value: item.controls.grain.regression_preset,
      hint: "Basic mode uses this preset to resolve the regression coefficients unless Custom is selected",
    },
    {
      label: "Injector Pressure-Drop Policy",
      value: item.controls.injector.pressure_drop_policy,
      hint: "Basic mode uses this simple policy to pick a project-default injector delta-p fraction",
    },
    {
      label: "Injector Override",
      value: item.controls.injector.override_total_area ? "Enabled" : "Auto-derived",
      hint: "Whether injector total area is manually overridden",
    },
    {
      label: "Initial Port Override",
      value: item.controls.grain.override_initial_port_radius ? "Enabled" : "Auto-derived",
      hint: "Whether initial port radius is manually overridden",
    },
    {
      label: "Grain Length Override",
      value: item.controls.grain.override_grain_length ? "Enabled" : "Auto-derived",
      hint: "Whether grain length is manually overridden",
    },
    {
      label: "Outer Radius Override",
      value: item.controls.grain.override_outer_radius ? "Enabled" : "Auto-derived",
      hint: "Whether outer radius is manually overridden",
    },
    {
      label: "Injector Delta-p Mode",
      value: item.controls.injector.delta_p_mode === "explicit" ? "Explicit" : "Fraction of Pc",
      hint: "How injector sizing delta-p is defined in the first-pass estimate",
    },
    {
      label: "Burn Time",
      value: `${fmt(item.controls.simulation.burn_time_s, 2)} s`,
      hint: "Requested transient duration",
    },
  ] : [];

  if (item.status !== "completed") {
    const statusMetric = {
      running: "Running",
      not_run: "Waiting",
      error: "Error",
      cancelled: "Cancelled",
    }[item.status] || "Pending";
    $("blowdownOutput").innerHTML = `
      <article class="best-isp-card">
        <div class="best-isp-card-head">
          <div>
            <p class="eyebrow">Preliminary 0D Blowdown</p>
            <h3>${escapeHtml(item.seed_case_source_label || "Highest Isp CEA Case")}</h3>
          </div>
          <div class="best-isp-metric">${escapeHtml(statusMetric)}</div>
        </div>
        <p class="best-isp-note">${escapeHtml(item.error ? `${item.message} ${item.error}` : item.message)}</p>
        ${renderBestIspSection("Blowdown Settings", controlCards)}
        ${renderBestIspSection("CEA Seed Case", seedCards)}
      </article>
    `;
    clearBlowdownCharts(item.message || "Run the 0D blowdown model to populate this chart.");
    return;
  }
  const summaryCards = cardsFromFields(item.summary_fields, "Summary field");

  $("blowdownOutput").innerHTML = `
    <article class="best-isp-card">
      <div class="best-isp-card-head">
        <div>
          <p class="eyebrow">Preliminary 0D Blowdown</p>
          <h3>${escapeHtml(item.seed_case_source_label || "Highest Isp CEA Case")}</h3>
        </div>
        <div class="best-isp-metric">${fmt(item.runtime_seconds, 2)} <span>s runtime</span></div>
      </div>
      <p class="best-isp-note">${escapeHtml(item.message)}</p>
      ${renderBestIspSection("Simulation Summary", summaryCards)}
      ${renderBestIspSection("Seeded 0D Design Inputs", derivedCards)}
      ${renderBestIspSection("Preliminary Injector and Feed Estimates", injectorEstimateCards)}
      ${renderBestIspSection("Override Sources", overrideCards)}
      ${renderBestIspSection("Initial 0D State", initialStateCards)}
      ${renderBestIspSection("Final 0D State", finalStateCards)}
      ${renderBestIspSection("Blowdown Settings", controlCards)}
      ${renderBestIspSection("CEA Seed Case", seedCards)}
    </article>
  `;
}

function renderBlowdownCharts(results) {
  const item = results?.blowdown;
  if (!item || item.status !== "completed" || !item.charts) {
    clearBlowdownCharts(item?.message || "Run the 0D blowdown model to populate this chart.");
    return;
  }

  renderChartInto("blowdownPressureChart", buildTransientChartConfig(item.charts.pressure_vs_time, {
    title: "0D Blowdown Pressures vs Time",
    yLabel: "Pressure [bar]",
    metricKey: "blowdown_pressure_vs_time",
    filename: "blowdown_pressures_vs_time.png",
  }));
  renderChartInto("blowdownMassFlowChart", buildTransientChartConfig(item.charts.mass_flow_vs_time, {
    title: "0D Blowdown Mass Flow vs Time",
    yLabel: "Mass Flow [kg/s]",
    metricKey: "blowdown_mass_flow_vs_time",
    filename: "blowdown_mass_flow_vs_time.png",
  }));
  renderChartInto("blowdownThrustChart", buildTransientChartConfig(item.charts.thrust_vs_time, {
    title: "0D Blowdown Thrust vs Time",
    yLabel: "Thrust [N]",
    metricKey: "blowdown_thrust_vs_time",
    filename: "blowdown_thrust_vs_time.png",
  }));
  renderChartInto("blowdownStateChart", buildTransientChartConfig(item.charts.state_vs_time, {
    title: "0D Blowdown State vs Time",
    yLabel: "State [-]",
    metricKey: "blowdown_state_vs_time",
    filename: "blowdown_state_vs_time.png",
  }));
}

function renderBlowdownResults(results) {
  renderBlowdownOutput(results);
  renderBlowdownCharts(results);
  renderEstimationsPanel(results);
}

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function rowsToCsv(headers, rows) {
  return [
    headers.map((header) => csvEscape(header)).join(","),
    ...rows.map((row) => row.map((value) => csvEscape(value)).join(",")),
  ].join("\r\n");
}

function makeDownloadUrl(csvText) {
  const url = URL.createObjectURL(new Blob([csvText], { type: "text/csv;charset=utf-8" }));
  state.downloadUrls.push(url);
  return url;
}

function clearDownloadUrls() {
  state.downloadUrls.forEach((url) => URL.revokeObjectURL(url));
  state.downloadUrls = [];
}

function renderCsvDownloads(results) {
  clearDownloadUrls();
  const fields = results.best_isp_case.fields.map((field) => ({ key: field.key, label: field.label }));
  const allCasesCsv = rowsToCsv(
    fields.map((field) => field.label),
    results.cases.map((item) => fields.map((field) => item[field.key])),
  );
  const bestIspCsv = rowsToCsv(
    ["key", "label", "value"],
    results.best_isp_case.fields.map((field) => [field.key, field.label, field.value]),
  );
  const allCasesUrl = makeDownloadUrl(allCasesCsv);
  const bestIspUrl = makeDownloadUrl(bestIspCsv);

  $("csvDownloads").innerHTML = `
    <div class="download-grid">
      <a class="download-card" href="${allCasesUrl}" download="cea_all_converged_cases.csv">
        <span class="download-title">All Converged Cases CSV</span>
        <span class="download-meta">${results.cases.length.toLocaleString()} rows, ${fields.length} columns</span>
      </a>
      <a class="download-card" href="${bestIspUrl}" download="cea_highest_isp_case.csv">
        <span class="download-title">Highest Isp Case CSV</span>
        <span class="download-meta">Optimized for Isp, ${fields.length} parameters</span>
      </a>
    </div>
  `;
}

function setHero(results) {
  $("caseCount").textContent = results.meta.case_count.toLocaleString();
  $("failureCount").textContent = results.meta.failure_count.toLocaleString();
  $("runtimeValue").textContent = `${fmt(results.meta.runtime_seconds, 1)} s`;
  $("heroTitle").textContent = "Sweep overview";
  const capText = results.controls.ae_at_cap_mode === "exit_diameter"
    ? `Cases exceeding ${fmt(results.controls.max_exit_diameter_cm, 1)} cm exit diameter are filtered out.`
    : `The sweep is capped at Ae/At ${fmt(results.controls.max_area_ratio, 2)}.`;
  $("heroSubtext").textContent = `Evaluated ${results.meta.total_combinations.toLocaleString()} candidate combinations at fuel ${fmt(results.controls.fuel_temperature_k, 2)} K, oxidizer ${fmt(results.controls.oxidizer_temperature_k, 2)} K, and ${fmt(results.controls.desired_infill_percent, 1)}% infill using ${results.meta.backend} with ${results.meta.cpu_workers} worker(s). ${capText}`;
  $("overviewMetricTitle").textContent = `Raw ${results.meta.selected_metric_label} vs O/F`;
}

function buildMetricSeries(results, metricKey) {
  const aeAtDigits = decimalPlacesForStep(results?.controls?.ae_at?.step, 6);
  const byAeAt = new Map();
  results.cases.forEach((row) => {
    const x = Number(row.of);
    const y = Number(row[metricKey]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }
    const aeAt = normalizeSweepValue(row.ae_at, aeAtDigits);
    if (!Number.isFinite(aeAt)) {
      return;
    }
    if (!byAeAt.has(aeAt)) {
      byAeAt.set(aeAt, []);
    }
    byAeAt.get(aeAt).push({ x, y });
  });

  return [...byAeAt.entries()]
    .sort(([left], [right]) => Number(left) - Number(right))
    .map(([aeAt, points]) => ({
      label: `Ae/At ${formatSweepValue(aeAt, aeAtDigits)}`,
      points,
    }));
}

function buildMetricChartConfigs(results) {
  state.chartConfigs = {};
  getMetricOptions().forEach((option) => {
    const rawSeries = buildMetricSeries(results, option.key);
    state.chartConfigs[option.key] = createLineChartConfig(rawSeries, {
      title: `Raw ${option.label} vs O/F`,
      xLabel: "O/F [-]",
      yLabel: option.label,
      metricKey: option.key,
      metricLabel: option.label,
      filename: `cea_${safeFileName(option.key)}_vs_of.png`,
      height: 740,
      xDigits: 2,
      yDigits: 2,
    });
  });
}

function selectFallbackMetric(results) {
  const selector = $("selected_metric");
  const requested = selector.value || results.meta.selected_metric || state.defaults?.selected_metric;
  if (requested && state.chartConfigs[requested]) {
    return requested;
  }
  return Object.keys(state.chartConfigs)[0] || null;
}

function renderSelectedMetricChart() {
  if (!state.results) {
    $("selected_metric").disabled = true;
    $("overviewMetricChart").innerHTML = chartEmptyState("Run a sweep to populate the chart.");
    return;
  }

  const selector = $("selected_metric");
  const metricKey = selectFallbackMetric(state.results);
  if (!metricKey) {
    selector.disabled = true;
    $("overviewMetricChart").innerHTML = chartEmptyState("No preloaded graph metrics are available.");
    return;
  }

  selector.value = metricKey;
  selector.disabled = false;
  state.activeMetric = metricKey;
  const config = state.chartConfigs[metricKey];
  $("overviewMetricTitle").textContent = `Raw ${config.metricLabel} vs O/F`;
  renderChartInto("overviewMetricChart", config);
}

function renderOverview(results) {
  buildMetricChartConfigs(results);
  renderSelectedMetricChart();
}

function onMetricSelectionChange() {
  if (!state.results) {
    return;
  }
  renderSelectedMetricChart();
  renderBestIspOutput(state.results);
  renderCalculationArticle(state.results);
}

function renderResults(results) {
  state.results = results;
  setHero(results);
  renderOverview(results);
  renderBestIspOutput(results);
  renderBlowdownResults(results);
  renderCsvDownloads(results);
  renderCalculationArticle(results);
  updateBlowdownButtonState(false);
  scheduleBlowdownPreview(50);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function stopPolling() {
  if (state.pollTimer !== null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function scheduleStatusPoll(delayMs = 700) {
  stopPolling();
  state.pollTimer = window.setTimeout(async () => {
    try {
      const status = await requestJson("/api/sweep-status");
      handleStatus(status);
    } catch (error) {
      toast(error.message, true);
      stopPolling();
      setFormBusy(false, false);
    }
  }, delayMs);
}

function handleStatus(status) {
  const previousKey = state.lastStatusKey;
  const currentKey = `${status.job_id}:${status.status}`;
  state.lastStatusKey = currentKey;
  showSweepStatus(status);

  const resultKey = status.result
    ? `${status.job_id}:${status.status}:${status.phase || ""}:${status.result?.blowdown?.status || "none"}`
    : null;

  if (status.result && resultKey !== state.renderedResultKey) {
    renderResults(status.result);
    state.renderedJobId = status.job_id;
    state.renderedResultKey = resultKey;
  }

  if (status.status === "running" || status.status === "stopping") {
    scheduleStatusPoll();
    return;
  }

  stopPolling();
  if (previousKey !== currentKey) {
    if (status.status === "completed") {
      toast(status.message || "Analysis complete.");
    } else if (status.status === "cancelled") {
      toast(status.message || "Analysis cancelled.");
    } else if (status.status === "error") {
      toast(status.error || status.message || "Analysis failed.", true);
    }
  }
}

async function loadDefaults() {
  const defaults = await requestJson("/api/default-config");
  state.defaults = defaults;
  populateForm(defaults);
  scheduleBlowdownPreview(50);
}

async function loadStatus() {
  const status = await requestJson("/api/sweep-status");
  handleStatus(status);
}

async function startSweep() {
  const status = await requestJson("/api/run-sweep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildPayload()),
  });
  handleStatus(status);
}

async function startBlowdown() {
  const status = await requestJson("/api/run-blowdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildBlowdownPayload()),
  });
  handleStatus(status);
}

async function stopSweep() {
  const status = await requestJson("/api/stop-sweep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  handleStatus(status);
}

async function onSweepSubmit(event) {
  event.preventDefault();
  try {
    if ($("runButton").classList.contains("is-stop") && !$("runButton").disabled) {
      await stopSweep();
    } else {
      await startSweep();
    }
  } catch (error) {
    toast(error.message, true);
    const status = await requestJson("/api/sweep-status").catch(() => null);
    if (status) {
      handleStatus(status);
    }
  }
}

async function onBlowdownRun() {
  try {
    await startBlowdown();
  } catch (error) {
    toast(error.message, true);
    const status = await requestJson("/api/sweep-status").catch(() => null);
    if (status) {
      handleStatus(status);
    }
  }
}

async function bootstrap() {
  initializeTheme();
  configureNumericInputs();
  attachFieldLabelTooltips();
  $("sweepForm").addEventListener("submit", onSweepSubmit);
  $("runBlowdownButton").addEventListener("click", onBlowdownRun);
  $("themeToggle").addEventListener("click", toggleTheme);
  $("ae_at_custom_enabled").addEventListener("change", updateAdvancedControls);
  $("ae_at_cap_mode").addEventListener("change", updateAdvancedControls);
  $("blowdown_ui_mode").addEventListener("change", updateAdvancedControls);
  $("blowdown_grain_regression_preset").addEventListener("change", updateAdvancedControls);
  $("blowdown_injector_pressure_drop_policy").addEventListener("change", updateAdvancedControls);
  $("blowdown_injector_delta_p_mode").addEventListener("change", updateAdvancedControls);
  $("blowdown_tank_override_mass_volume").addEventListener("change", updateAdvancedControls);
  $("blowdown_injector_override_total_area").addEventListener("change", updateAdvancedControls);
  $("blowdown_grain_override_initial_port_radius").addEventListener("change", updateAdvancedControls);
  $("blowdown_grain_override_grain_length").addEventListener("change", updateAdvancedControls);
  $("blowdown_grain_override_outer_radius").addEventListener("change", updateAdvancedControls);
  $("selected_metric").addEventListener("change", onMetricSelectionChange);
  document.querySelectorAll("#sweepForm input, #sweepForm select").forEach((node) => {
    if (node.id !== "selected_metric") {
      node.addEventListener("input", () => scheduleBlowdownPreview());
      node.addEventListener("change", () => scheduleBlowdownPreview());
    }
  });
  $("blowdown_tank_reset_override").addEventListener("click", () => {
    $("blowdown_tank_override_mass_volume").checked = false;
    updateAdvancedControls();
    scheduleBlowdownPreview(20);
  });
  $("blowdown_injector_reset_override").addEventListener("click", () => {
    $("blowdown_injector_override_total_area").checked = false;
    updateAdvancedControls();
    scheduleBlowdownPreview(20);
  });
  $("blowdown_grain_reset_initial_port_radius").addEventListener("click", () => {
    $("blowdown_grain_override_initial_port_radius").checked = false;
    updateAdvancedControls();
    scheduleBlowdownPreview(20);
  });
  $("blowdown_grain_reset_grain_length").addEventListener("click", () => {
    $("blowdown_grain_override_grain_length").checked = false;
    updateAdvancedControls();
    scheduleBlowdownPreview(20);
  });
  $("blowdown_grain_reset_outer_radius").addEventListener("click", () => {
    $("blowdown_grain_override_outer_radius").checked = false;
    updateAdvancedControls();
    scheduleBlowdownPreview(20);
  });
  $("chartModalClose").addEventListener("click", closeModal);
  document.addEventListener("click", (event) => {
    if (event.target.matches("[data-close-modal='true']")) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  });
  await loadDefaults();
  renderCalculationArticle();
  await loadStatus();
}

bootstrap().catch((error) => {
  toast(error.message, true);
});
