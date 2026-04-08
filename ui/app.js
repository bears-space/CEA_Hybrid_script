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
  seed_oxidizer_temp_k: "From the latest highest-Isp CEA case oxidizer temperature.",
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
  tank_initial_mass_kg: "Uses the loaded oxidizer mass unless a manual tank override is active.",
  initial_port_area_mm2: "A_port,0 = mdot_ox / target_initial_gox.",
  initial_port_radius_mm: "R_port,0 = 0.5 * sqrt(4 * mdot_ox / (pi * N_ports * Gox_0)).",
  initial_regression_rate_mm_s: "rdot_0 = a * Gox_0^n.",
  grain_length_m: "Lg = mdot_f / (rho_f * N_ports * pi * D_port,0 * rdot_0).",
  grain_outer_radius_mm: "R_outer = sqrt(R_port,0^2 + V_fuel / (N_ports * pi * Lg)).",
  injector_delta_p_bar: "Either explicit injector delta-p or injector_delta_p_fraction_of_pc * Pc.",
  injector_total_area_mm2: "A_inj = mdot_ox / (Cd * sqrt(2 * rho_ox_liq(T_ox) * dP_inj)).",
  injector_area_per_hole_mm2: "Injector total area divided evenly by hole count.",
  injector_hole_diameter_mm: "Equivalent hole diameter = sqrt(4 * A_inj_total / (pi * N_holes)).",
  tank_mass_volume_source: "Shows whether tank mass/volume are auto-derived or manually overridden.",
  injector_total_area_source: "Shows whether injector total area is auto-derived or manually overridden.",
  initial_port_source: "Shows whether initial port radius is auto-derived or manually overridden.",
  grain_length_source: "Shows whether grain length is auto-derived or manually overridden.",
  outer_radius_source: "Shows whether outer grain radius is auto-derived or manually overridden.",
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

function infoDot(text, label = "More information") {
  return `<button class="info-dot" type="button" data-tip="${escapeHtml(text)}" aria-label="${escapeHtml(label)}">i</button>`;
}

function labelWithTip(label, tipText, labelText) {
  return `${escapeHtml(label)} ${infoDot(tipText, labelText || `Explain ${label}`)}`;
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
            When those modes are enabled, the backend derives tank, grain, and blend inputs from the seeded highest-Isp CEA case and the requested burn time.
          </p>
          <div class="calc-equation">mdot_total = F / (g0 * Isp)
mdot_ox = (O/F) / (1 + O/F) * mdot_total
mdot_f = mdot_total / (1 + O/F)
m_required = mdot * t_b
m_loaded = m_required / usable_fraction</div>
          <div class="calc-equation">V_tank = m_ox_loaded / (rho_ox_liq * fill_fraction)
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
  $("blowdown_tank_initial_temp_k").value = blowdown.tank.initial_temp_k;
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
  $("blowdown_injector_delta_p_mode").value = blowdown.injector.delta_p_mode;
  $("blowdown_injector_delta_p_pa").value = blowdown.injector.delta_p_pa / 1e5;
  $("blowdown_injector_delta_p_fraction_of_pc").value = blowdown.injector.delta_p_fraction_of_pc;
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
  const isAdvanced = $("blowdown_ui_mode").value === "advanced";
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
  $("blowdown_tank_initial_temp_k").disabled = !isAdvanced;
  $("blowdown_injector_total_area_mm2").disabled = !injectorOverride;
  $("blowdown_grain_initial_port_radius_mm").disabled = !portOverride;
  $("blowdown_grain_length_m").disabled = !lengthOverride;
  $("blowdown_grain_outer_radius_mm").disabled = !outerOverride;
  const explicitDeltaP = $("blowdown_injector_delta_p_mode").value === "explicit";
  $("blowdown_injector_delta_p_pa").disabled = !explicitDeltaP;
  $("blowdown_injector_delta_p_fraction_of_pc").disabled = explicitDeltaP;
  updateBlowdownButtonState(false);
}

function buildBlowdownPayload() {
  return {
    auto_run_after_cea: $("blowdown_auto_run_after_cea").checked,
    ui_mode: $("blowdown_ui_mode").value,
    seed_case: "highest_isp",
    tank: {
      volume_l: parseNumericInput("blowdown_tank_volume_l", "Blowdown tank volume"),
      initial_mass_kg: parseNumericInput("blowdown_tank_initial_mass_kg", "Blowdown initial tank mass"),
      initial_temp_k: parseNumericInput("blowdown_tank_initial_temp_k", "Blowdown initial tank temperature"),
      usable_oxidizer_fraction: parseNumericInput("blowdown_tank_usable_oxidizer_fraction", "Blowdown usable oxidizer fraction"),
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
      cd: parseNumericInput("blowdown_injector_cd", "Blowdown injector Cd"),
      hole_count: parseNumericInput("blowdown_injector_hole_count", "Blowdown injector hole count", { integer: true }),
      total_area_mm2: parseNumericInput("blowdown_injector_total_area_mm2", "Blowdown injector total area"),
      override_total_area: $("blowdown_injector_override_total_area").checked,
      delta_p_mode: $("blowdown_injector_delta_p_mode").value,
      delta_p_pa: parseNumericInput("blowdown_injector_delta_p_pa", "Blowdown injector delta-p") * 1e5,
      delta_p_fraction_of_pc: parseNumericInput("blowdown_injector_delta_p_fraction_of_pc", "Blowdown injector delta-p fraction of chamber pressure"),
    },
    grain: {
      abs_density_kg_m3: state.defaults?.blowdown?.grain?.abs_density_kg_m3 ?? 1050.0,
      paraffin_density_kg_m3: state.defaults?.blowdown?.grain?.paraffin_density_kg_m3 ?? 930.0,
      a_reg_si: parseNumericInput("blowdown_grain_a_reg_si", "Blowdown regression coefficient a"),
      n_reg: parseNumericInput("blowdown_grain_n_reg", "Blowdown regression exponent n"),
      port_count: parseNumericInput("blowdown_grain_port_count", "Blowdown grain port count", { integer: true }),
      target_initial_gox_kg_m2_s: parseNumericInput("blowdown_grain_target_initial_gox_kg_m2_s", "Blowdown target initial oxidizer flux"),
      initial_port_radius_mm: parseNumericInput("blowdown_grain_initial_port_radius_mm", "Blowdown initial port radius"),
      grain_length_m: parseNumericInput("blowdown_grain_length_m", "Blowdown grain length"),
      fuel_usable_fraction: parseNumericInput("blowdown_grain_fuel_usable_fraction", "Blowdown fuel usable fraction"),
      outer_radius_mm: parseNumericInput("blowdown_grain_outer_radius_mm", "Blowdown outer grain radius", { allowBlank: true }),
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
    hint: BLOWDOWN_FORMULA_HINTS[field.key] || `Field: ${field.key}`,
  }));
}

function renderBlowdownPreview(preview) {
  state.blowdownPreview = preview;
  if (!preview) {
    $("blowdownLivePreview").innerHTML = chartEmptyState("Run a CEA sweep to unlock live blowdown sizing estimates.");
    return;
  }
  if (preview.status !== "ready") {
    const text = preview.error ? `${preview.message} ${preview.error}` : preview.message;
    $("blowdownLivePreview").innerHTML = `<div class="empty-state">${escapeHtml(text || "Live sizing preview is unavailable.")}</div>`;
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
      message: "Live sizing preview needs valid inputs.",
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
      <div class="compact-output-label">${escapeHtml(card.label)}</div>
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
    hint: `Field: ${field.key}`,
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
    return value ?? "-";
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
  return (fields || []).map((field) => ({
    label: field.label,
    value: formatCaseField(field.key, field.value),
    hint: BLOWDOWN_FORMULA_HINTS[field.key] || `${hintPrefix}: ${field.key}`,
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
        ${renderTextListSection("Assumptions and Estimations", item.assumptions)}
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
      ${renderTextListSection("Assumptions and Estimations", item.assumptions)}
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
  const byAeAt = new Map();
  results.cases.forEach((row) => {
    const x = Number(row.of);
    const y = Number(row[metricKey]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }
    const aeAt = row.ae_at;
    if (!byAeAt.has(aeAt)) {
      byAeAt.set(aeAt, []);
    }
    byAeAt.get(aeAt).push({ x, y });
  });

  return [...byAeAt.entries()]
    .sort(([left], [right]) => Number(left) - Number(right))
    .map(([aeAt, points]) => ({
      label: `Ae/At ${Number(aeAt).toLocaleString(undefined, { maximumFractionDigits: 6 })}`,
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
  $("sweepForm").addEventListener("submit", onSweepSubmit);
  $("runBlowdownButton").addEventListener("click", onBlowdownRun);
  $("themeToggle").addEventListener("click", toggleTheme);
  $("ae_at_custom_enabled").addEventListener("change", updateAdvancedControls);
  $("ae_at_cap_mode").addEventListener("change", updateAdvancedControls);
  $("blowdown_ui_mode").addEventListener("change", updateAdvancedControls);
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
