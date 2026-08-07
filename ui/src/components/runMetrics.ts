/**
 * runMetrics — pure helpers shared by the RunHistory and RunCompare pages:
 * extracting the final per-reviewer records from a run, numeric means, token
 * totals, and the accept / non-accept binarization used for the decision
 * verdict (human decisions are free text like "Accept (Poster)").
 */
import type { AgentResponseRecord, GraphReviewRecord, OpenReviewItem } from '../api/types';

export function payloadNum(payload: Record<string, unknown> | undefined, key: string): number | null {
  const value = payload?.[key];
  return typeof value === 'number' ? value : null;
}

/** Mean of the non-null values, null when nothing is numeric. */
export function mean(values: (number | null | undefined)[]): number | null {
  const nums = values.filter((v): v is number => typeof v === 'number');
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

export function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

export function formatNum(value: number | null, digits = 1): string {
  return value === null ? '—' : String(Math.round(value * 10 ** digits) / 10 ** digits);
}

/** The LAST invocation per reviewer index (the final round's review), ordered
 * by index — the values a human would compare against. */
export function finalReviewers(record: GraphReviewRecord): AgentResponseRecord[] {
  const byIndex = new Map<number, AgentResponseRecord>();
  for (const rec of record.agent_records ?? []) {
    if (rec.agent_role !== 'reviewer') continue;
    const index = rec.agent_index ?? 0;
    const current = byIndex.get(index);
    if (!current || rec.round >= current.round) byIndex.set(index, rec);
  }
  return [...byIndex.entries()].sort(([a], [b]) => a - b).map(([, rec]) => rec);
}

/** The last invocation of a singleton role (meta_reviewer, area_chair). */
export function lastByRole(record: GraphReviewRecord, role: string): AgentResponseRecord | null {
  const records = (record.agent_records ?? []).filter((r) => r.agent_role === role);
  return records.length > 0 ? records[records.length - 1] : null;
}

export function totalTokens(record: GraphReviewRecord): number | null {
  const totals = (record.agent_records ?? []).map((r) => r.total_tokens).filter((t): t is number => typeof t === 'number');
  if (totals.length === 0) return null;
  return totals.reduce((a, b) => a + b, 0);
}

export function formatTokens(total: number | null): string {
  if (total === null) return '—';
  return total >= 1000 ? `${round1(total / 1000)}k` : String(total);
}

/** Human reviewer notes, ordered by reviewer index. */
export function humanReviewers(items: OpenReviewItem[]): OpenReviewItem[] {
  return items
    .filter((i) => i.reviewer_type === 'reviewer')
    .sort((a, b) => (a.reviewer_index ?? 0) - (b.reviewer_index ?? 0));
}

export function humanMeta(items: OpenReviewItem[]): OpenReviewItem | null {
  return items.find((i) => i.reviewer_type === 'meta_reviewer') ?? null;
}

export function humanAreaChair(items: OpenReviewItem[]): OpenReviewItem | null {
  return items.find((i) => i.reviewer_type === 'area_chair') ?? null;
}

/** Binarize a decision to accept / non-accept: graph decisions are the enum
 * (accept / minor_revision / …), human ones free text ("Accept (Poster)"). */
export function isAccept(decision: string | null | undefined): boolean | null {
  if (!decision) return null;
  return decision.toLowerCase().includes('accept');
}
