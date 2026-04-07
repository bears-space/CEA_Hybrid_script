const palette = ["#0f766e", "#b86a2d", "#345c7c", "#7c5aa6", "#a3475d", "#5c7f37", "#2d8d88", "#9a6742", "#536a7a"];
const THEME_STORAGE_KEY = "ceaHybridTheme";
const state = {
  defaults: null,
  results: null,
  pollTimer: null,
  renderedJobId: null,
  lastStatusKey: null,
  downloadUrls: [],
};

function $(id) {
  return document.getElementById(id);
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
  const metricLabel = results?.meta?.selected_metric_label || state.defaults?.selected_metric || "selected metric";
  const fuelTemperature = results?.controls?.fuel_temperature_k ?? state.defaults?.fuel_temperature_k;
  const oxidizerTemperature = results?.controls?.oxidizer_temperature_k ?? state.defaults?.oxidizer_temperature_k;
  const infill = results?.controls?.desired_infill_percent ?? state.defaults?.desired_infill_percent;

  $("calculationArticle").innerHTML = `
    <div class="calc-article-shell">
      <nav class="calc-article-nav">
        <h3>Contents</h3>
        <a href="#calc-thermo">1. Thermochemical core</a>
        <a href="#calc-selection">2. Variable selection</a>
        <a href="#calc-limits">3. Model limits</a>
        <a href="#calc-references">4. References</a>
      </nav>
      <div class="calc-article-body">
        <div class="calc-callout">
          The current UI state is configured around <strong>${escapeHtml(String(metricLabel))}</strong>,
          fuel temperature <strong>${fuelTemperature !== undefined ? `${fmt(fuelTemperature, 2)} K` : "not yet loaded"}</strong>,
          oxidizer temperature <strong>${oxidizerTemperature !== undefined ? `${fmt(oxidizerTemperature, 2)} K` : "not yet loaded"}</strong>,
          and infill <strong>${infill !== undefined ? `${fmt(infill, 1)}%` : "not yet loaded"}</strong>.
          This NASA CEA setup is specifically for an N2O and paraffin engine with ABS structure. The backend reports CEA outputs and minimal thrust-normalized nozzle sizing derived from those CEA outputs.
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
sizing: mdot_total_kg_s, at_m2, ae_m2, dt_mm, de_mm, de_cm</div>
          <p>
            To add or remove reported values later, change that file first. The CSV writer, plot metric selector,
            labels, and UI payloads all consume the same selection.
          </p>
        </section>

        <section class="calc-section" id="calc-limits">
          <h3>3. Model limits</h3>
          <ul>
            <li>It does not resolve finite-rate combustion, droplet breakup, or injector spray physics. NASA CEA assumes chemical equilibrium for the solved state.</li>
            <li>It does not perform hybrid regression, injector, grain, chamber, or structural sizing.</li>
            <li>Nozzle sizing assumes circular-equivalent throat and exit areas and uses CEA <code>c*</code> and <code>Isp</code>.</li>
          </ul>
        </section>

        <section class="calc-section calc-reference" id="calc-references">
          <h3>4. References</h3>
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
    button.textContent = "Stop Sweep";
  } else {
    button.textContent = "Run Sweep";
  }
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
    running: "Sweep running",
    stopping: "Stopping sweep",
    completed: "Sweep complete",
    cancelled: "Sweep cancelled",
    error: "Sweep failed",
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
  updateAdvancedControls();
}

function updateAdvancedControls() {
  const customEnabled = $("ae_at_custom_enabled").checked;
  $("aeAtCustomFields").disabled = !customEnabled;
  const capMode = $("ae_at_cap_mode").value;
  $("max_exit_diameter_cm").disabled = capMode !== "exit_diameter";
  $("max_area_ratio").disabled = capMode !== "area_ratio";
}

function buildPayload() {
  return {
    target_thrust_n: Number($("target_thrust_n").value),
    max_exit_diameter_cm: Number($("max_exit_diameter_cm").value),
    max_area_ratio: Number($("max_area_ratio").value),
    ae_at_cap_mode: $("ae_at_cap_mode").value,
    pc_bar: Number($("pc_bar").value),
    selected_metric: $("selected_metric").value,
    fuel_temperature_k: Number($("fuel_temperature_k").value),
    oxidizer_temperature_k: Number($("oxidizer_temperature_k").value),
    desired_infill_percent: Number($("desired_infill_percent").value),
    ae_at: {
      custom_enabled: $("ae_at_custom_enabled").checked,
      start: Number($("ae_at_start").value),
      stop: Number($("ae_at_stop").value),
      step: Number($("ae_at_step").value),
      cf_search_upper_bound: state.defaults?.ae_at?.cf_search_upper_bound ?? 3.0,
    },
    of: {
      start: Number($("of_start").value),
      stop: Number($("of_stop").value),
      count: Number($("of_count").value),
    },
  };
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

function formatCaseField(key, value) {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value !== "number") {
    return value ?? "-";
  }
  if (key.endsWith("_frac") || key === "cf" || key === "gamma_e") {
    return fmt(value, 4);
  }
  if (key === "ae_at" || key === "of" || key.endsWith("_cm") || key.endsWith("_mm")) {
    return fmt(value, 2);
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
      value: results.meta.selected_metric_label,
      hint: "Metric shown on the raw O/F chart",
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

function renderOverview(results) {
  const rawSeries = results.charts.raw_metric_by_ae_at.map((series) => ({
    label: series.label,
    points: series.points.map((point) => ({ x: point.x, y: point.y })),
  }));
  renderChartInto("overviewMetricChart", createLineChartConfig(rawSeries, {
    title: `Raw ${results.meta.selected_metric_label} vs O/F`,
    xLabel: "O/F [-]",
    yLabel: results.meta.selected_metric_label,
    height: 740,
    xDigits: 2,
    yDigits: 2,
  }));
}

function renderResults(results) {
  state.results = results;
  setHero(results);
  renderBestIspOutput(results);
  renderCsvDownloads(results);
  renderOverview(results);
  renderCalculationArticle(results);
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

  if (status.result && status.job_id !== state.renderedJobId) {
    renderResults(status.result);
    state.renderedJobId = status.job_id;
  }

  if (status.status === "running" || status.status === "stopping") {
    scheduleStatusPoll();
    return;
  }

  stopPolling();
  if (previousKey !== currentKey) {
    if (status.status === "completed") {
      toast("Sweep complete.");
    } else if (status.status === "cancelled") {
      toast("Sweep cancelled.");
    } else if (status.status === "error") {
      toast(status.error || "Sweep failed.", true);
    }
  }
}

async function loadDefaults() {
  const defaults = await requestJson("/api/default-config");
  state.defaults = defaults;
  populateForm(defaults);
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

async function bootstrap() {
  initializeTheme();
  $("sweepForm").addEventListener("submit", onSweepSubmit);
  $("themeToggle").addEventListener("click", toggleTheme);
  $("ae_at_custom_enabled").addEventListener("change", updateAdvancedControls);
  $("ae_at_cap_mode").addEventListener("change", updateAdvancedControls);
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
