const { createApp } = Vue;
const {
  formatJson,
  formatMetricValue,
  latestRunAssetUrl,
  requestJson,
} = window.WorkflowUiShared;

const EDITOR_DEFINITIONS = [
  {
    key: "design",
    modelKey: "design",
    payloadKey: "design_config",
    title: "Design Config",
    tag: "Required for most modes",
    textareaId: "designConfig",
  },
  {
    key: "cea",
    modelKey: "cea",
    payloadKey: "cea_config",
    title: "CEA Config",
    tag: "Used by thermochemistry-aware modes",
    textareaId: "ceaConfig",
  },
  {
    key: "hydraulic",
    modelKey: "hydraulic",
    payloadKey: "hydraulic_validation_config",
    title: "Hydraulic Validation Config",
    tag: "Used by hydraulic prediction and calibration",
    textareaId: "hydraulicConfig",
  },
  {
    key: "structural",
    modelKey: "structural",
    payloadKey: "structural_config",
    title: "Structural Config",
    tag: "Used by structural sizing",
    textareaId: "structuralConfig",
  },
  {
    key: "thermal",
    modelKey: "thermal",
    payloadKey: "thermal_config",
    title: "Thermal Config",
    tag: "Used by thermal sizing",
    textareaId: "thermalConfig",
  },
  {
    key: "nozzleOffdesign",
    modelKey: "nozzleOffdesign",
    payloadKey: "nozzle_offdesign_config",
    title: "Nozzle Off-Design Config",
    tag: "Used by launch-environment and off-design checks",
    textareaId: "nozzleOffdesignConfig",
  },
  {
    key: "cfd",
    modelKey: "cfd",
    payloadKey: "cfd_config",
    title: "CFD Config",
    tag: "Used by CFD planning, case export, result ingest, and correction application",
    textareaId: "cfdConfig",
  },
  {
    key: "testing",
    modelKey: "testing",
    payloadKey: "testing_config",
    title: "Testing Config",
    tag: "Used by campaign planning, dataset ingest, model comparison, calibration, and readiness gates",
    textareaId: "testingConfig",
  },
];

const EDITOR_LABELS = Object.freeze(
  Object.fromEntries(EDITOR_DEFINITIONS.map((editor) => [editor.key, editor.title])),
);

function executionSummaryForMode(modeKey) {
  if (["cea", "nominal", "oat", "corners", "hydraulic_predict", "hydraulic_calibrate", "hydraulic_compare"].includes(modeKey)) {
    return "Runs only this selected workflow.";
  }
  if (["geometry", "internal_ballistics", "injector_design", "structural_size"].includes(modeKey)) {
    return "Runs the selected workflow and auto-builds prerequisite geometry or injector artifacts when needed.";
  }
  if (["thermal_size", "nozzle_offdesign"].includes(modeKey)) {
    return "Runs the selected workflow and also generates its structural and thermal prerequisites inside the same run.";
  }
  if (String(modeKey || "").startsWith("cfd_")) {
    return "Runs the selected CFD workflow and builds upstream geometry, structural, thermal, and nozzle dependencies inside the same run.";
  }
  if (String(modeKey || "").startsWith("test_")) {
    return "Runs the selected testing workflow and builds upstream dependencies first; CFD planning is also included when the testing config asks for CFD context.";
  }
  return "Runs the selected workflow.";
}

function emptyEditors() {
  return {
    design: "{}",
    cea: "{}",
    hydraulic: "{}",
    structural: "{}",
    thermal: "{}",
    nozzleOffdesign: "{}",
    cfd: "{}",
    testing: "{}",
  };
}

createApp({
  data() {
    return {
      busy: false,
      defaults: null,
      editorDefinitions: EDITOR_DEFINITIONS,
      editors: emptyEditors(),
      latestRun: null,
      modes: [],
      outputDir: "output",
      pollTimer: null,
      selectedMode: "nominal",
      statusSnapshot: {
        status: "idle",
        message: "Ready.",
        logs: [],
      },
    };
  },
  computed: {
    activeSummary() {
      if (this.statusSnapshot?.result) {
        return {
          labelMode: "Mode",
          labelRunId: "Run ID",
          lines: this.statusSnapshot.result.summary_lines || [],
          mode: this.statusSnapshot.result.mode || "unknown",
          runId: this.statusSnapshot.result.run_id || "unknown",
          runRoot: this.statusSnapshot.result.run_root || "",
        };
      }
      if (!this.latestRunManifest) {
        return null;
      }
      const items = this.latestRun?.dashboard?.summary_items || [];
      return {
        labelMode: "Requested Mode",
        labelRunId: "Latest Run",
        lines: items.length
          ? items.map((item) => `${item.label}: ${item.value}`)
          : ["Manifest summary is not available for this run."],
        mode: this.latestRun?.requested_mode || "unknown",
        runId: this.latestRun?.run_id || "unknown",
        runRoot: this.latestRun?.root || "",
      };
    },
    artifactSections() {
      return Object.entries(this.latestRun?.artifacts_by_section || {}).map(([name, rows]) => ({ name, rows }));
    },
    latestRunManifest() {
      return this.latestRun?.manifest || null;
    },
    manifestSections() {
      return Object.entries(this.latestRunManifest?.sections || {}).map(([name, path]) => ({ name, path }));
    },
    modeGuideItems() {
      if (!this.selectedModeDefinition) {
        return [];
      }
      const editorNames = (this.selectedModeDefinition.editors || []).map((key) => EDITOR_LABELS[key] || key);
      return [
        { label: "Selected Mode", value: this.selectedModeDefinition.title },
        { label: "What To Edit", value: editorNames.join(", ") || "No config editor is needed." },
        {
          label: "Defaults",
          value: "All editors are preloaded with effective project defaults. Leave them unchanged unless you want to override something.",
        },
        { label: "Run Button Behavior", value: executionSummaryForMode(this.selectedModeDefinition.key) },
        {
          label: "Run Full Sequence",
          value: "Runs the default-safe end-to-end chain in order, from CEA through CFD/test planning, and skips ingest/calibration modes that require external datasets.",
        },
      ];
    },
    persistedChartGroups() {
      return this.latestRun?.dashboard?.chart_groups || [];
    },
    persistedMetrics() {
      return this.latestRun?.dashboard?.metrics || [];
    },
    selectedModeDefinition() {
      return this.modes.find((mode) => mode.key === this.selectedMode) || null;
    },
    statusBadgeClass() {
      const status = this.statusSnapshot?.status || "idle";
      if (status === "running") {
        return "status-running";
      }
      if (status === "completed") {
        return "status-completed";
      }
      if (status === "error") {
        return "status-error";
      }
      return "status-idle";
    },
    statusLogs() {
      return this.statusSnapshot?.logs || [];
    },
  },
  methods: {
    applyDefaults(defaults) {
      this.outputDir = defaults.output_dir || "output";
      const nextEditors = emptyEditors();
      this.editorDefinitions.forEach((editor) => {
        nextEditors[editor.modelKey] = formatJson(defaults[editor.payloadKey] || {});
      });
      this.editors = nextEditors;
    },
    buildRunPayload() {
      return {
        mode: this.selectedMode,
        output_dir: this.outputDir.trim() || "output",
        cea_config: this.parseEditor("cea"),
        cfd_config: this.parseEditor("cfd"),
        design_config: this.parseEditor("design"),
        hydraulic_validation_config: this.parseEditor("hydraulic"),
        nozzle_offdesign_config: this.parseEditor("nozzleOffdesign"),
        structural_config: this.parseEditor("structural"),
        testing_config: this.parseEditor("testing"),
        thermal_config: this.parseEditor("thermal"),
      };
    },
    formatMetricValue,
    isEditorVisible(key) {
      return (this.selectedModeDefinition?.editors || []).includes(key);
    },
    async loadDefaults() {
      const defaults = await requestJson("/api/default-config");
      this.defaults = defaults;
      this.applyDefaults(defaults);
    },
    async loadLatestRun() {
      const payload = await requestJson("/api/latest-run");
      this.latestRun = payload?.latest_run || null;
    },
    async loadWorkflowModes() {
      const payload = await requestJson("/api/workflow-modes");
      this.modes = payload.modes || [];
      if (!this.modes.some((mode) => mode.key === this.selectedMode) && this.modes.length) {
        this.selectedMode = this.modes[0].key;
      }
    },
    logTime(timestamp) {
      const stamp = new Date((timestamp || 0) * 1000);
      return Number.isNaN(stamp.getTime())
        ? "--:--:--"
        : stamp.toLocaleTimeString([], { hour12: false });
    },
    parseEditor(modelKey) {
      const raw = String(this.editors[modelKey] || "").trim();
      if (!raw) {
        return {};
      }
      try {
        return JSON.parse(raw);
      } catch (error) {
        const label = this.editorDefinitions.find((editor) => editor.modelKey === modelKey)?.title || modelKey;
        throw new Error(`${label} is not valid JSON: ${error.message}`);
      }
    },
    async pollStatus() {
      const snapshot = await requestJson("/api/job-status").catch(() => null);
      if (!snapshot) {
        return;
      }
      const previousStatus = this.statusSnapshot?.status || "idle";
      this.statusSnapshot = snapshot;
      this.busy = snapshot.status === "running";
      await this.$nextTick();
      this.scrollLogsToBottom();
      if (snapshot.status === "completed" && previousStatus !== "completed") {
        await this.loadLatestRun().catch(() => null);
      }
    },
    async refreshLatest() {
      try {
        await this.loadLatestRun();
      } catch (error) {
        this.statusSnapshot = {
          ...this.statusSnapshot,
          message: error.message,
          status: "error",
        };
      }
    },
    resetDefaults() {
      if (this.defaults) {
        this.applyDefaults(this.defaults);
      }
    },
    async runAllWorkflows() {
      await this.submitRun("/api/run-all");
    },
    async runWorkflow() {
      await this.submitRun("/api/run-workflow");
    },
    scrollLogsToBottom() {
      const host = this.$refs.logsCard;
      if (host) {
        host.scrollTop = host.scrollHeight;
      }
    },
    async submitRun(url) {
      let keepBusy = false;
      try {
        this.busy = true;
        const snapshot = await requestJson(url, {
          body: JSON.stringify(this.buildRunPayload()),
          method: "POST",
        });
        keepBusy = snapshot.status === "running";
        this.statusSnapshot = snapshot;
      } catch (error) {
        this.statusSnapshot = {
          ...this.statusSnapshot,
          message: error.message,
          status: "error",
        };
      } finally {
        if (!keepBusy) {
          this.busy = false;
        }
      }
    },
    latestRunAssetUrl,
  },
  async mounted() {
    try {
      await this.loadWorkflowModes();
      await this.loadDefaults();
      await this.loadLatestRun().catch(() => null);
      await this.pollStatus();
    } catch (error) {
      this.statusSnapshot = {
        ...this.statusSnapshot,
        message: error.message,
        status: "error",
      };
    }
    this.pollTimer = window.setInterval(() => {
      this.pollStatus().catch(() => null);
    }, 1200);
  },
  beforeUnmount() {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
    }
  },
}).mount("#app");
