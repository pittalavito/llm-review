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
  if (description.startsWith("Compare persona e model")) return "Replica cycle (factorial 3×3)";
  if (description.startsWith("Tesi ")) return "Thesis self-review";
  return "Other";
}

/* ------------------------------------------------------------------ theme */

const themeButtons = {
  light: document.getElementById("theme-light"),
  dark: document.getElementById("theme-dark"),
};

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function markTheme() {
  const active = currentTheme();
  for (const [name, button] of Object.entries(themeButtons))
    button.classList.toggle("active", name === active);
}

function setTheme(name) {
  document.documentElement.dataset.theme = name;
  localStorage.setItem("viewer-theme", name);
  markTheme();
}

const savedTheme = localStorage.getItem("viewer-theme");
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
themeButtons.light.addEventListener("click", () => setTheme("light"));
themeButtons.dark.addEventListener("click", () => setTheme("dark"));
markTheme();

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
    [papers.length, "papers (10 ICLR 2026 + thesis)"],
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
        dot("human", row.human, "var(--human)"),
        dot("artificial", row.artificial, "var(--accent)"),
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

  document.getElementById("passes-table").replaceChildren(
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
      run.decision === "accept" ? "pill accept" :
      run.decision === "minor_revision" ? "pill minor" : "pill";
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

  document.getElementById("runs-table").replaceChildren(
    headerRow(["When"], ["Run"], ["Decision"], ["Meta", true], ["Rounds", true], ["Tokens", true]),
    ...rows);
}

/* ------------------------------------------------- run detail (flow view) */

const ROLE_ICON = {
  reviewer: "🔬",
  meta_reviewer: "📋",
  area_chair: "🪑",
  author_agent: "✍️",
};

/* Scalars shown as chips; every other payload key is rendered as a field. */
const SCORE_KEYS = ["rating", "confidence", "soundness", "presentation",
                    "contribution", "overall_score", "decision", "recommendation"];

const roleName = (agent) => {
  const base = (agent.agent_role || "").replace(/_/g, " ");
  const label = base.charAt(0).toUpperCase() + base.slice(1);
  return agent.agent_index ? `${label} ${agent.agent_index}` : label;
};

const fieldLabel = (key) => key.replace(/_/g, " ").toUpperCase();

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
  } catch { /* bundle missing: the flow still renders, without verbatim panels */ }

  const rounds = new Map();
  for (const agent of invocations) {
    const round = agent.round ?? 0;
    if (!rounds.has(round)) rounds.set(round, []);
    rounds.get(round).push(agent);
  }

  const flow = [...rounds.entries()]
    .sort((a, b) => a[0] - b[0])
    .flatMap(([round, agents]) => [
      el("h3", { class: "round-head" }, `Round ${round + 1}`),
      ...agents.map((agent) =>
        agentCard(agent, agent.trace_index != null ? traces[agent.trace_index] : undefined)),
    ]);

  detail.replaceChildren(
    el("h2", {}, run.description || run.run_id),
    el("p", { class: "meta" },
      `${(run.timestamp || "").slice(0, 16).replace("T", " ")} · max_rounds=${run.graph_config?.max_rounds ?? "—"} · `,
      el("a", { href: traceUrl }, "verbatim trace bundle (JSON)")),
    runTiles(run, invocations),
    el("h3", { class: "flow-head" }, "Flusso completo round per round"),
    ...flow);
}

function runTiles(run, invocations) {
  const reviewers = invocations.filter((a) => a.agent_role === "reviewer" && a.rating != null);
  const meanRating = reviewers.length
    ? (reviewers.reduce((sum, a) => sum + a.rating, 0) / reviewers.length).toFixed(1)
    : "—";
  const tokens = invocations.reduce((sum, a) => sum + (a.total_tokens || 0), 0);
  const decisionPill = el("span", {
    class: "pill " + (run.decision === "reject" ? "reject" :
                      run.decision === "accept" ? "accept" :
                      run.decision === "minor_revision" ? "minor" : ""),
  }, run.decision || "—");

  const tile = (label, value, sub) =>
    el("div", { class: "tile" },
      el("span", { class: "tile-label" }, label),
      typeof value === "string" ? el("b", {}, value) : el("b", {}, value),
      sub ? el("span", {}, sub) : "");

  return el("div", { class: "tiles run-tiles" },
    el("div", { class: "tile" },
      el("span", { class: "tile-label" }, "Decisione"),
      el("div", { class: "tile-pill" }, decisionPill)),
    tile("Meta score", String(run.meta_overall_score ?? "—"), "su 10"),
    tile("Rating medio", meanRating, `${reviewers.length} reviewer`),
    tile("Round", String(run.total_rounds ?? "—")),
    tile("Token totali", tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens)));
}

function agentCard(agent, trace) {
  const payload = agent.response_payload || {};
  const toolCalls = trace?.tool_trace || [];
  const contextChars = trace?.context_chars || 0;
  const isBlind = agent.agent_role === "reviewer" && trace && !contextChars && !toolCalls.length;

  const headline = [];
  if (agent.rating != null) headline.push(`rating ${agent.rating}`);
  if (agent.overall_score != null) headline.push(`meta ${agent.overall_score}`);
  if (agent.confidence != null) headline.push(`conf. ${agent.confidence}`);
  if (agent.soundness != null)
    headline.push(`${agent.soundness}·${agent.presentation}·${agent.contribution}`);
  if (agent.decision) headline.push(agent.decision);

  const head = el("summary", { class: "agent-head" },
    el("span", { class: "agent-name" },
      `${ROLE_ICON[agent.agent_role] || "•"} ${roleName(agent)}`,
      ...(isBlind ? [" ", el("span", { class: "pill reject" }, "blind")] : [])),
    el("span", { class: "agent-model" }, agent.model || "—"),
    el("span", { class: "agent-headline" }, headline.join(" · ")),
    el("span", { class: "agent-tokens" },
      `${fmt(agent.total_tokens || 0)} tok · ${agent.latency_seconds ? Number(agent.latency_seconds).toFixed(1) : "—"}s`));

  return el("details", { class: "agent-card" }, head,
    el("div", { class: "agent-body" },
      scoreChips(payload),
      ...payloadFields(payload),
      ...(toolCalls.length ? [toolPanel(toolCalls)] : []),
      techPanel(agent, trace)));
}

function scoreChips(payload) {
  const chips = SCORE_KEYS
    .filter((key) => payload[key] != null && payload[key] !== "")
    .map((key) => el("span", { class: "chip" }, `${key.replace(/_/g, " ")} ${payload[key]}`));
  if (!chips.length) return "";
  return el("div", { class: "field" },
    el("div", { class: "field-label" }, "PUNTEGGI"),
    el("div", { class: "chips" }, chips));
}

function payloadFields(payload) {
  return Object.entries(payload)
    .filter(([key, value]) =>
      !SCORE_KEYS.includes(key) && value != null && value !== "" &&
      !(Array.isArray(value) && !value.length))
    .map(([key, value]) => el("div", { class: "field" },
      el("div", { class: "field-label" }, fieldLabel(key)),
      renderValue(value)));
}

function renderValue(value) {
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item !== "object" || item === null))
      return el("ul", { class: "field-list" }, value.map((item) => el("li", {}, String(item))));
    return el("div", {}, value.map((item) =>
      el("details", { class: "sub-item" },
        el("summary", {}, String(item.section_name ?? item.title ?? item.reviewer ?? "elemento")),
        el("div", { class: "field-text" },
          String(item.content ?? item.text ?? item.response ?? JSON.stringify(item, null, 1))))));
  }
  if (typeof value === "object")
    return el("pre", { class: "verbatim" }, JSON.stringify(value, null, 1));
  return el("div", { class: "field-text" }, String(value));
}

function toolPanel(toolCalls) {
  const items = toolCalls.map((call) => el("li", {},
    el("code", {}, `${call.tool_name}(${JSON.stringify(Object.values(call.arguments || {}).join(", "))})`),
    el("div", { class: "tool-result" }, call.result || "(empty result)")));
  return el("details", { class: "tech" },
    el("summary", {}, `▸ ${toolCalls.length} CHIAMATE ALLO STRUMENTO DI RICERCA`),
    el("ol", { class: "tool-list" }, items));
}

function techPanel(agent, trace) {
  const tokenLine = `token: input ${fmt(agent.input_tokens || 0)} · output ${fmt(agent.output_tokens || 0)} · ` +
    `totale ${fmt(agent.total_tokens || 0)}` +
    (agent.latency_seconds ? ` · ${Number(agent.latency_seconds).toFixed(1)}s` : "");

  const blocks = [el("div", { class: "token-line" }, tokenLine)];
  if (trace) {
    if (trace.system_prompt)
      blocks.push(el("div", { class: "field-label" }, "SYSTEM PROMPT"),
                  el("pre", { class: "verbatim tall" }, trace.system_prompt));
    if (trace.input_message)
      blocks.push(el("div", { class: "field-label" }, "INPUT MESSAGE"),
                  el("pre", { class: "verbatim" }, trace.input_message));
    blocks.push(el("div", { class: "field-label" }, "CONTEXT"),
      el("div", { class: "context-note" },
        trace.context_chars
          ? `${fmt(trace.context_chars)} caratteri di contesto documentale` +
            (trace.context_hash ? ` (SHA-256 ${trace.context_hash.slice(0, 12)}…)` : "") +
            " — il testo integrale non è incluso in questo export pubblico: gli articoli sono su OpenReview, la tesi in resource/thesis."
          : "nessun contesto iniziale fornito a questo agente."));
  } else {
    blocks.push(el("div", { class: "context-note" }, "traccia verbatim non disponibile per questa invocazione."));
  }

  return el("details", { class: "tech" },
    el("summary", {}, "▸ DETTAGLI TECNICI"),
    el("div", { class: "tech-body" }, blocks));
}

main().catch((error) => {
  document.getElementById("manifest-line").textContent = "failed to load results: " + error.message;
});
