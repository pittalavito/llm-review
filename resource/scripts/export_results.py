"""Export the experimental results (Postgres facts + Redis traces) to static
JSON files under resource/results/, ready to be committed and served by the
GitHub Pages viewer (docs/).

Deliberate exclusions, stated in manifest.json:
- no full paper texts: the agent-context keyspace is not exported; traces keep
  the context hash and its length only (papers are on OpenReview, forum ids
  are in papers.json);
- tool results are truncated to a short preview (enough to document what the
  agent saw without redistributing the paper in chunks);
- author emails are dropped (personal data collected from OpenReview).

Run from the repo root:  uv run python resource/scripts/export_results.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import redis

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "resource" / "results"
TOOL_RESULT_PREVIEW_CHARS = 300

TRACE_PREFIX = "llm-review:agent-trace:"
CONTEXT_PREFIX = "llm-review:agent-context:"


def load_env(path: Path) -> dict[str, str]:
    """Minimal .env parser with ${VAR} interpolation (no external deps)."""
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    resolved = {}
    for key, value in env.items():
        resolved[key] = re.sub(r"\$\{(\w+)\}", lambda m: env.get(m.group(1), ""), value)
    return resolved


def fetch_all(cur, query: str) -> list[dict]:
    cur.execute(query)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def truncate_tool_results(trace: dict) -> dict:
    tool_trace = trace.get("tool_trace")
    if tool_trace:
        for call in tool_trace:
            result = call.get("result") or ""
            if len(result) > TOOL_RESULT_PREVIEW_CHARS:
                call["result"] = result[:TOOL_RESULT_PREVIEW_CHARS] + " … [truncated for export]"
    return trace


def main() -> None:
    env = load_env(ROOT / ".env")
    db_url = env["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    r = redis.Redis.from_url(env["REDIS_URL"], decode_responses=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "traces").mkdir(exist_ok=True)

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        runs = fetch_all(cur, "SELECT * FROM graph_review ORDER BY timestamp")
        agents = fetch_all(cur, "SELECT * FROM graph_review_agent ORDER BY id")
        papers = fetch_all(cur, """
            SELECT p.id, p.paper_id, p.paper_name, p.paper_type, p.description,
                   p.conference, p.open_review_id, p.openreview_api_version,
                   p.human_decision, p.num_graph_review
            FROM paper p ORDER BY p.id""")
        authors = fetch_all(cur, "SELECT id, full_name, affiliation, openreview_profile_id FROM author ORDER BY id")
        paper_authors = fetch_all(cur, "SELECT paper_id, author_id, position FROM paper_author ORDER BY paper_id, position")
        open_review = fetch_all(cur, "SELECT * FROM open_review ORDER BY paper_id, reviewer_index NULLS LAST, id")
        prompt_versions = fetch_all(cur, "SELECT * FROM prompt_version ORDER BY id")
        prompt_instructions = fetch_all(cur, "SELECT * FROM prompt_instruction ORDER BY id")
        presets = fetch_all(cur, "SELECT * FROM system_prompt_preset ORDER BY id")

    for stale in (OUT / "traces").glob("*.json"):
        stale.unlink()
    run_ids = {run["run_id"] for run in runs}
    trace_files = 0
    orphan_bundles = 0
    for key in sorted(r.scan_iter(match=TRACE_PREFIX + "*")):
        run_id = key[len(TRACE_PREFIX):]
        if run_id not in run_ids:
            orphan_bundles += 1
            continue
        bundle = json.loads(r.get(key))
        for trace in bundle.get("traces", []):
            trace.pop("context_used", None)
            context_hash = trace.get("context_hash")
            trace["context_chars"] = r.strlen(CONTEXT_PREFIX + context_hash) if context_hash else 0
            truncate_tool_results(trace)
        safe_name = run_id.replace(":", "_")
        (OUT / "traces" / f"{safe_name}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
        trace_files += 1

    def dump(name: str, payload) -> None:
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    dump("runs.json", runs)
    dump("agents.json", agents)
    dump("papers.json", {"papers": papers, "authors": authors, "paper_authors": paper_authors})
    dump("open_review.json", open_review)
    dump("prompts.json", {"versions": prompt_versions, "instructions": prompt_instructions, "presets": presets})
    dump("manifest.json", {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "runs": len(runs), "agent_invocations": len(agents), "papers": len(papers),
            "human_reviews": len(open_review), "trace_bundles": trace_files,
            "prompt_versions": len(prompt_versions), "prompt_instructions": len(prompt_instructions),
            "presets": len(presets),
        },
        "exclusions": [
            "full paper texts (agent-context keyspace): traces keep hash and length only",
            f"tool results truncated to {TOOL_RESULT_PREVIEW_CHARS} chars",
            "author emails dropped",
            "orphan trace bundles of runs deleted from the archive are not exported",
        ],
        "notes": [
            "the thesis cost accounting also includes discarded misconfigured executions "
            "that were deleted from the archive and therefore have no trace here",
        ],
    })
    print(f"Exported to {OUT}: {len(runs)} runs, {len(agents)} invocations, "
          f"{trace_files} trace bundles ({orphan_bundles} orphans skipped).")


if __name__ == "__main__":
    main()
