/**
 * charts — small pure CSS/SVG chart primitives for the run-history and
 * comparison pages. No chart library: flat marks on the app's design tokens,
 * two fixed series colors (purple = grafo, green = umani, set in
 * run-insights.css and validated for both themes), values always direct-labeled
 * so color is never the only carrier.
 */
import type { ReactNode } from 'react';

export function MetricCard({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="ri-metric">
      <span className="ri-metric__label">{label}</span>
      <span className="ri-metric__value">{value}</span>
      {hint && <span className="ri-metric__hint">{hint}</span>}
    </div>
  );
}

export function ChartLegend() {
  return (
    <div className="ri-legend" aria-hidden="true">
      <span><i className="ri-dot ri-dot--graph" /> Grafo</span>
      <span><i className="ri-dot ri-dot--human" /> Umani</span>
    </div>
  );
}

/** One horizontal bar with its value printed at the end (single series). */
export function BarRow({ label, value, max, sublabel }: {
  label: string;
  value: number | null;
  max: number;
  sublabel?: string;
}) {
  const width = value === null ? 0 : Math.max(2, (value / max) * 100);
  return (
    <div className="ri-bar-row" title={sublabel ? `${label}: ${value ?? '—'} (${sublabel})` : `${label}: ${value ?? '—'}`}>
      <span className="ri-bar-row__label">{label}{sublabel && <em className="ri-bar-row__sub">{sublabel}</em>}</span>
      <div className="ri-bar-row__track">
        {value !== null && <div className="ri-bar-row__fill ri-fill--graph" style={{ width: `${width}%` }} />}
      </div>
      <span className="ri-bar-row__value">{value ?? '—'}</span>
    </div>
  );
}

export interface DumbbellRow {
  label: string;
  graph: number | null;
  human: number | null;
}

/** Dumbbell: one row per entity, a dot per series on a shared scale — the
 * segment length IS the disagreement. Values printed on the right. */
export function DumbbellChart({ rows, min, max }: { rows: DumbbellRow[]; min: number; max: number }) {
  const pos = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="ri-dumbbell">
      {rows.map((row) => {
        const both = row.graph !== null && row.human !== null;
        const left = both ? Math.min(pos(row.graph!), pos(row.human!)) : 0;
        const width = both ? Math.abs(pos(row.graph!) - pos(row.human!)) : 0;
        return (
          <div key={row.label} className="ri-dumbbell__row" title={`${row.label}: grafo ${row.graph ?? '—'} · umani ${row.human ?? '—'}`}>
            <span className="ri-dumbbell__label">{row.label}</span>
            <div className="ri-dumbbell__track">
              {both && <div className="ri-dumbbell__segment" style={{ left: `${left}%`, width: `${width}%` }} />}
              {row.human !== null && <i className="ri-dot ri-dot--human ri-dumbbell__dot" style={{ left: `${pos(row.human)}%` }} />}
              {row.graph !== null && <i className="ri-dot ri-dot--graph ri-dumbbell__dot" style={{ left: `${pos(row.graph)}%` }} />}
            </div>
            <span className="ri-dumbbell__values">
              {row.graph ?? '—'} <em>vs</em> {row.human ?? '—'}
            </span>
          </div>
        );
      })}
      <div className="ri-dumbbell__scale"><span>{min}</span><span>{max}</span></div>
    </div>
  );
}

export interface PairedGroup {
  label: string;
  graph: number | null;
  human: number | null;
}

/** Vertical paired bars per group (grafo | umani), values on top of each bar. */
export function PairedBars({ groups, max }: { groups: PairedGroup[]; max: number }) {
  const height = (v: number | null) => (v === null ? 0 : Math.max(3, (v / max) * 100));
  return (
    <div className="ri-paired">
      {groups.map((g) => (
        <div key={g.label} className="ri-paired__group" title={`${g.label}: grafo ${g.graph ?? '—'} · umani ${g.human ?? '—'}`}>
          <div className="ri-paired__bars">
            <div className="ri-paired__col">
              <span className="ri-paired__value">{g.graph ?? '—'}</span>
              <div className="ri-paired__bar ri-fill--graph" style={{ height: `${height(g.graph)}%` }} />
            </div>
            <div className="ri-paired__col">
              <span className="ri-paired__value">{g.human ?? '—'}</span>
              <div className="ri-paired__bar ri-fill--human" style={{ height: `${height(g.human)}%` }} />
            </div>
          </div>
          <span className="ri-paired__label">{g.label}</span>
        </div>
      ))}
    </div>
  );
}

export interface TrendPoint {
  label: string;
  value: number;
}

/** Small SVG line of a run metric over time, with an optional dashed human
 * reference line. Fixed 1..max domain, direct label on every point. */
export function TrendChart({ points, refValue, refLabel, max }: {
  points: TrendPoint[];
  refValue: number | null;
  refLabel: string;
  max: number;
}) {
  const width = 560;
  const height = 120;
  const padX = 16;
  const padY = 18;
  const x = (i: number) => points.length === 1
    ? width / 2
    : padX + (i / (points.length - 1)) * (width - 2 * padX);
  const y = (v: number) => height - padY - ((v - 1) / (max - 1)) * (height - 2 * padY);
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(p.value)}`).join(' ');
  return (
    <svg className="ri-trend" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Andamento del meta score nelle run del paper">
      {refValue !== null && (
        <g>
          <line className="ri-trend__ref" x1={padX} y1={y(refValue)} x2={width - padX} y2={y(refValue)} />
          <text className="ri-trend__ref-label" x={width - padX} y={y(refValue) - 5} textAnchor="end">{refLabel} {refValue}</text>
        </g>
      )}
      {points.length > 1 && <path className="ri-trend__line" d={path} />}
      {points.map((p, i) => (
        <g key={i}>
          <circle className="ri-trend__dot" cx={x(i)} cy={y(p.value)} r={4}>
            <title>{p.label}: {p.value}</title>
          </circle>
          <text className="ri-trend__value" x={x(i)} y={y(p.value) - 8} textAnchor="middle">{p.value}</text>
        </g>
      ))}
    </svg>
  );
}
