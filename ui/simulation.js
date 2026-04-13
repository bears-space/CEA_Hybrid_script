function $(id) {
  return document.getElementById(id);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function latestRunAssetUrl(relativePath) {
  return `/api/latest-run-download?relative_path=${encodeURIComponent(relativePath)}`;
}

function sectionParam() {
  return new URLSearchParams(window.location.search).get("section") || "";
}

function metricMarkup(metric) {
  const unit = metric?.unit ? ` ${metric.unit}` : "";
  return `
    <article class="metric-card metric-${escapeHtml(metric.emphasis || "neutral")}">
      <div class="metric-label">${escapeHtml(metric.label)}</div>
      <div class="metric-value">${escapeHtml(`${metric.value ?? "n/a"}${unit}`)}</div>
    </article>
  `;
}

function renderHeader(payload) {
  $("detailHeader").innerHTML = `
    <p class="eyebrow">Latest Run Section</p>
    <h1>${escapeHtml(payload.title)}</h1>
    <p class="hero-text">Interactive detail page built from the latest persisted artifacts for <code>${escapeHtml(payload.section)}</code>.</p>
    <div class="run-meta">
      <div><strong>Run ID:</strong> <code>${escapeHtml(payload.run_id || "")}</code></div>
      <div><strong>Requested Mode:</strong> <code>${escapeHtml(payload.requested_mode || "")}</code></div>
      <div><strong>Run Root:</strong> <code>${escapeHtml(payload.root || "")}</code></div>
    </div>
  `;
}

function renderMetrics(metrics) {
  $("detailMetricGrid").innerHTML = metrics?.length
    ? metrics.map(metricMarkup).join("")
    : '<div class="empty-state">No persisted metrics available.</div>';
}

function niceNumber(value) {
  if (!Number.isFinite(value)) {
    return "";
  }
  const abs = Math.abs(value);
  if (abs >= 1000 || (abs > 0 && abs < 0.01)) {
    return value.toExponential(2);
  }
  if (abs >= 100) {
    return value.toFixed(1);
  }
  if (abs >= 1) {
    return value.toFixed(2);
  }
  return value.toFixed(3);
}

const PALETTE = ["#125f4b", "#8a5d00", "#944b2d", "#2a6cb0", "#6a3ea1", "#267a34"];

function lineChartSvg(chart) {
  const width = 760;
  const height = 330;
  const margin = { top: 24, right: 24, bottom: 52, left: 76 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const allPoints = (chart.series || []).flatMap((series) => series.points || []);
  if (!allPoints.length) {
    return "";
  }
  let minX = Math.min(...allPoints.map((point) => point.x));
  let maxX = Math.max(...allPoints.map((point) => point.x));
  let minY = Math.min(...allPoints.map((point) => point.y));
  let maxY = Math.max(...allPoints.map((point) => point.y));
  if (minX === maxX) {
    minX -= 1;
    maxX += 1;
  }
  if (minY === maxY) {
    minY -= 1;
    maxY += 1;
  }
  const yPad = (maxY - minY) * 0.08;
  minY -= yPad;
  maxY += yPad;
  const x = (value) => margin.left + ((value - minX) / (maxX - minX)) * innerWidth;
  const y = (value) => margin.top + innerHeight - ((value - minY) / (maxY - minY)) * innerHeight;

  const grid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const yValue = minY + (maxY - minY) * ratio;
    const yPos = y(yValue);
    return `
      <line x1="${margin.left}" y1="${yPos}" x2="${width - margin.right}" y2="${yPos}" class="interactive-grid"/>
      <text x="${margin.left - 10}" y="${yPos + 4}" text-anchor="end" class="interactive-axis-label">${escapeHtml(niceNumber(yValue))}</text>
    `;
  }).join("");

  const xTicks = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const xValue = minX + (maxX - minX) * ratio;
    const xPos = x(xValue);
    return `
      <line x1="${xPos}" y1="${margin.top}" x2="${xPos}" y2="${height - margin.bottom}" class="interactive-grid interactive-grid-vertical"/>
      <text x="${xPos}" y="${height - margin.bottom + 18}" text-anchor="middle" class="interactive-axis-label">${escapeHtml(niceNumber(xValue))}</text>
    `;
  }).join("");

  const seriesMarkup = (chart.series || []).map((series, index) => {
    const color = PALETTE[index % PALETTE.length];
    const points = series.points || [];
    const path = points.map((point, pointIndex) => `${pointIndex === 0 ? "M" : "L"} ${x(point.x)} ${y(point.y)}`).join(" ");
    const stride = chart.kind === "scatter" ? 1 : Math.max(1, Math.ceil(points.length / 50));
    const markers = points.filter((_, pointIndex) => pointIndex % stride === 0 || pointIndex === points.length - 1).map((point) => `
      <circle cx="${x(point.x)}" cy="${y(point.y)}" r="${chart.kind === "scatter" ? 4.5 : 3.2}" fill="${color}" class="interactive-point">
        <title>${series.name}: ${chart.x_label} ${niceNumber(point.x)}, ${chart.y_label} ${niceNumber(point.y)}</title>
      </circle>
    `).join("");
    return `
      <path d="${path}" fill="none" stroke="${color}" stroke-width="${chart.kind === "scatter" ? 0 : 2.5}" />
      ${markers}
    `;
  }).join("");

  const legend = (chart.series || []).map((series, index) => `
    <div class="interactive-legend-item">
      <span class="interactive-legend-swatch" style="background:${PALETTE[index % PALETTE.length]}"></span>
      <span>${escapeHtml(series.name)}</span>
    </div>
  `).join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" class="interactive-chart-svg" role="img" aria-label="${escapeHtml(chart.title)}">
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" class="interactive-chart-bg"/>
      ${grid}
      ${xTicks}
      <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" class="interactive-axis"/>
      <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" class="interactive-axis"/>
      ${seriesMarkup}
      <text x="${width / 2}" y="${height - 10}" text-anchor="middle" class="interactive-axis-title">${escapeHtml(chart.x_label || "")}</text>
      <text x="18" y="${height / 2}" text-anchor="middle" transform="rotate(-90 18 ${height / 2})" class="interactive-axis-title">${escapeHtml(chart.y_label || "")}</text>
    </svg>
    <div class="interactive-legend">${legend}</div>
  `;
}

function barChartSvg(chart) {
  const width = 760;
  const height = 330;
  const margin = { top: 24, right: 24, bottom: 92, left: 72 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const bars = chart.bars || [];
  if (!bars.length) {
    return "";
  }
  const maxValue = Math.max(...bars.map((bar) => bar.value), 1);
  const barWidth = innerWidth / bars.length;
  const y = (value) => margin.top + innerHeight - (value / maxValue) * innerHeight;

  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = (maxValue * index) / 4;
    const yPos = y(value);
    return `
      <line x1="${margin.left}" y1="${yPos}" x2="${width - margin.right}" y2="${yPos}" class="interactive-grid"/>
      <text x="${margin.left - 10}" y="${yPos + 4}" text-anchor="end" class="interactive-axis-label">${escapeHtml(niceNumber(value))}</text>
    `;
  }).join("");

  const barsMarkup = bars.map((bar, index) => {
    const xPos = margin.left + index * barWidth + barWidth * 0.14;
    const rectWidth = barWidth * 0.72;
    const yPos = y(bar.value);
    const label = bar.label.length > 18 ? `${bar.label.slice(0, 18)}...` : bar.label;
    return `
      <rect x="${xPos}" y="${yPos}" width="${rectWidth}" height="${height - margin.bottom - yPos}" rx="8" fill="${PALETTE[index % PALETTE.length]}" class="interactive-bar">
        <title>${bar.label}: ${niceNumber(bar.value)}</title>
      </rect>
      <text x="${xPos + rectWidth / 2}" y="${height - margin.bottom + 12}" text-anchor="end" transform="rotate(-34 ${xPos + rectWidth / 2} ${height - margin.bottom + 12})" class="interactive-axis-label">${escapeHtml(label)}</text>
    `;
  }).join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" class="interactive-chart-svg" role="img" aria-label="${escapeHtml(chart.title)}">
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" class="interactive-chart-bg"/>
      ${grid}
      <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" class="interactive-axis"/>
      <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" class="interactive-axis"/>
      ${barsMarkup}
      <text x="${width / 2}" y="${height - 10}" text-anchor="middle" class="interactive-axis-title">${escapeHtml(chart.x_label || "")}</text>
      <text x="18" y="${height / 2}" text-anchor="middle" transform="rotate(-90 18 ${height / 2})" class="interactive-axis-title">${escapeHtml(chart.y_label || "")}</text>
    </svg>
  `;
}

function renderCharts(charts) {
  const host = $("detailChartGrid");
  if (!charts?.length) {
    host.innerHTML = '<div class="empty-state">No interactive charts available.</div>';
    return;
  }
  host.innerHTML = charts.map((chart) => `
    <article class="interactive-chart-card">
      <div class="chart-header">
        <h4>${escapeHtml(chart.title)}</h4>
      </div>
      ${chart.kind === "bar" ? barChartSvg(chart) : lineChartSvg(chart)}
    </article>
  `).join("");
}

function renderSvgs(svgCharts) {
  const host = $("detailSvgGrid");
  if (!svgCharts?.length) {
    host.innerHTML = '<div class="empty-state">No persisted SVG exports available.</div>';
    return;
  }
  host.innerHTML = svgCharts.map((chart) => `
    <article class="chart-card">
      <div class="chart-header">
        <h5>${escapeHtml(chart.title)}</h5>
      </div>
      <img class="chart-preview" src="${latestRunAssetUrl(chart.relative_path)}" alt="${escapeHtml(chart.title)}">
    </article>
  `).join("");
}

function renderNotes(notes) {
  $("detailNotesCard").innerHTML = notes?.length
    ? `<ul class="artifact-list">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
    : '<div class="empty-state">No notes available.</div>';
}

function renderDownloads(downloads) {
  $("detailDownloadsCard").innerHTML = downloads?.length
    ? `<ul class="artifact-list">${downloads.map((item) => `<li><a href="${latestRunAssetUrl(item.relative_path)}">${escapeHtml(item.relative_path)}</a></li>`).join("")}</ul>`
    : '<div class="empty-state">No downloads available.</div>';
}

async function init() {
  const section = sectionParam();
  if (!section) {
    throw new Error("Missing section query parameter.");
  }
  const payload = await requestJson(`/api/latest-run-section?section=${encodeURIComponent(section)}`);
  renderHeader(payload);
  renderMetrics(payload.metrics || []);
  renderCharts(payload.charts || []);
  renderSvgs(payload.svg_charts || []);
  renderNotes(payload.notes || []);
  renderDownloads(payload.downloads || []);
}

window.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    $("detailHeader").innerHTML = `<div class="status-card"><div class="status-badge status-error">error</div><p class="status-message">${escapeHtml(error.message)}</p></div>`;
  });
});
