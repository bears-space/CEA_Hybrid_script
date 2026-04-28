(function initWorkflowUiShared(globalScope) {
  const PALETTE = ["#125f4b", "#8a5d00", "#944b2d", "#2a6cb0", "#6a3ea1", "#267a34", "#7b4057"];

  async function requestJson(url, options) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...(options || {}),
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

  function formatJson(value) {
    return JSON.stringify(value ?? {}, null, 2);
  }

  function prettyJson(value) {
    return JSON.stringify(value ?? {}, null, 2);
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

  function latestRunAssetUrl(relativePath) {
    return `/api/latest-run-download?relative_path=${encodeURIComponent(relativePath)}`;
  }

  function cellText(value) {
    if (value === null || value === undefined) {
      return "";
    }
    if (typeof value === "object") {
      return prettyJson(value);
    }
    return String(value);
  }

  function formatMetricValue(metric) {
    const value = metric?.value;
    if (value === null || value === undefined || value === "") {
      return "n/a";
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return `${value}${metric?.unit ? ` ${metric.unit}` : ""}`;
    }
    return `${value}${metric?.unit ? ` ${metric.unit}` : ""}`;
  }

  function lineChartSvg(chart) {
    const width = 960;
    const height = 420;
    const margin = { top: 28, right: 28, bottom: 56, left: 82 };
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
      const stride = chart.kind === "scatter" ? 1 : Math.max(1, Math.ceil(points.length / 80));
      const markers = points
        .filter((_, pointIndex) => pointIndex % stride === 0 || pointIndex === points.length - 1)
        .map((point) => `
          <circle cx="${x(point.x)}" cy="${y(point.y)}" r="${chart.kind === "scatter" ? 5 : 3.4}" fill="${color}" class="interactive-point">
            <title>${series.name}: ${chart.x_label} ${niceNumber(point.x)}, ${chart.y_label} ${niceNumber(point.y)}</title>
          </circle>
        `).join("");
      const hoverTargets = points.map((point) => `
        <circle cx="${x(point.x)}" cy="${y(point.y)}" r="${chart.kind === "scatter" ? 9 : 7}" fill="${color}" class="interactive-hover-target">
          <title>${series.name}: ${chart.x_label} ${niceNumber(point.x)}, ${chart.y_label} ${niceNumber(point.y)}</title>
        </circle>
      `).join("");
      return `
        <path d="${path}" fill="none" stroke="${color}" stroke-width="${chart.kind === "scatter" ? 0 : 2.8}" />
        ${markers}
        ${hoverTargets}
      `;
    }).join("");

    return `
      <svg viewBox="0 0 ${width} ${height}" class="interactive-chart-svg" role="img" aria-label="${escapeHtml(chart.title)}">
        <rect x="0" y="0" width="${width}" height="${height}" rx="18" class="interactive-chart-bg"/>
        ${grid}
        ${xTicks}
        <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" class="interactive-axis"/>
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" class="interactive-axis"/>
        ${seriesMarkup}
        <text x="${width / 2}" y="${height - 12}" text-anchor="middle" class="interactive-axis-title">${escapeHtml(chart.x_label || "")}</text>
        <text x="18" y="${height / 2}" text-anchor="middle" transform="rotate(-90 18 ${height / 2})" class="interactive-axis-title">${escapeHtml(chart.y_label || "")}</text>
      </svg>
    `;
  }

  function barChartSvg(chart) {
    const width = 960;
    const height = 420;
    const margin = { top: 28, right: 28, bottom: 110, left: 78 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const bars = chart.bars || [];
    if (!bars.length) {
      return "";
    }
    const maxValue = Math.max(...bars.map((bar) => bar.value), 1);
    const barWidth = innerWidth / Math.max(bars.length, 1);
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
      const label = String(bar.label || "").length > 22 ? `${String(bar.label).slice(0, 22)}...` : String(bar.label);
      return `
        <rect x="${xPos}" y="${yPos}" width="${rectWidth}" height="${height - margin.bottom - yPos}" rx="8" fill="${PALETTE[index % PALETTE.length]}" class="interactive-bar">
          <title>${bar.label}: ${niceNumber(bar.value)}</title>
        </rect>
        <text x="${xPos + rectWidth / 2}" y="${height - margin.bottom + 14}" text-anchor="end" transform="rotate(-34 ${xPos + rectWidth / 2} ${height - margin.bottom + 14})" class="interactive-axis-label">${escapeHtml(label)}</text>
      `;
    }).join("");

    return `
      <svg viewBox="0 0 ${width} ${height}" class="interactive-chart-svg" role="img" aria-label="${escapeHtml(chart.title)}">
        <rect x="0" y="0" width="${width}" height="${height}" rx="18" class="interactive-chart-bg"/>
        ${grid}
        <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" class="interactive-axis"/>
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" class="interactive-axis"/>
        ${barsMarkup}
        <text x="${width / 2}" y="${height - 14}" text-anchor="middle" class="interactive-axis-title">${escapeHtml(chart.x_label || "")}</text>
        <text x="18" y="${height / 2}" text-anchor="middle" transform="rotate(-90 18 ${height / 2})" class="interactive-axis-title">${escapeHtml(chart.y_label || "")}</text>
      </svg>
    `;
  }

  globalScope.WorkflowUiShared = Object.freeze({
    PALETTE,
    barChartSvg,
    cellText,
    escapeHtml,
    formatJson,
    formatMetricValue,
    latestRunAssetUrl,
    lineChartSvg,
    niceNumber,
    prettyJson,
    requestJson,
  });
}(window));
