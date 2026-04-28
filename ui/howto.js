const { createApp } = Vue;
const { escapeHtml, requestJson } = window.WorkflowUiShared;

function groupNodesByPhase(phases, nodes) {
  return (phases || []).map((phase) => ({
    ...phase,
    nodes: (nodes || []).filter((node) => node.phase === phase.key),
  }));
}

function downstreamMap(nodes, edges) {
  const nodeIndex = new Map((nodes || []).map((node) => [node.id, node]));
  const map = new Map((nodes || []).map((node) => [node.id, []]));
  (edges || []).forEach((edge) => {
    const target = nodeIndex.get(edge.to);
    if (map.has(edge.from) && target) {
      map.get(edge.from).push({
        id: target.id,
        label: edge.label,
        title: target.title,
      });
    }
  });
  return Object.fromEntries(map.entries());
}

function measureCanvas(phases) {
  const phaseWidth = 320;
  const gutter = 40;
  const nodeHeight = 130;
  const nodeGap = 20;
  const headerHeight = 72;
  const maxNodes = Math.max(...phases.map((phase) => phase.nodes.length), 1);
  return {
    width: phases.length * phaseWidth + (phases.length - 1) * gutter,
    height: headerHeight + maxNodes * nodeHeight + Math.max(0, maxNodes - 1) * nodeGap + 28,
    phaseWidth,
    gutter,
    headerHeight,
    nodeHeight,
    nodeGap,
  };
}

function buildGraphLayout(phases) {
  const canvas = measureCanvas(phases);
  const nodeWidth = 280;
  const positions = new Map();
  phases.forEach((phase, phaseIndex) => {
    const columnX = phaseIndex * (canvas.phaseWidth + canvas.gutter);
    phase.nodes.forEach((node, nodeIndex) => {
      const x = columnX + 20;
      const y = canvas.headerHeight + nodeIndex * (canvas.nodeHeight + canvas.nodeGap);
      positions.set(node.id, {
        x,
        y,
        width: nodeWidth,
        height: canvas.nodeHeight,
        centerX: x + nodeWidth / 2,
        centerY: y + canvas.nodeHeight / 2,
      });
    });
  });
  return { canvas, positions };
}

function wrapSvgText(text, lineLength) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  words.forEach((word) => {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > lineLength && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  });
  if (current) {
    lines.push(current);
  }
  return lines.slice(0, 4);
}

function nodePreview(node) {
  const inputs = node.inputs?.length ? `${node.inputs.length} inputs` : "no inputs";
  const outputs = node.outputs?.length ? `${node.outputs.length} outputs` : "no outputs";
  return `${inputs} - ${outputs}`;
}

function edgePath(from, to) {
  const startX = from.x + from.width;
  const startY = from.centerY;
  const endX = to.x;
  const endY = to.centerY;
  const bend = Math.max(36, (endX - startX) * 0.45);
  return `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`;
}

function workflowMapMarkup(phases, nodes, edges) {
  if (!phases?.length || !nodes?.length) {
    return '<div class="empty-state">Workflow graph is not available.</div>';
  }
  const grouped = groupNodesByPhase(phases, nodes);
  const { canvas, positions } = buildGraphLayout(grouped);

  const phaseHeaders = grouped.map((phase, phaseIndex) => {
    const x = phaseIndex * (canvas.phaseWidth + canvas.gutter) + 20;
    return `
      <g>
        <rect x="${x}" y="14" width="280" height="42" rx="14" class="workflow-phase-pill"/>
        <text x="${x + 20}" y="40" class="workflow-phase-pill-text">${escapeHtml(phase.title)}</text>
      </g>
    `;
  }).join("");

  const edgeMarkup = (edges || []).map((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) {
      return "";
    }
    const labelX = (from.x + from.width + to.x) / 2;
    const labelY = (from.centerY + to.centerY) / 2 - 10;
    return `
      <g>
        <path d="${edgePath(from, to)}" class="workflow-edge">
          <title>${escapeHtml(`${edge.label}: ${edge.from} -> ${edge.to}`)}</title>
        </path>
        <rect x="${labelX - 56}" y="${labelY - 11}" width="112" height="22" rx="11" class="workflow-edge-label-bg"/>
        <text x="${labelX}" y="${labelY + 4}" text-anchor="middle" class="workflow-edge-label">${escapeHtml(edge.label)}</text>
      </g>
    `;
  }).join("");

  const nodeMarkup = (nodes || []).map((node) => {
    const box = positions.get(node.id);
    if (!box) {
      return "";
    }
    const titleLines = wrapSvgText(node.title, 24);
    const descriptionLines = wrapSvgText(nodePreview(node), 28);
    const title = titleLines.map((line, index) => `
      <text x="${box.x + 16}" y="${box.y + 30 + index * 18}" class="workflow-node-title">${escapeHtml(line)}</text>
    `).join("");
    const description = descriptionLines.map((line, index) => `
      <text x="${box.x + 16}" y="${box.y + 88 + index * 15}" class="workflow-node-meta">${escapeHtml(line)}</text>
    `).join("");
    return `
      <a href="${escapeHtml(node.detail_href || `/simulation.html?step=${node.id}`)}">
        <g>
          <rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="18" class="workflow-node workflow-node-${escapeHtml(node.kind || "workflow")}"/>
          <text x="${box.x + 16}" y="${box.y + 18}" class="workflow-node-kind">${escapeHtml((node.kind || "workflow").toUpperCase())}</text>
          ${title}
          ${description}
          <title>${escapeHtml(node.description || "")}</title>
        </g>
      </a>
    `;
  }).join("");

  return `
    <div class="workflow-map-meta">
      <div class="workflow-map-legend">
        <span class="workflow-legend-chip workflow-legend-config">Config Input</span>
        <span class="workflow-legend-chip workflow-legend-step">Program Step</span>
      </div>
      <p>The map shows high-level flow. Use the step cards below for the full input/output lists and downstream consumers.</p>
    </div>
    <div class="workflow-map-scroller">
      <svg viewBox="0 0 ${canvas.width} ${canvas.height}" class="workflow-map-svg" role="img" aria-label="Workflow input and output map">
        ${phaseHeaders}
        ${edgeMarkup}
        ${nodeMarkup}
      </svg>
    </div>
  `;
}

createApp({
  data() {
    return {
      error: "",
      payload: null,
    };
  },
  computed: {
    downstreamById() {
      return downstreamMap(this.payload?.nodes || [], this.payload?.edges || []);
    },
    phaseGroups() {
      return groupNodesByPhase(this.payload?.phases || [], this.payload?.nodes || []);
    },
    workflowMapMarkup() {
      return workflowMapMarkup(this.payload?.phases || [], this.payload?.nodes || [], this.payload?.edges || []);
    },
  },
  methods: {
    ioItemKey(item) {
      if (typeof item === "string") {
        return item;
      }
      return `${item?.name || "unknown"}-${item?.description || ""}`;
    },
  },
  async mounted() {
    try {
      this.payload = await requestJson("/api/workflow-map");
    } catch (error) {
      this.error = error.message;
    }
  },
}).mount("#app");
