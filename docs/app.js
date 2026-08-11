/* Results viewer: loads the exported JSON (resource/results) and renders
   summary tiles, the committee-vs-human dumbbell chart, the per-pass table
   and the run drill-down. DOM is built with element helpers, no innerHTML. */

const BASES = ["./results/", "../resource/results/"];
let base = BASES[0];

const SVG_NS = "http://www.w3.org/2000/svg";

/* ---------------------------------------------------------------- helpers */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  applyAttrs(node, attrs);
  node.append(...children.flat());
  return node;
}

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyAttrs(node, attrs);
  node.append(...children.flat());
  return node;
}

function applyAttrs(node, attrs) {
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.setAttribute("class", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
}

function headerRow(...labels) {
  return el("tr", {}, labels.map(([text, numeric]) =>
    el("th", numeric ? { class: "num" } : {}, text)));
}

function cell(text, numeric = false) {
  return el("td", numeric ? { class: "num" } : {}, String(text));
}

const fmt = (n) => n.toLocaleString("en-US");

async function load(name) {
  for (const candidate of [base, ...BASES]) {
    try {
      const response = await fetch(candidate + name);
      if (response.ok) {
        base = candidate;
        return await response.json();
      }
    } catch { /* try the next base */ }
  }
  throw new Error("cannot load " + name);
}

/* ------------------------------------------------------------- pass names */

function passOf(description) {
  if (description.startsWith("Q1")) return "P1 — v2 (GPT-4o)";
  if (description.startsWith("Q2")) return "P2a — v3 (GPT-4o)";
  if (description.startsWith("Q3")) return "P2b — v3+cal (GPT-4o)";
  if (description.startsWith("Q4")) return "P4 — calib. DeepSeek";
  if (description.startsWith("Effetto modello gpt-5")) return "P3 — GPT-5";
  if (description.startsWith("Effetto modello sonnet")) return "P3 — Sonnet 4.5";
  if (description.startsWith("Effetto modello deepsearch")) return "P3 — DeepSeek V3";
  return "Replica cycle (factorial 3×3)";
}

/* ---------------------------------------------------------------- tooltip */

const tip = document.getElementById("tip");

function showTip(event, lines) {
  tip.replaceChildren(...lines.map(([cls, text]) => el("div", cls ? { class: cls } : {}, text)));
  tip.style.display = "block";
  tip.style.left = `${event.clientX + 14}px`;
  tip.style.top = `${event.clientY - 10}px`;
}

const hideTip = () => { tip.style.display = "none"; };

/* ------------------------------------------------------------------ main */

async function main() {
  const [manifest, runs, agents, papersDoc, openReview] = await Promise.all(
    ["manifest.json", "runs.json", "agents.json", "papers.json", "open_review.json"].map(load));

  const papers = papersDoc.papers;
  const paperById = new Map(papers.map((p) => [p.paper_id, p]));

  const agentsByRun = new Map();
  for (const agent of agents) {
    if (!agentsByRun.has(agent.run_id)) agentsByRun.set(agent.run_id, []);
    agentsByRun.get(agent.run_id).push(agent);
  }

  const humanMean = new Map();
  for (const paper of papers) {
    const ratings = openReview
      .filter((r) => r.paper_id === paper.paper_id && r.rating != null)
      .map((r) => r.rating);
    if (ratings.length) humanMean.set(paper.paper_id, ratings.reduce((a, b) => a + b) / ratings.length);
  }

  renderManifest(manifest);
  renderTiles(manifest, agents, papers);
  setupChart(runs, agentsByRun, paperById, humanMean);
  renderPasses(runs, agentsByRun);
  renderRuns(runs, agentsByRun);
}

/* -------------------------------------------------------- static sections */

function renderManifest(manifest) {
  const day = new Date(manifest.exported_at).toISOString().slice(0, 10);
  const c = manifest.counts;
  document.getElementById("manifest-line").textContent =
    `Export of ${day} — ${c.runs} runs · ${c.agent_invocations} agent invocations · ` +
    `${c.human_reviews} human review records · ${c.trace_bundles} verbatim trace bundles`;
  document.getElementById("exclusions").textContent =
    "Deliberate exclusions: " + manifest.exclusions.join("; ") + ".";
}

function renderTiles(manifest, agents, papers) {
  const tokensIn = agents.reduce((sum, a) => sum + (a.input_tokens || 0), 0);
  const tokensOut = agents.reduce((sum, a) => sum + (a.output_tokens || 0), 0);
  const tiles = [
    [manifest.counts.runs, "graph runs"],
    [manifest.counts.agent_invocations, "LLM invocations"],
    [`${(tokensIn / 1e6).toFixed(2)} M`, "tokens in"],
    [`${(tokensOut / 1e3).toFixed(0)} k`, "tokens out"],
    [papers.length, "papers (ICLR 2026)"],
    [manifest.counts.human_reviews, "human review records"],
  ];
  document.getElementById("tiles").replaceChildren(
    ...tiles.map(([value, label]) =>
      el("div", { class: "tile" }, el("b", {}, String(value)), el("span", {}, label))));
}

/* ------------------------------------------------------------------ chart */

function setupChart(runs, agentsByRun, paperById, humanMean) {
  const groups = [...new Set(runs.map((r) => passOf(r.description || "")))];
  const select = document.getElementById("pass");
  select.replaceChildren(...groups.map((g) =>
    el("option", g.includes("Sonnet") ? { selected: "" } : {}, g)));
  select.addEventListener("change", draw);
  draw();

  function chartRows(group) {
    const rows = [];
    for (const run of runs) {
      if (passOf(run.description || "") !== group) continue;
      const reviewers = (agentsByRun.get(run.run_id) || [])
        .filter((a) => a.agent_role === "reviewer" && a.rating != null);
      if (!reviewers.length || !humanMean.has(run.paper_id)) continue;
      const paper = paperById.get(run.paper_id);
      rows.push({
        name: paper ? paper.paper_name : run.paper_id,
        forum: paper?.open_review_id || "",
        decision: paper?.human_decision || "",
        human: humanMean.get(run.paper_id),
        artificial: reviewers.reduce((sum, a) => sum + a.rating, 0) / reviewers.length,
      });
    }
    return rows.sort((a, b) => a.human - b.human);
  }

  function draw() {
    const rows = chartRows(select.value);
    const width = 980, rowHeight = 34, padLeft = 320, padRight = 60, padTop = 26, padBottom = 8;
    const height = padTop + rows.length * rowHeight + padBottom;
    const x = (value) => padLeft + (value / 10) * (width - padLeft - padRight);

    const root = svg("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": "Mean rating, artificial vs human, per paper",
    });

    for (let value = 0; value <= 10; value += 2) {
      root.append(
        svg("line", { x1: x(value), y1: padTop - 8, x2: x(value), y2: height - padBottom,
                      stroke: "var(--grid)", "stroke-width": 1 }),
        svg("text", { x: x(value), y: padTop - 12, "text-anchor": "middle", fill: "var(--muted)" },
            String(value)));
    }

    rows.forEach((row, index) => {
      const y = padTop + index * rowHeight + rowHeight / 2;
      const label = row.name.length > 44 ? row.name.slice(0, 42) + "…" : row.name;
      const dot = (series, value, color) =>
        svg("circle", {
          cx: x(value), cy: y, r: 6, fill: color,
          stroke: "var(--surface)", "stroke-width": 2,
          onmousemove: (event) => showTip(event, [
            ["tip-title", row.name],
            ["", `${series} mean rating: ${value.toFixed(2)}`],
            ["tip-meta", `${row.decision} · ${row.forum}`],
          ]),
          onmouseleave: hideTip,
        });
      root.append(
        svg("text", { x: padLeft - 12, y: y + 4, "text-anchor": "end", fill: "var(--ink-2)" }, label),
        svg("line", { x1: x(Math.min(row.human, row.artificial)), y1: y,
                      x2: x(Math.max(row.human, row.artificial)), y2: y,
                      stroke: "var(--axis)", "stroke-width": 2 }),
        dot("human", row.human, "var(--s2)"),
        dot("artificial", row.artificial, "var(--s1)"),
        svg("text", { x: x(Math.max(row.human, row.artificial)) + 12, y: y + 4,
                      fill: "var(--ink-2)" },
            `${row.artificial.toFixed(1)} vs ${row.human.toFixed(1)}`));
    });

    document.getElementById("chart").replaceChildren(root);
    renderChartTable(rows);
  }

  function renderChartTable(rows) {
    const table = el("table", {},
      headerRow(["Paper"], ["Outcome"], ["Human", true], ["Artificial", true], ["Δ", true]),
      rows.map((row) => {
        const delta = row.artificial - row.human;
        return el("tr", {},
          cell(row.name), cell(row.decision),
          cell(row.human.toFixed(2), true), cell(row.artificial.toFixed(2), true),
          cell(`${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`, true));
      }));
    document.getElementById("chart-table").replaceChildren(table);
  }
}

/* ----------------------------------------------------------------- passes */

function renderPasses(runs, agentsByRun) {
  const byGroup = new Map();
  for (const run of runs) {
    const group = passOf(run.description || "");
    if (!byGroup.has(group)) byGroup.set(group, []);
    byGroup.get(group).push(run);
  }

  const rows = [...byGroup.entries()].map(([group, groupRuns]) => {
    const invocations = groupRuns.flatMap((run) => agentsByRun.get(run.run_id) || []);
    const rejects = groupRuns.filter((run) => run.decision === "reject").length;
    return el("tr", {},
      cell(group),
      cell(groupRuns.length, true),
      cell(invocations.length, true),
      cell(fmt(invocations.reduce((sum, a) => sum + (a.input_tokens || 0), 0)), true),
      cell(fmt(invocations.reduce((sum, a) => sum + (a.output_tokens || 0), 0)), true),
      cell(`${rejects}/${groupRuns.length}`, true));
  });

  document.getElementById("passes").replaceChildren(
    headerRow(["Pass"], ["Runs", true], ["Invocations", true],
              ["Tokens in", true], ["Tokens out", true], ["Rejects", true]),
    ...rows);
}

/* ------------------------------------------------------------------- runs */

function renderRuns(runs, agentsByRun) {
  const rows = runs.map((run) => {
    const invocations = agentsByRun.get(run.run_id) || [];
    const totalTokens = invocations.reduce((sum, a) => sum + (a.total_tokens || 0), 0);
    const pillClass =
      run.decision === "reject" ? "pill reject" :
      run.decision === "accept" ? "pill accept" : "pill";
    return el("tr", {
      class: "click",
      onclick: () => renderDetail(run, invocations),
    },
      cell((run.timestamp || "").slice(0, 16).replace("T", " ")),
      cell(run.description || run.run_id),
      el("td", {}, el("span", { class: pillClass }, run.decision || "—")),
      cell(run.meta_overall_score ?? "—", true),
      cell(run.total_rounds, true),
      cell(fmt(totalTokens), true));
  });

  document.getElementById("runs").replaceChildren(
    headerRow(["When"], ["Run"], ["Decision"], ["Meta", true], ["Rounds", true], ["Tokens", true]),
    ...rows);
}

async function renderDetail(run, invocations) {
  const traceUrl = base + "traces/" + run.run_id.replaceAll(":", "_") + ".json";
  const detail = document.getElementById("detail");
  detail.replaceChildren(
    el("h2", {}, run.description || run.run_id),
    el("p", { class: "meta" }, "loading trace bundle…"));
  detail.scrollIntoView({ behavior: "smooth", block: "nearest" });

  let traces = [];
  try {
    traces = (await (await fetch(traceUrl)).json()).traces || [];
  } catch { /* bundle missing: the table still renders, without trace columns */ }

  const COLUMNS = 10;
  const rows = invocations.flatMap((a) => {
    const trace = a.trace_index != null ? traces[a.trace_index] : undefined;
    const toolCalls = trace?.tool_trace || [];
    const contextChars = trace?.context_chars || 0;
    const isBlindReview =
      a.agent_role === "reviewer" && trace && contextChars === 0 && toolCalls.length === 0;

    const agentCell = el("td", {},
      `${a.agent_role}${a.agent_index ? " " + a.agent_index : ""}`,
      ...(isBlindReview ? [" ", el("span", { class: "pill reject" }, "blind")] : []));

    const row = el("tr", {},
      cell(a.round, true),
      agentCell,
      cell(a.model || "—"),
      cell(a.rating ?? (a.overall_score != null ? `meta ${a.overall_score}` : (a.decision || "—")), true),
      cell(a.confidence ?? "—", true),
      cell(a.soundness != null ? `${a.soundness}·${a.presentation}·${a.contribution}` : "—", true),
      cell(trace ? fmt(contextChars) : "—", true),
      cell(trace ? String(toolCalls.length) : "—", true),
      cell(fmt(a.total_tokens || 0), true),
      cell(a.latency_seconds ? Number(a.latency_seconds).toFixed(1) : "—", true));

    if (!toolCalls.length) return [row];
    return [row, toolCallsRow(a, toolCalls, COLUMNS)];
  });

  detail.replaceChildren(
    el("h2", {}, run.description || run.run_id),
    el("p", { class: "meta" },
      `max_rounds=${run.graph_config?.max_rounds ?? "—"} · `,
      el("a", { href: traceUrl }, "verbatim trace bundle (JSON)")),
    el("table", {},
      headerRow(["Round", true], ["Agent"], ["Model"], ["Rating", true], ["Conf.", true],
                ["S·P·C", true], ["Ctx chars", true], ["Tool calls", true],
                ["Tokens", true], ["Lat. s", true]),
      ...rows));
}

function toolCallsRow(agent, toolCalls, columns) {
  const label = `${agent.agent_role}${agent.agent_index ? " " + agent.agent_index : ""}`;
  const items = toolCalls.map((call, index) => {
    const args = Object.values(call.arguments || {}).join(", ");
    return el("li", {},
      el("code", {}, `${call.tool_name}(${JSON.stringify(args)})`),
      el("div", { class: "tool-result" }, call.result || "(empty result)"));
  });
  return el("tr", { class: "tool-row" },
    el("td", { colspan: String(columns) },
      el("details", {},
        el("summary", {}, `${toolCalls.length} search call${toolCalls.length === 1 ? "" : "s"} by ${label} — queries and result previews`),
        el("ol", { class: "tool-list" }, items))));
}

main().catch((error) => {
  document.getElementById("manifest-line").textContent = "failed to load results: " + error.message;
});
