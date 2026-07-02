from __future__ import annotations


def render_enterprise_console() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Semantic Data Portal</title>
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
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }
    main {
      width: min(1480px, 100%);
      margin: 0 auto;
      padding: 20px 24px 28px;
    }
    .status-line {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: var(--muted);
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
      min-height: 86px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-strong);
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
    .footer {
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 980px) {
      header { align-items: flex-start; flex-direction: column; }
      main { padding: 14px; }
      .grid, .metrics, .flow { grid-template-columns: 1fr; }
      td:last-child, th:last-child { text-align: left; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Semantic Data Portal</h1>
    <div class="status-line">
      <span class="badge ok" id="readyBadge">pilot evidence</span>
      <span class="badge">valuation target KRW 2B</span>
      <span class="badge warn">Figma Code Connect disabled</span>
    </div>
  </header>
  <main>
    <div class="grid">
      <div class="stack">
        <section aria-labelledby="metricsTitle">
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
        <section aria-labelledby="flowTitle">
          <h2 id="flowTitle">Pilot Flow</h2>
          <div class="flow">
            <div class="node"><strong>Readiness</strong><code>/enterprise/readiness</code></div>
            <div class="node"><strong>Evidence</strong><code>/enterprise/evidence-pack</code></div>
            <div class="node"><strong>Steward</strong><code>/enterprise/steward-review</code></div>
            <div class="node"><strong>Query</strong><code>/browse/query</code></div>
            <div class="node"><strong>Connector</strong><code>/enterprise/connectors/sql_connector/probe</code></div>
          </div>
        </section>
        <section aria-labelledby="controlsTitle">
          <h2 id="controlsTitle">Controls</h2>
          <table>
            <thead><tr><th>Control</th><th>Status</th></tr></thead>
            <tbody id="controlsRows"><tr><td>Loading</td><td>--</td></tr></tbody>
          </table>
        </section>
      </div>
      <div class="stack">
        <section aria-labelledby="connectorsTitle">
          <h2 id="connectorsTitle">Connectors</h2>
          <table>
            <thead><tr><th>Path</th><th>Status</th></tr></thead>
            <tbody id="connectorRows">
              <tr><td class="mono">/enterprise/connectors/sql_connector/probe</td><td>--</td></tr>
            </tbody>
          </table>
        </section>
        <section aria-labelledby="kpiTitle">
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
        `<tr><td>${item.label}</td><td><span class="badge ${item.status === 'implemented' ? 'ok' : 'warn'}">${item.status}</span></td></tr>`
      ).join('');
    }

    async function loadKpis() {
      const kpis = await json('/enterprise/kpis');
      document.getElementById('kpiRows').innerHTML = [...kpis.primary_kpis, ...kpis.guardrail_kpis].map((item) =>
        `<tr><td>${item.label}</td><td>${item.target}</td></tr>`
      ).join('');
    }

    async function loadConnectors() {
      const rows = await Promise.all([
        ['sql_connector', 'crm-customer-master'],
        ['rdf_connector', 'semantic-glossary'],
        ['file_lake_connector', 'crm-event'],
        ['rest_connector', 'marketing-campaign'],
      ].map(async ([connector, dataset]) => {
        const path = `/enterprise/connectors/${connector}/probe?dataset_id=${dataset}`;
        const probe = await json(path);
        return `<tr><td class="mono">${path}</td><td><span class="badge ${probe.status === 'ready_for_demo' ? 'ok' : 'warn'}">${probe.status}</span></td></tr>`;
      }));
      document.getElementById('connectorRows').innerHTML = rows.join('');
    }

    Promise.all([loadEvidence(), loadControls(), loadKpis(), loadConnectors()])
      .then(() => text('readyBadge', 'ready for pilot review'))
      .catch(() => text('readyBadge', 'evidence load failed'));
  </script>
</body>
</html>"""
