const { createApp } = Vue;
const {
  PALETTE,
  barChartSvg,
  cellText,
  latestRunAssetUrl,
  lineChartSvg,
  prettyJson,
  requestJson,
} = window.WorkflowUiShared;

const SECTION_STEP_FALLBACK = {
  thermochemistry: "cea",
  performance: "nominal",
  analysis: "corners",
  geometry: "geometry",
  internal_ballistics: "internal_ballistics",
  injector_design: "injector_design",
  hydraulic_validation: "hydraulic_predict",
  structural: "structural_size",
  thermal: "thermal_size",
  nozzle_offdesign: "nozzle_offdesign",
  cfd: "cfd_plan",
  testing: "test_readiness",
};

function stepParam() {
  const params = new URLSearchParams(window.location.search);
  return params.get("step") || SECTION_STEP_FALLBACK[params.get("section") || ""] || "";
}

function tableIndex(tables) {
  return new Map((tables || []).map((table) => [table.key, table]));
}

function buildLineChartFromHint(hint, table) {
  if (!table?.rows?.length) {
    return null;
  }
  const grouped = new Map();
  table.rows.forEach((row) => {
    const xValue = row[hint.x_key];
    const yValue = row[hint.y_key];
    if (!Number.isFinite(Number(xValue)) || !Number.isFinite(Number(yValue))) {
      return;
    }
    const seriesName = hint.series_key ? String(row[hint.series_key] ?? "Series") : "Series";
    if (!grouped.has(seriesName)) {
      grouped.set(seriesName, []);
    }
    grouped.get(seriesName).push({ x: Number(xValue), y: Number(yValue) });
  });
  const series = Array.from(grouped.entries()).map(([name, points]) => ({
    name,
    points: points.sort((left, right) => left.x - right.x),
  })).filter((item) => item.points.length);
  if (!series.length) {
    return null;
  }
  return {
    kind: hint.kind,
    source_path: table.relative_path,
    series,
    title: hint.title,
    x_label: hint.x_label,
    y_label: hint.y_label,
  };
}

function buildBarChartFromHint(hint, table) {
  if (!table?.rows?.length) {
    return null;
  }
  const bars = [];
  table.rows.forEach((row) => {
    const label = row[hint.category_key];
    const value = row[hint.value_key];
    if (label === null || label === undefined || label === "" || !Number.isFinite(Number(value))) {
      return;
    }
    bars.push({ label: String(label), value: Number(value) });
  });
  if (!bars.length) {
    return null;
  }
  return {
    bars,
    kind: "bar",
    source_path: table.relative_path,
    title: hint.title,
    x_label: hint.x_label,
    y_label: hint.y_label,
  };
}

function buildCountBarChartFromHint(hint, table) {
  if (!table?.rows?.length) {
    return null;
  }
  const counts = new Map();
  table.rows.forEach((row) => {
    const label = row[hint.category_key];
    if (label === null || label === undefined || label === "") {
      return;
    }
    const key = String(label);
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  if (!counts.size) {
    return null;
  }
  return {
    bars: Array.from(counts.entries()).map(([label, value]) => ({ label, value })),
    kind: "bar",
    source_path: table.relative_path,
    title: hint.title,
    x_label: hint.x_label,
    y_label: hint.y_label,
  };
}

function numericColumns(table) {
  return (table.columns || []).filter((column) => (table.rows || []).some((row) => Number.isFinite(Number(row[column]))));
}

function categoryColumns(table) {
  return (table.columns || []).filter((column) => (table.rows || []).some((row) => typeof row[column] === "string" && row[column]));
}

function fallbackCharts(tables) {
  const charts = [];
  (tables || []).forEach((table) => {
    const numerics = numericColumns(table);
    const categories = categoryColumns(table);
    if (!numerics.length) {
      return;
    }
    if (table.columns?.includes("time_s")) {
      const seriesKey = ["region", "case_name", "target_name", "stage_name"].find((key) => table.columns.includes(key));
      numerics.filter((column) => column !== "time_s").slice(0, 3).forEach((column) => {
        charts.push({
          kind: "line",
          series_key: seriesKey,
          table_key: table.key,
          title: `${table.title}: ${column.replaceAll("_", " ")}`,
          x_key: "time_s",
          x_label: "Time [s]",
          y_key: column,
          y_label: column.replaceAll("_", " "),
        });
      });
      return;
    }
    if (categories.length) {
      const categoryKey = categories[0];
      numerics.slice(0, 2).forEach((column) => {
        charts.push({
          category_key: categoryKey,
          kind: "bar",
          table_key: table.key,
          title: `${table.title}: ${column.replaceAll("_", " ")}`,
          value_key: column,
          x_label: categoryKey.replaceAll("_", " "),
          y_label: column.replaceAll("_", " "),
        });
      });
      return;
    }
    if (numerics.length >= 2) {
      numerics.slice(1, 3).forEach((column) => {
        charts.push({
          kind: "scatter",
          table_key: table.key,
          title: `${table.title}: ${column.replaceAll("_", " ")}`,
          x_key: numerics[0],
          x_label: numerics[0].replaceAll("_", " "),
          y_key: column,
          y_label: column.replaceAll("_", " "),
        });
      });
    }
  });
  return charts.slice(0, 6);
}

function buildRenderedCharts(payload) {
  const tables = tableIndex(payload?.tables || []);
  const hints = payload?.chart_hints?.length ? payload.chart_hints : fallbackCharts(payload?.tables || []);
  return hints.map((hint) => {
    const table = tables.get(hint.table_key);
    if (hint.kind === "bar") {
      return buildBarChartFromHint(hint, table);
    }
    if (hint.kind === "count_bar") {
      return buildCountBarChartFromHint(hint, table);
    }
    return buildLineChartFromHint(hint, table);
  }).filter(Boolean);
}

function isInputArtifact(relativePath) {
  return /(?:_used|_source)\.json$/i.test(relativePath || "");
}

function makeJsonCard(title, sourceLabel, content, cardKey, relativePath = "") {
  return {
    cardKey,
    content: content || {},
    kind: "json-preview",
    relativePath,
    sourceLabel,
    title,
  };
}

function makeTablePreviewCard(table) {
  return {
    cardKey: `table-preview:${table.relative_path}`,
    columns: table.columns || [],
    kind: "table-preview",
    meta: [`${table.rows?.length || 0} rows | ${table.columns?.length || 0} columns`],
    relativePath: table.relative_path,
    rows: table.rows || [],
    sourceLabel: table.relative_path,
    title: table.title,
  };
}

function makeTableSummaryCard(table) {
  const columns = (table.columns || []).slice(0, 8).join(", ");
  return {
    cardKey: `table-summary:${table.relative_path}`,
    kind: "summary",
    meta: [
      `${table.rows?.length || 0} rows | ${table.columns?.length || 0} columns`,
      `Columns: ${columns || "n/a"}`,
    ],
    relativePath: table.relative_path,
    sourceLabel: table.relative_path,
    title: table.title,
  };
}

function makeJsonSummaryCard(artifact) {
  const keys = Object.keys(artifact.content || {}).slice(0, 10).join(", ");
  return {
    cardKey: `json-summary:${artifact.relative_path}`,
    content: artifact.content || {},
    kind: "json-summary",
    meta: [`Top-level keys: ${keys || "n/a"}`],
    relativePath: artifact.relative_path,
    sourceLabel: artifact.relative_path,
    title: artifact.title,
  };
}

function makeSvgSummaryCard(artifact) {
  return {
    cardKey: `svg-summary:${artifact.relative_path}`,
    kind: "summary",
    meta: ["Persisted SVG export from the workflow run."],
    relativePath: artifact.relative_path,
    sourceLabel: artifact.relative_path,
    title: artifact.title,
  };
}

const IoValue = {
  props: {
    value: {
      required: false,
      type: null,
    },
  },
  computed: {
    isPrimitive() {
      return ["string", "number", "boolean"].includes(typeof this.value);
    },
    jsonText() {
      return prettyJson(this.value);
    },
    primitiveText() {
      return String(this.value);
    },
  },
  template: `
    <div v-if="value === null || value === undefined" class="workflow-io-value-empty">Value not available.</div>
    <div v-else-if="isPrimitive" class="workflow-io-value"><code>{{ primitiveText }}</code></div>
    <details v-else class="workflow-io-value-details">
      <summary>View Value</summary>
      <pre class="json-preview">{{ jsonText }}</pre>
    </details>
  `,
};

const IoItem = {
  components: {
    IoValue,
  },
  props: {
    item: {
      required: true,
      type: null,
    },
  },
  computed: {
    isStringItem() {
      return typeof this.item === "string";
    },
  },
  template: `
    <li class="workflow-io-item">
      <template v-if="isStringItem">
        {{ item }}
      </template>
      <template v-else>
        <div class="workflow-io-name-row">
          <code>{{ item.name || "unknown" }}</code>
          <span v-if="item.optional" class="workflow-io-flag">Optional</span>
        </div>
        <div class="workflow-io-description">{{ item.description || "" }}</div>
        <io-value :value="item.value"></io-value>
        <div class="workflow-io-source">Source: <code>{{ item.value_source || "n/a" }}</code></div>
      </template>
    </li>
  `,
};

const ChartCard = {
  props: {
    chart: {
      required: true,
      type: Object,
    },
  },
  data() {
    return {
      hiddenSeries: [],
    };
  },
  computed: {
    hasLegend() {
      return (this.chart.series || []).length > 1;
    },
    svgMarkup() {
      const currentChart = this.visibleChart;
      return currentChart.kind === "bar" ? barChartSvg(currentChart) : lineChartSvg(currentChart);
    },
    visibleChart() {
      if (!this.chart.series) {
        return this.chart;
      }
      return {
        ...this.chart,
        series: this.chart.series.filter((series) => !this.hiddenSeries.includes(series.name)),
      };
    },
  },
  methods: {
    isHidden(name) {
      return this.hiddenSeries.includes(name);
    },
    swatch(index) {
      return PALETTE[index % PALETTE.length];
    },
    toggleSeries(name) {
      if (this.hiddenSeries.includes(name)) {
        this.hiddenSeries = this.hiddenSeries.filter((item) => item !== name);
        return;
      }
      this.hiddenSeries = [...this.hiddenSeries, name];
    },
  },
  template: `
    <article class="interactive-chart-card">
      <div class="chart-header">
        <h4>{{ chart.title }}</h4>
        <p class="chart-source-label">Source: <code>{{ chart.source_path || "derived from persisted CSV" }}</code></p>
      </div>
      <div class="interactive-chart-body" v-html="svgMarkup"></div>
      <div class="interactive-legend">
        <button
          v-for="(series, index) in chart.series || []"
          :key="series.name"
          type="button"
          class="chart-series-toggle"
          :class="{ 'is-hidden': isHidden(series.name) }"
          @click="toggleSeries(series.name)"
        >
          <span class="interactive-legend-swatch" :style="{ background: swatch(index) }"></span>
          <span>{{ series.name }}</span>
        </button>
        <template v-if="!hasLegend"></template>
      </div>
    </article>
  `,
};

const ArtifactCard = {
  props: {
    card: {
      required: true,
      type: Object,
    },
  },
  methods: {
    cellText,
    latestRunAssetUrl,
    prettyJson,
  },
  template: `
    <article class="source-card">
      <div class="source-card-top">
        <h4>{{ card.title }}</h4>
        <a v-if="card.relativePath" class="button" :href="latestRunAssetUrl(card.relativePath)">Download</a>
      </div>
      <div class="source-card-path"><code>{{ card.sourceLabel }}</code></div>
      <p v-for="line in card.meta || []" :key="line" class="source-card-meta">{{ line }}</p>

      <pre v-if="card.kind === 'json-preview' || card.kind === 'json-summary'" class="json-preview">{{ prettyJson(card.content) }}</pre>

      <div v-else-if="card.kind === 'table-preview'">
        <div v-if="card.columns && card.columns.length" class="table-preview-shell">
          <table class="table-preview">
            <thead>
              <tr>
                <th v-for="column in card.columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!card.rows.length">
                <td :colspan="card.columns.length">No rows available.</td>
              </tr>
              <tr v-for="(row, rowIndex) in card.rows" :key="rowIndex">
                <td v-for="column in card.columns" :key="column"><code>{{ cellText(row[column]) }}</code></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state">No columns were found in this CSV artifact.</div>
      </div>
    </article>
  `,
};

createApp({
  components: {
    ArtifactCard,
    ChartCard,
    IoItem,
  },
  data() {
    return {
      error: "",
      payload: null,
    };
  },
  computed: {
    configSnapshot() {
      return this.payload?.config_snapshot || null;
    },
    downloads() {
      return this.payload?.downloads || [];
    },
    latestRunText() {
      if (!this.payload) {
        return "";
      }
      return this.payload.run_id
        ? `Latest run detail built from ${this.payload.run_id}.`
        : "No latest-run artifacts were found for this step yet.";
    },
    metrics() {
      return this.payload?.metrics || [];
    },
    notes() {
      return this.payload?.notes || [];
    },
    renderedCharts() {
      return this.payload ? buildRenderedCharts(this.payload) : [];
    },
    sourceCards() {
      if (!this.payload) {
        return [];
      }
      const cards = [];
      (this.payload.tables || []).forEach((table) => {
        cards.push(makeTableSummaryCard(table));
      });
      (this.payload.json_artifacts || []).forEach((artifact) => {
        cards.push(makeJsonSummaryCard(artifact));
      });
      (this.payload.svg_exports || []).forEach((artifact) => {
        cards.push(makeSvgSummaryCard(artifact));
      });
      return cards;
    },
    valueGroups() {
      if (!this.payload) {
        return [];
      }
      const inputCards = [];
      const outputCards = [];

      if (this.payload.kind === "config" && this.payload.config_snapshot) {
        inputCards.push(
          makeJsonCard(
            this.payload.config_snapshot.title || this.payload.title,
            this.payload.config_snapshot.source || "Current default editor payload",
            this.payload.config_snapshot.content || {},
            `config:${this.payload.step}`,
          ),
        );
      }

      (this.payload.json_artifacts || []).forEach((artifact) => {
        const card = makeJsonCard(
          artifact.title,
          artifact.relative_path,
          artifact.content || {},
          `json:${artifact.relative_path}`,
          artifact.relative_path,
        );
        if (isInputArtifact(artifact.relative_path)) {
          inputCards.push(card);
        } else {
          outputCards.push(card);
        }
      });

      (this.payload.tables || []).forEach((table) => {
        outputCards.push(makeTablePreviewCard(table));
      });

      return [
        {
          cards: inputCards,
          description: this.payload.kind === "config"
            ? "This config node exposes the full editable payload currently driving the workflow."
            : "These persisted input payloads were consumed or carried into the selected step.",
          emptyText: this.payload.kind === "config"
            ? "No config payload is available for this node."
            : "No persisted input payloads were attached to this step.",
          title: this.payload.kind === "config" ? "Configured Values" : "Input Payloads",
        },
        {
          cards: outputCards,
          description: "These JSON and CSV artifacts were generated by the selected step and are rendered inline in full.",
          emptyText: "No generated JSON or CSV values were attached to this step.",
          title: "Generated Values",
        },
      ];
    },
  },
  methods: {
    ioItemKey(item) {
      if (typeof item === "string") {
        return item;
      }
      return `${item?.name || "unknown"}-${item?.value_source || ""}`;
    },
    latestRunAssetUrl,
    prettyJson,
  },
  async mounted() {
    try {
      const step = stepParam();
      if (!step) {
        throw new Error("Missing step query parameter.");
      }
      this.payload = await requestJson(`/api/workflow-step?step=${encodeURIComponent(step)}`);
    } catch (error) {
      this.error = error.message;
    }
  },
}).mount("#app");
