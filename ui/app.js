const palette = ["#4de2cf", "#ffb454", "#7ab7ff", "#d4a5ff", "#ff7d96", "#b7ef57", "#60f0db", "#f6a6db", "#ffd166"];
const state = {
  defaults: null,
  results: null,
  pollTimer: null,
  renderedJobId: null,
  lastStatusKey: null,
};

function $(id) {
  return document.getElementById(id);
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return Number(value).toFixed(digits).replace(/\.?0+$/, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.remove("hidden");
  node.style.background = isError ? "rgba(111, 28, 46, 0.96)" : "rgba(6, 15, 22, 0.96)";
  window.clearTimeout(toast._timer);
  toast._timer = window.setTimeout(() => node.classList.add("hidden"), 3200);
}

function setFormBusy(isBusy, isStopping = false) {
  document.querySelectorAll("#sweepForm input, #sweepForm select").forEach((node) => {
    node.disabled = isBusy;
  });
  if (!isBusy) {
    updateHybridModelControls();
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
  $("pc_bar").value = defaults.pc_bar;
  $("ae_at_start").value = defaults.ae_at.start;
  $("ae_at_stop").value = defaults.ae_at.stop;
  $("ae_at_step").value = defaults.ae_at.step;
  $("of_start").value = defaults.of.start;
  $("of_stop").value = defaults.of.stop;
  $("of_count").value = defaults.of.count;
  $("desired_infill_percent").value = defaults.desired_infill_percent;
  $("hybrid_port_diameter_mm").value = defaults.hybrid_design.port_diameter_m * 1000;
  $("hybrid_burn_time_s").value = defaults.hybrid_design.burn_time_s;
  $("hybrid_characteristic_length_m").value = defaults.hybrid_design.characteristic_length_m;
  $("hybrid_regression_a_mps").value = defaults.hybrid_design.regression_a_mps;
  $("hybrid_regression_n").value = defaults.hybrid_design.regression_n;

  const temperatureSelect = $("reactant_temperature_k");
  temperatureSelect.innerHTML = "";
  defaults.reactant_temperature_options.forEach((value) => {
    const node = document.createElement("option");
    node.value = String(value);
    node.textContent = `${fmt(value, 2)} K`;
    if (Math.abs(Number(value) - Number(defaults.reactant_temperature_k)) < 1e-9) {
      node.selected = true;
    }
    temperatureSelect.appendChild(node);
  });

  const objectiveSelect = $("objective_metric");
  objectiveSelect.innerHTML = "";
  defaults.metric_options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.key;
    node.textContent = option.label;
    if (option.key === defaults.objective_metric) {
      node.selected = true;
    }
    objectiveSelect.appendChild(node);
  });

  const regressionSelect = $("hybrid_regression_model");
  regressionSelect.innerHTML = "";
  defaults.regression_models.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.key;
    node.textContent = option.label;
    if (option.key === defaults.hybrid_design.regression_model) {
      node.selected = true;
    }
    regressionSelect.appendChild(node);
  });
  regressionSelect.onchange = updateHybridModelControls;
  updateHybridModelControls();
}

function updateHybridModelControls() {
  const regressionModel = $("hybrid_regression_model").value;
  const isManual = regressionModel === "manual";
  $("hybrid_regression_a_mps").disabled = !isManual;
  $("hybrid_regression_n").disabled = !isManual;
  const modelInfo = state.defaults?.regression_models?.find((item) => item.key === regressionModel);
  const modelText = modelInfo ? `${modelInfo.description} ` : "";
  $("hybridSizingExplain").innerHTML = `${modelText}<code>D_p</code> is the initial circular fuel-port diameter. Pre-chamber length uses an empirical axial showerhead estimate, and post-chamber length is solved from the target characteristic length.`;
}

function buildPayload() {
  return {
    target_thrust_n: Number($("target_thrust_n").value),
    pc_bar: Number($("pc_bar").value),
    objective_metric: $("objective_metric").value,
    reactant_temperature_k: Number($("reactant_temperature_k").value),
    desired_infill_percent: Number($("desired_infill_percent").value),
    ae_at: {
      start: Number($("ae_at_start").value),
      stop: Number($("ae_at_stop").value),
      step: Number($("ae_at_step").value),
    },
    of: {
      start: Number($("of_start").value),
      stop: Number($("of_stop").value),
      count: Number($("of_count").value),
    },
    hybrid_design: {
      regression_model: $("hybrid_regression_model").value,
      port_diameter_m: Number($("hybrid_port_diameter_mm").value) / 1000,
      burn_time_s: Number($("hybrid_burn_time_s").value),
      characteristic_length_m: Number($("hybrid_characteristic_length_m").value),
      regression_a_mps: Number($("hybrid_regression_a_mps").value),
      regression_n: Number($("hybrid_regression_n").value),
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
    context.fillStyle = "#09141c";
    context.fillRect(0, 0, width, height);
    context.fillStyle = "#0d1821";
    context.fillRect(geometry.plotLeft, geometry.plotTop, geometry.plotWidth, geometry.plotHeight);
    context.strokeStyle = "#223444";
    context.lineWidth = 1 * dpr;
    context.strokeRect(geometry.plotLeft, geometry.plotTop, geometry.plotWidth, geometry.plotHeight);

    const yTicks = buildTicks(viewY.min, viewY.max, 6);
    context.font = `${13 * dpr}px "Aptos", "Segoe UI Variable Text", sans-serif`;
    context.fillStyle = "#97aab8";
    context.textAlign = "right";
    yTicks.forEach((value) => {
      const ratio = (viewY.max - value) / (viewY.max - viewY.min);
      const y = geometry.plotTop + ratio * geometry.plotHeight;
      context.strokeStyle = "#223444";
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
      context.strokeStyle = "#15222c";
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
      context.strokeStyle = "#f3fbff";
      context.lineWidth = 2.4 * dpr;
      context.fillStyle = item.color;
      context.beginPath();
      context.arc(hoveredPoint.screenPoint.x, hoveredPoint.screenPoint.y, 7.4 * dpr, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }
    context.restore();

    context.fillStyle = "#edf6ff";
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

function renderSummaryCards(results) {
  const meta = results.meta;
  const controls = results.controls;
  const cards = [
    {
      label: "Primary Objective",
      value: meta.objective_metric_label,
      hint: "Best-case value across the current O/F scan",
    },
    {
      label: "Reactant Temperature",
      value: `${fmt(controls.reactant_temperature_k, 2)} K`,
      hint: "Applied to both fuel and oxidizer",
    },
    {
      label: "Desired Infill",
      value: `${fmt(controls.desired_infill_percent, 1)} %`,
      hint: `ABS fraction ${fmt(controls.desired_infill_percent / 100, 3)}`,
    },
    {
      label: "Sweep Density",
      value: `${controls.ae_at_values.length} x ${controls.of_values.length}`,
      hint: "Ae/At samples x O/F samples",
    },
  ];

  $("summaryCards").innerHTML = cards.map((card) => `
    <article class="summary-card">
      <div class="label">${escapeHtml(card.label)}</div>
      <div class="value">${escapeHtml(card.value)}</div>
      <div class="hint">${escapeHtml(card.hint)}</div>
    </article>
  `).join("");
}

function renderOptimizerCards(results) {
  $("optimizerCards").innerHTML = results.optimizations.map((item) => `
    <article class="optimizer-card">
      <h3>Optimized for ${escapeHtml(item.value_label)}</h3>
      <div class="metric">${fmt(item.value, 2)} <span class="metric-unit">${escapeHtml(item.value_label)}</span></div>
      <dl>
        <div><dt>Objective</dt><dd>${escapeHtml(item.objective)}</dd></div>
        <div><dt>Infill</dt><dd>${fmt(item.case.abs_vol_frac * 100, 1)}%</dd></div>
        <div><dt>O/F</dt><dd>${fmt(item.case.of, 2)}</dd></div>
        <div><dt>Ae/At</dt><dd>${fmt(item.case.ae_at, 2)}</dd></div>
        <div><dt>Reactant T</dt><dd>${fmt(item.case.fuel_temp_k, 2)} K</dd></div>
        <div><dt>mdot</dt><dd>${fmt(item.case.mdot_total_kg_s, 3)} kg/s</dd></div>
        <div><dt>Chamber T</dt><dd>${fmt(item.case.tc_k, 0)} K</dd></div>
      </dl>
    </article>
  `).join("");
}

function renderOptimizerTable(results) {
  $("optimizerTableBody").innerHTML = results.optimizations.map((item) => `
    <tr>
      <td>${escapeHtml(item.objective)}</td>
      <td>${fmt(item.value, 2)} ${escapeHtml(item.value_label)}</td>
      <td>${fmt(item.case.abs_vol_frac * 100, 1)}%</td>
      <td>${fmt(item.case.of, 2)}</td>
      <td>${fmt(item.case.ae_at, 2)}</td>
      <td>${fmt(item.case.fuel_temp_k, 2)} K</td>
      <td>${fmt(item.case.isp_vac_s, 2)} s</td>
      <td>${fmt(item.case.mdot_total_kg_s, 3)} kg/s</td>
      <td>${fmt(item.case.dt_mm, 2)} mm</td>
      <td>${fmt(item.case.de_mm, 2)} mm</td>
    </tr>
  `).join("");
}

function fmtMm(valueM, digits = 1) {
  return `${fmt(valueM * 1000, digits)} mm`;
}

function fmtFlow(value) {
  return `${fmt(value, 3)} kg/s`;
}

function fmtRate(value) {
  return `${fmt(value * 1000, 3)} mm/s`;
}

function fmtPostLength(geometry) {
  if (geometry.post_chamber_length_m <= 1e-9) {
    return "0 mm";
  }
  return fmtMm(geometry.post_chamber_length_m, 1);
}

function renderHybridDiagram(item) {
  const geometry = item.hybrid_design.geometry;
  const equations = item.hybrid_design.equations;
  const assumptions = item.hybrid_design.assumptions;
  const totalLength = geometry.total_chamber_length_m + (geometry.chamber_inner_diameter_m * 1.2);
  const scaleX = 430 / totalLength;
  const chamberHeight = Math.max(56, Math.min(110, geometry.chamber_inner_diameter_m * 1800));
  const portHeight = chamberHeight * (geometry.port_diameter_m / geometry.chamber_inner_diameter_m);
  const yCenter = 110;
  const chamberTop = yCenter - chamberHeight / 2;
  const portTop = yCenter - portHeight / 2;
  const x0 = 26;
  const preW = geometry.pre_chamber_length_m * scaleX;
  const grainW = geometry.grain_length_m * scaleX;
  const postW = geometry.post_chamber_length_m * scaleX;
  const nozzleBaseX = x0 + preW + grainW + postW;
  const nozzleTipX = nozzleBaseX + geometry.chamber_inner_diameter_m * 0.72 * scaleX;
  const throatHalf = Math.max(8, chamberHeight * 0.16);
  const nozzleExitHalf = chamberHeight * 0.44;

  return `
    <svg class="hybrid-diagram" viewBox="0 0 520 220" role="img" aria-label="${escapeHtml(item.objective)} hybrid layout">
      <defs>
        <linearGradient id="shell-${escapeHtml(item.key)}" x1="0" x2="1">
          <stop offset="0%" stop-color="#153240"/>
          <stop offset="100%" stop-color="#0e242f"/>
        </linearGradient>
        <linearGradient id="flame-${escapeHtml(item.key)}" x1="0" x2="1">
          <stop offset="0%" stop-color="#37d7c5"/>
          <stop offset="55%" stop-color="#69b7ff"/>
          <stop offset="100%" stop-color="#ffb454"/>
        </linearGradient>
      </defs>
      <rect x="${x0}" y="${chamberTop}" width="${preW + grainW + postW}" height="${chamberHeight}" rx="18" fill="url(#shell-${escapeHtml(item.key)})" stroke="#4a6577"/>
      <rect x="${x0 + preW}" y="${chamberTop}" width="${grainW}" height="${chamberHeight}" fill="rgba(255,180,84,0.08)" stroke="#ffb454" stroke-dasharray="5 4"/>
      <rect x="${x0}" y="${portTop}" width="${preW + grainW + postW}" height="${portHeight}" rx="${portHeight / 2}" fill="rgba(10,19,26,0.95)" stroke="url(#flame-${escapeHtml(item.key)})"/>
      <path d="M ${nozzleBaseX} ${yCenter - throatHalf} L ${nozzleTipX} ${yCenter - nozzleExitHalf} L ${nozzleTipX} ${yCenter + nozzleExitHalf} L ${nozzleBaseX} ${yCenter + throatHalf} Z" fill="rgba(17,34,45,0.96)" stroke="#8abed8"/>
      <circle cx="${x0 - 10}" cy="${yCenter}" r="10" fill="#31c9c9"/>
      <path d="M ${x0 - 10} ${yCenter} L ${x0} ${yCenter}" stroke="#31c9c9" stroke-width="4" stroke-linecap="round"/>
      <text x="${x0 - 18}" y="${yCenter - 18}" fill="#9ddfda" font-size="12" font-family="Aptos, Segoe UI, sans-serif">Injector</text>
      <text x="${x0 + preW / 2}" y="${chamberTop - 10}" fill="#d9e8f3" font-size="12" text-anchor="middle" font-family="Aptos, Segoe UI, sans-serif">Pre ${fmtMm(geometry.pre_chamber_length_m, 0)}</text>
      <text x="${x0 + preW + grainW / 2}" y="${chamberTop - 10}" fill="#ffd39b" font-size="12" text-anchor="middle" font-family="Aptos, Segoe UI, sans-serif">Grain ${fmtMm(geometry.grain_length_m, 0)}</text>
      <text x="${x0 + preW + grainW + postW / 2}" y="${chamberTop - 10}" fill="#d9e8f3" font-size="12" text-anchor="middle" font-family="Aptos, Segoe UI, sans-serif">Post ${fmtMm(geometry.post_chamber_length_m, 0)}</text>
      <text x="${x0 + preW + grainW / 2}" y="${yCenter + 6}" fill="#8edfe0" font-size="12" text-anchor="middle" font-family="Aptos, Segoe UI, sans-serif">Dp ${fmtMm(geometry.port_diameter_m, 0)}</text>
      <text x="${x0 + preW + grainW / 2}" y="${chamberTop + chamberHeight + 18}" fill="#a6b8c5" font-size="12" text-anchor="middle" font-family="Aptos, Segoe UI, sans-serif">Dc ${fmtMm(geometry.chamber_inner_diameter_m, 0)}</text>
      <text x="${nozzleTipX - 8}" y="${yCenter - nozzleExitHalf - 10}" fill="#9dd1ff" font-size="12" text-anchor="end" font-family="Aptos, Segoe UI, sans-serif">Nozzle</text>
      <text x="26" y="194" fill="#a6b8c5" font-size="12" font-family="Aptos, Segoe UI, sans-serif">mdot ox ${fmtFlow(equations.mdot_ox_kg_s)}</text>
      <text x="190" y="194" fill="#a6b8c5" font-size="12" font-family="Aptos, Segoe UI, sans-serif">rdot ${fmtRate(equations.regression_rate_mps)}</text>
      <text x="330" y="194" fill="#a6b8c5" font-size="12" font-family="Aptos, Segoe UI, sans-serif">burn ${fmt(geometry.burn_time_s, 1)} s</text>
      <text x="26" y="210" fill="#708695" font-size="11" font-family="Aptos, Segoe UI, sans-serif">${escapeHtml(assumptions.pre_chamber_method)}</text>
    </svg>
  `;
}

function renderHybridSizing(results) {
  $("hybridSizingGrid").innerHTML = results.optimizations.map((item) => {
    const geometry = item.hybrid_design.geometry;
    const equations = item.hybrid_design.equations;
    const assumptions = item.hybrid_design.assumptions;
    return `
      <article class="hybrid-card">
        <h3>Hybrid Layout for ${escapeHtml(item.value_label)}</h3>
        <div class="hybrid-value">${fmt(item.value, 2)} <span class="metric-unit">${escapeHtml(item.value_label)}</span></div>
        <div class="hybrid-meta">${escapeHtml(item.objective)} optimum. Single-port hybrid estimate for ${fmt(item.case.abs_vol_frac * 100, 1)}% infill and O/F ${fmt(item.case.of, 2)}.</div>
        ${renderHybridDiagram(item)}
        <div class="hybrid-stats">
          <div><div class="hybrid-stat-label">Objective</div><div class="hybrid-stat-value">${escapeHtml(item.objective)}</div></div>
          <div><div class="hybrid-stat-label">mdot ox</div><div class="hybrid-stat-value">${fmtFlow(equations.mdot_ox_kg_s)}</div></div>
          <div><div class="hybrid-stat-label">mdot fuel</div><div class="hybrid-stat-value">${fmtFlow(equations.mdot_f_total_kg_s)}</div></div>
          <div><div class="hybrid-stat-label">Total Fuel Mass</div><div class="hybrid-stat-value">${fmt(geometry.fuel_mass_total_kg, 2)} kg</div></div>
          <div><div class="hybrid-stat-label">Gox</div><div class="hybrid-stat-value">${fmt(equations.gox_kg_m2_s, 1)} kg/m²/s</div></div>
          <div><div class="hybrid-stat-label">Port Diameter</div><div class="hybrid-stat-value">${fmtMm(geometry.port_diameter_m)}</div></div>
          <div><div class="hybrid-stat-label">Final Port / Dc</div><div class="hybrid-stat-value">${fmtMm(geometry.final_port_diameter_m)} / ${fmtMm(geometry.chamber_inner_diameter_m)}</div></div>
          <div><div class="hybrid-stat-label">Grain Length</div><div class="hybrid-stat-value">${fmtMm(geometry.grain_length_m)}</div></div>
          <div><div class="hybrid-stat-label">Volumetric Loading</div><div class="hybrid-stat-value">${fmt(geometry.volumetric_loading, 3)}</div></div>
          <div><div class="hybrid-stat-label">Pre / Post</div><div class="hybrid-stat-value">${fmtMm(geometry.pre_chamber_length_m, 0)} / ${fmtPostLength(geometry)}</div></div>
          <div><div class="hybrid-stat-label">L* min / target / achieved</div><div class="hybrid-stat-value">${fmt(geometry.characteristic_length_minimum_m, 2)} / ${fmt(geometry.characteristic_length_target_m, 2)} / ${fmt(geometry.characteristic_length_achieved_m, 2)} m</div></div>
          <div><div class="hybrid-stat-label">Regression model</div><div class="hybrid-stat-value">${escapeHtml(assumptions.regression_model_label)}</div></div>
          <div><div class="hybrid-stat-label">OF / F / c*</div><div class="hybrid-stat-value">${fmt(equations.of_check, 3)} / ${fmt(equations.thrust_from_cf_n, 0)} N / ${fmt(equations.cstar_from_flow_mps, 1)} m/s</div></div>
        </div>
      </article>
    `;
  }).join("");
}

function renderHybridSizingTable(results) {
  $("hybridSizingTableBody").innerHTML = results.optimizations.map((item) => {
    const geometry = item.hybrid_design.geometry;
    const equations = item.hybrid_design.equations;
    return `
      <tr>
        <td>${escapeHtml(item.objective)}</td>
        <td>${fmtFlow(equations.mdot_ox_kg_s)}</td>
        <td>${fmtFlow(equations.mdot_f_total_kg_s)}</td>
        <td>${fmt(geometry.fuel_mass_total_kg, 2)} kg</td>
        <td>${fmt(equations.gox_kg_m2_s, 1)} kg/m²/s</td>
        <td>${fmtRate(equations.regression_rate_mps)}</td>
        <td>${fmtMm(geometry.port_diameter_m, 1)}</td>
        <td>${fmtMm(geometry.chamber_inner_diameter_m, 1)}</td>
        <td>${fmtMm(geometry.grain_length_m, 1)}</td>
        <td>${fmtMm(geometry.pre_chamber_length_m, 1)}</td>
        <td>${fmtPostLength(geometry)}</td>
        <td>${fmt(geometry.burn_time_s, 1)} s</td>
        <td>${fmt(equations.of_check, 3)}</td>
        <td>${fmt(equations.thrust_from_cf_n, 1)} N</td>
        <td>${fmt(equations.cstar_from_flow_mps, 1)} m/s</td>
      </tr>
    `;
  }).join("");
}

function setHero(results) {
  $("caseCount").textContent = results.meta.case_count.toLocaleString();
  $("failureCount").textContent = results.meta.failure_count.toLocaleString();
  $("runtimeValue").textContent = `${fmt(results.meta.runtime_seconds, 1)} s`;
  $("heroTitle").textContent = `Objective: ${results.meta.objective_metric_label}`;
  $("heroSubtext").textContent = `Evaluated ${results.meta.total_combinations.toLocaleString()} combinations at ${fmt(results.controls.reactant_temperature_k, 2)} K and ${fmt(results.controls.desired_infill_percent, 1)}% infill using ${results.meta.backend} with ${results.meta.cpu_workers} worker(s). The plots below are rendered in-browser from raw sweep data.`;
  $("overviewMetricTitle").textContent = `Raw ${results.meta.objective_metric_label} vs O/F`;
}

function renderOverview(results) {
  const rawSeries = results.charts.raw_objective_by_ae_at.map((series) => ({
    label: series.label,
    points: series.points.map((point) => ({ x: point.x, y: point.y })),
  }));
  renderChartInto("overviewMetricChart", createLineChartConfig(rawSeries, {
    title: `Raw ${results.meta.objective_metric_label} vs O/F`,
    xLabel: "O/F [-]",
    yLabel: results.meta.objective_metric_label,
    height: 740,
    xDigits: 2,
    yDigits: 2,
  }));

  renderChartInto("overviewObjectiveAeAtChart", createLineChartConfig([{
    label: results.charts.best_objective_by_ae_at.label,
    points: results.charts.best_objective_by_ae_at.points.map((point) => ({ x: point.x, y: point.y })),
  }], {
    title: `Best ${results.meta.objective_metric_label} vs Ae/At`,
    xLabel: "Ae/At [-]",
    yLabel: results.meta.objective_metric_label,
    height: 940,
    xDigits: 2,
    yDigits: 2,
  }));

  renderChartInto("overviewBestOfChart", createLineChartConfig([{
    label: results.charts.best_of_by_ae_at.label,
    points: results.charts.best_of_by_ae_at.points.map((point) => ({ x: point.x, y: point.y })),
  }], {
    title: "Best O/F vs Ae/At",
    xLabel: "Ae/At [-]",
    yLabel: "Best O/F [-]",
    height: 700,
    xDigits: 2,
    yDigits: 2,
  }));
}

function renderResults(results) {
  state.results = results;
  setHero(results);
  renderSummaryCards(results);
  renderOptimizerCards(results);
  renderOptimizerTable(results);
  renderHybridSizing(results);
  renderHybridSizingTable(results);
  renderOverview(results);
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
  $("sweepForm").addEventListener("submit", onSweepSubmit);
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
  await loadStatus();
}

bootstrap().catch((error) => {
  toast(error.message, true);
});
