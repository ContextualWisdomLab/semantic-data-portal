from __future__ import annotations


def render_enterprise_console() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enterprise Data Trust Console | Semantic Data Portal</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #5b6778;
      --line: #d8dee8;
      --panel: #f7f9fc;
      --panel-strong: #eef3f8;
      --accent: #0f766e;
      --warn: #a16207;
      --ok: #166534;
      --surface: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: #eef2f6;
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      background: var(--surface);
      border-bottom: 1px solid var(--line);
    }
    .brand {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    .eyebrow {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      letter-spacing: 0;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      max-width: 720px;
      color: var(--muted);
      font-size: 13px;
    }
    main {
      width: min(1480px, 100%);
      margin: 0 auto;
      padding: 20px 24px 28px;
    }
    .header-tools {
      display: grid;
      gap: 10px;
      justify-items: end;
    }
    .status-line {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: var(--muted);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .action {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 4px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--ink);
      font-size: 12px;
      font-weight: 650;
      text-decoration: none;
      white-space: nowrap;
    }
    .action:hover, .action:focus-visible {
      border-color: var(--accent);
      outline: none;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 2px 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--ink);
      font-size: 12px;
      white-space: nowrap;
    }
    .badge.ok { color: var(--ok); border-color: #bbd7c0; background: #eff8f0; }
    .badge.warn { color: var(--warn); border-color: #e7cf96; background: #fff8e7; }
    .grid {
      display: grid;
      gap: 14px;
      grid-template-columns: 1.15fr 0.85fr;
      align-items: start;
    }
    .stack { display: grid; gap: 14px; }
    section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .metrics {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .metric {
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .metric .value {
      margin-top: 6px;
      font-size: 22px;
      font-weight: 750;
      letter-spacing: 0;
    }
    .bar {
      height: 8px;
      margin-top: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: #dce5ee;
    }
    .bar > span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--accent);
    }
    .flow {
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }
    .node {
      display: block;
      min-height: 86px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-strong);
      color: inherit;
      text-decoration: none;
    }
    .node:hover, .node:focus-visible {
      border-color: var(--accent);
      outline: none;
    }
    .node strong {
      display: block;
      margin-bottom: 6px;
      font-size: 13px;
    }
    .node code {
      color: var(--muted);
      font-size: 11px;
      white-space: normal;
      overflow-wrap: anywhere;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    td:last-child, th:last-child { text-align: right; }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .endpoint-link {
      display: grid;
      gap: 3px;
      color: inherit;
      text-decoration: none;
    }
    .endpoint-link:hover strong, .endpoint-link:focus-visible strong {
      color: var(--accent);
    }
    .endpoint-link:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    .endpoint-link code {
      color: var(--muted);
      font-size: 11px;
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .footer {
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 980px) {
      header { align-items: flex-start; flex-direction: column; }
      .header-tools { justify-items: start; width: 100%; }
      .actions { justify-content: flex-start; }
      main { padding: 14px; }
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
