from __future__ import annotations

from .design_tokens import root_css_variables


_CONSOLE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enterprise Data Trust Console | Semantic Data Portal</title>
  <style>
    __SDP_ROOT_TOKENS__
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--sdp-color-text-primary);
      background: var(--sdp-color-background-canvas);
      font: var(--sdp-font-size-14)/var(--sdp-line-height-normal) system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--sdp-space-16);
      padding: var(--sdp-space-18) var(--sdp-space-24);
      background: var(--sdp-color-surface-default);
      border-bottom: 1px solid var(--sdp-color-border-default);
    }
    .brand {
      display: grid;
      gap: var(--sdp-space-4);
      min-width: 0;
    }
    .eyebrow {
      margin: 0;
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-12);
      font-weight: var(--sdp-font-weight-medium);
      letter-spacing: 0;
    }
    h1 {
      margin: 0;
      font-size: var(--sdp-font-size-24);
      font-weight: var(--sdp-font-weight-bold);
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      max-width: 720px;
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-13);
    }
    main {
      width: min(1480px, 100%);
      margin: 0 auto;
      padding: var(--sdp-space-20) var(--sdp-space-24) var(--sdp-space-28);
    }
    .header-tools {
      display: grid;
      gap: var(--sdp-space-10);
      justify-items: end;
    }
    .status-line {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sdp-space-8);
      align-items: center;
      color: var(--sdp-color-text-muted);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sdp-space-8);
      justify-content: flex-end;
    }
    .action {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: var(--sdp-space-4) var(--sdp-space-10);
      border: 1px solid var(--sdp-color-border-default);
      border-radius: var(--sdp-radius-control);
      background: var(--sdp-color-surface-default);
      color: var(--sdp-color-text-primary);
      font-size: var(--sdp-font-size-12);
      font-weight: var(--sdp-font-weight-medium);
      text-decoration: none;
      white-space: nowrap;
    }
    .action:hover, .action:focus-visible {
      border-color: var(--sdp-color-interaction-primary);
      outline: none;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: var(--sdp-space-2) var(--sdp-space-9);
      border: 1px solid var(--sdp-color-border-default);
      border-radius: var(--sdp-radius-control);
      background: var(--sdp-color-surface-muted);
      color: var(--sdp-color-text-primary);
      font-size: var(--sdp-font-size-12);
      white-space: nowrap;
    }
    .badge.ok { color: var(--sdp-badge-success-fg); border-color: var(--sdp-badge-success-border); background: var(--sdp-badge-success-bg); }
    .badge.warn { color: var(--sdp-badge-warning-fg); border-color: var(--sdp-badge-warning-border); background: var(--sdp-badge-warning-bg); }
    .grid {
      display: grid;
      gap: var(--sdp-space-14);
      grid-template-columns: 1.15fr 0.85fr;
      align-items: start;
    }
    .stack { display: grid; gap: var(--sdp-space-14); }
    section {
      background: var(--sdp-color-surface-default);
      border: 1px solid var(--sdp-color-border-default);
      border-radius: var(--sdp-radius-surface);
      padding: var(--sdp-space-16);
    }
    h2 {
      margin: 0 0 var(--sdp-space-12);
      font-size: var(--sdp-font-size-15);
      font-weight: var(--sdp-font-weight-bold);
      letter-spacing: 0;
    }
    .metrics {
      display: grid;
      gap: var(--sdp-space-10);
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .metric {
      min-width: 0;
      padding: var(--sdp-space-12);
      border: 1px solid var(--sdp-color-border-default);
      border-radius: var(--sdp-radius-surface);
      background: var(--sdp-color-surface-muted);
    }
    .metric .label {
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-12);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .metric .value {
      margin-top: var(--sdp-space-6);
      font-size: var(--sdp-font-size-22);
      font-weight: var(--sdp-font-weight-heavy);
      letter-spacing: 0;
    }
    .bar {
      height: 8px;
      margin-top: var(--sdp-space-8);
      overflow: hidden;
      border-radius: var(--sdp-radius-pill);
      background: var(--sdp-color-border-muted);
    }
    .bar > span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--sdp-color-interaction-primary);
    }
    .flow {
      display: grid;
      gap: var(--sdp-space-8);
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }
    .node {
      display: block;
      min-height: 86px;
      padding: var(--sdp-space-12);
      border: 1px solid var(--sdp-color-border-default);
      border-radius: var(--sdp-radius-surface);
      background: var(--sdp-color-surface-strong);
      color: inherit;
      text-decoration: none;
    }
    .node:hover, .node:focus-visible {
      border-color: var(--sdp-color-interaction-primary);
      outline: none;
    }
    .node strong {
      display: block;
      margin-bottom: var(--sdp-space-6);
      font-size: var(--sdp-font-size-13);
    }
    .node code {
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-11);
      white-space: normal;
      overflow-wrap: anywhere;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      padding: var(--sdp-space-9) var(--sdp-space-8);
      border-bottom: 1px solid var(--sdp-color-border-default);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-12);
      font-weight: var(--sdp-font-weight-medium);
    }
    td:last-child, th:last-child { text-align: right; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: var(--sdp-font-size-12);
    }
    .endpoint-link {
      display: grid;
      gap: var(--sdp-space-3);
      color: inherit;
      text-decoration: none;
    }
    .endpoint-link:hover strong, .endpoint-link:focus-visible strong {
      color: var(--sdp-color-interaction-primary);
    }
    .endpoint-link:focus-visible {
      outline: 2px solid var(--sdp-color-interaction-primary);
      outline-offset: 2px;
    }
    .endpoint-link code {
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-11);
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .footer {
      margin-top: var(--sdp-space-14);
      color: var(--sdp-color-text-muted);
      font-size: var(--sdp-font-size-12);
    }
    @media (max-width: 980px) {
      header { align-items: flex-start; flex-direction: column; }
      .header-tools { justify-items: start; width: 100%; }
      .actions { justify-content: flex-start; }
      main { padding: var(--sdp-space-14); }
      .grid, .metrics, .flow { grid-template-columns: 1fr; }
      td:last-child, th:last-child { text-align: left; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <p class="eyebrow">Semantic Data Portal</p>
      <h1>Enterprise Data Trust Console</h1>
      <p class="subtitle">Buyer pilot evidence surface for KRW 2B enterprise readiness.</p>
    </div>
    <div class="header-tools">
      <div class="status-line">
        <span class="badge ok" id="readyBadge">pilot evidence</span>
        <span class="badge">KRW 2B enterprise readiness</span>
        <span class="badge warn">Figma Code Connect disabled</span>
      </div>
      <nav class="actions" aria-label="Console evidence links">
        <a class="action" href="/enterprise/readiness">Readiness</a>
        <a class="action" href="/enterprise/evidence-pack">Evidence</a>
        <a class="action" href="/enterprise/production-readiness">Production</a>
        <a class="action" href="/enterprise/demo-plan">Demo Plan</a>
        <a class="action" href="/docs">API Docs</a>
      </nav>
    </div>
  </header>
  <main>
    <div class="grid">
      <div class="stack">
        <section aria-label="Evidence scorecard" aria-labelledby="metricsTitle">
          <h2 id="metricsTitle">Evidence</h2>
          <div class="metrics">
            <div class="metric">
              <div class="label">Metadata validation</div>
              <div class="value" id="metadataRate">--</div>
              <div class="bar"><span id="metadataBar"></span></div>
            </div>
            <div class="metric">
              <div class="label">SHACL validation</div>
              <div class="value" id="shaclRate">--</div>
              <div class="bar"><span id="shaclBar"></span></div>
            </div>
            <div class="metric">
              <div class="label">Ontology coverage</div>
              <div class="value" id="ontologyRate">--</div>
              <div class="bar"><span id="ontologyBar"></span></div>
            </div>
            <div class="metric">
              <div class="label">Review queue</div>
              <div class="value" id="reviewCount">--</div>
              <div class="bar"><span id="reviewBar"></span></div>
            </div>
          </div>
        </section>
        <section aria-label="Pilot workflow" aria-labelledby="flowTitle">
          <h2 id="flowTitle">Pilot Flow</h2>
          <div class="flow">
            <a class="node" href="/enterprise/readiness"><strong>Readiness</strong><code>/enterprise/readiness</code></a>
            <a class="node" href="/enterprise/evidence-pack"><strong>Evidence</strong><code>/enterprise/evidence-pack</code></a>
            <a class="node" href="/enterprise/steward-review"><strong>Steward</strong><code>/enterprise/steward-review</code></a>
            <a class="node" href="/browse/query"><strong>Query</strong><code>/browse/query</code></a>
            <a class="node" href="/enterprise/connectors/sql_connector/probe"><strong>Connector</strong><code>/enterprise/connectors/sql_connector/probe</code></a>
          </div>
        </section>
        <section aria-label="Enterprise controls" aria-labelledby="controlsTitle">
          <h2 id="controlsTitle">Controls</h2>
          <table>
            <thead><tr><th>Control</th><th>Status</th></tr></thead>
            <tbody id="controlsRows"><tr><td>Loading</td><td>--</td></tr></tbody>
          </table>
        </section>
      </div>
      <div class="stack">
        <section aria-label="Connector readiness" aria-labelledby="connectorsTitle">
          <h2 id="connectorsTitle">Connectors</h2>
          <table>
            <thead><tr><th>Connector</th><th>Dataset</th><th>Status</th></tr></thead>
            <tbody id="connectorRows">
              <tr><td>SQL connector</td><td class="mono">crm-customer-master</td><td>--</td></tr>
            </tbody>
          </table>
        </section>
        <section aria-label="KPI gate targets" aria-labelledby="kpiTitle">
          <h2 id="kpiTitle">KPI Gates</h2>
          <table>
            <thead><tr><th>Gate</th><th>Target</th></tr></thead>
            <tbody id="kpiRows"><tr><td>Loading</td><td>--</td></tr></tbody>
          </table>
        </section>
      </div>
    </div>
    <div class="footer">Figma/FigJam board: https://www.figma.com/board/UptVQaUlwbLVYv20ot4ZDm</div>
  </main>
  <script>
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[char]);
    const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
    const width = (id, value) => document.getElementById(id).style.width = pct(value);
    const text = (id, value) => document.getElementById(id).textContent = value;

    async function json(path) {
      const response = await fetch(path);
      if (!response.ok) throw new Error(path);
      return response.json();
    }

    async function loadEvidence() {
      const evidence = await json('/enterprise/evidence-pack');
      text('metadataRate', pct(evidence.metadata_validation_pass_rate));
      text('shaclRate', pct(evidence.shacl_validation_pass_rate));
      text('ontologyRate', pct(evidence.ontology_mapping_coverage));
      text('reviewCount', evidence.steward_review_queue_count);
      width('metadataBar', evidence.metadata_validation_pass_rate);
      width('shaclBar', evidence.shacl_validation_pass_rate);
      width('ontologyBar', evidence.ontology_mapping_coverage);
      width('reviewBar', evidence.steward_review_queue_count === 0 ? 1 : 0.35);
    }

    async function loadControls() {
      const controls = await json('/enterprise/controls');
      document.getElementById('controlsRows').innerHTML = controls.controls.map((item) =>
        `<tr><td>${esc(item.label)}</td><td><span class="badge ${item.status === 'implemented' ? 'ok' : 'warn'}">${esc(item.status)}</span></td></tr>`
      ).join('');
    }

    async function loadKpis() {
      const kpis = await json('/enterprise/kpis');
      document.getElementById('kpiRows').innerHTML = [...kpis.primary_kpis, ...kpis.guardrail_kpis].map((item) =>
        `<tr><td>${esc(item.label)}</td><td>${esc(item.target)}</td></tr>`
      ).join('');
    }

    async function loadConnectors() {
      const rows = await Promise.all([
        ['SQL connector', 'sql_connector', 'crm-customer-master'],
        ['RDF connector', 'rdf_connector', 'semantic-glossary'],
        ['File lake connector', 'file_lake_connector', 'crm-event'],
        ['REST connector', 'rest_connector', 'marketing-campaign'],
      ].map(async ([label, connector, dataset]) => {
        const path = `/enterprise/connectors/${connector}/probe?dataset_id=${dataset}`;
        const probe = await json(path);
        return `<tr><td><a class="endpoint-link" href="${esc(path)}" aria-label="${esc(label)} probe endpoint for ${esc(dataset)}"><strong>${esc(label)}</strong></a></td><td class="mono">${esc(dataset)}</td><td><span class="badge ${probe.status === 'ready_for_demo' ? 'ok' : 'warn'}">${esc(probe.status)}</span></td></tr>`;
      }));
      document.getElementById('connectorRows').innerHTML = rows.join('');
    }

    Promise.all([loadEvidence(), loadControls(), loadKpis(), loadConnectors()])
      .then(() => text('readyBadge', 'ready for pilot review'))
      .catch(() => text('readyBadge', 'evidence load failed'));
  </script>
</body>
</html>"""


def render_enterprise_console() -> str:
    return _CONSOLE_TEMPLATE.replace("__SDP_ROOT_TOKENS__", root_css_variables())
