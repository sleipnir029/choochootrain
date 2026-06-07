// Reusable visualization primitives (Phase C) — composed by the team/player/matchup pages.
// All SVG/CSS, no chart lib; each is small and answer-first.
import type { ReactNode } from 'react'

const clamp01 = (x: number) => Math.max(0, Math.min(1, x))

// Big answer-first number + label + context/delta.
export function Ban({ label, value, sub, delta }: {
  label: string; value: ReactNode; sub?: ReactNode; delta?: number | null
}) {
  return (
    <div className="ban">
      <div className="ban-label">{label}</div>
      <div className="ban-value">{value}</div>
      {(sub != null || delta != null) && (
        <div className="ban-sub">
          {delta != null && (
            <span className={delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : 'delta-flat'}>
              {delta > 0 ? '▲ +' : delta < 0 ? '▼ −' : '± '}{Math.abs(Math.round(delta))}
            </span>
          )}
          {delta != null && sub != null && ' · '}
          {sub}
        </div>
      )}
    </div>
  )
}

// Recent W/L momentum, oldest → newest.
export function FormDots({ results }: { results: ('W' | 'L')[] }) {
  return <span className="form-dots">{results.map((r, i) => <i key={i} className={r === 'W' ? 'w' : 'l'}>{r}</i>)}</span>
}

// Generic labelled bar. frac 0..1 fills the track; `value` is the printed text.
export function Bar({ label, frac, value, tone }: {
  label: ReactNode; frac: number; value: ReactNode; tone?: 'hi' | 'lo' | ''
}) {
  return (
    <div className="pct-bar">
      <span>{label}</span>
      <span className="track"><span className={`fill ${tone ?? ''}`} style={{ width: `${Math.round(clamp01(frac) * 100)}%` }} /></span>
      <span className="pv">{value}</span>
    </div>
  )
}

// Two teams compared across metrics; a/b are 0..1 positions on a shared track.
export function Dumbbell({ rows, aName, bName }: {
  rows: { label: string; a: number; b: number; aText?: string; bText?: string }[]; aName: string; bName: string
}) {
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        <span className="t1">●</span> {aName} &nbsp; <span className="t2">●</span> {bName}
      </div>
      {rows.map((r) => {
        const ax = clamp01(r.a) * 100, bx = clamp01(r.b) * 100
        const lo = Math.min(ax, bx), hi = Math.max(ax, bx)
        return (
          <div className="dumbbell" key={r.label}>
            <span className="dlabel">{r.label}</span>
            <div className="dumb-track">
              <span className="line" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
              <span className="dot a" style={{ left: `${ax}%` }} title={`${aName}: ${r.aText ?? ''}`} />
              <span className="dot b" style={{ left: `${bx}%` }} title={`${bName}: ${r.bText ?? ''}`} />
              {r.aText && <span className="dv a" style={{ left: `${ax}%` }}>{r.aText}</span>}
              {r.bText && <span className="dv b" style={{ left: `${bx}%` }}>{r.bText}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Relative-edge spectrum: edge in -1..1 (−1 = team2/red, +1 = team1/green).
export function Spectrum({ rows }: { rows: { label: ReactNode; edge: number; note?: ReactNode }[] }) {
  return (
    <div>
      {rows.map((r, i) => {
        const pos = ((Math.max(-1, Math.min(1, r.edge)) + 1) / 2) * 100
        return (
          <div className="spectrum-row" key={i}>
            <span>{r.label}</span>
            <div className="spectrum-track"><span className="mark" style={{ left: `${pos}%` }} /></div>
            <span className="muted" style={{ fontSize: 12, textAlign: 'right' }}>{r.note}</span>
          </div>
        )
      })}
    </div>
  )
}

// Radar/pizza with the percentile printed at each axis. axes pct 0..100.
export function Pizza({ axes, size = 230 }: { axes: { label: string; pct: number }[]; size?: number }) {
  const cx = size / 2, cy = size / 2, r = size / 2 - 34, n = axes.length
  const ang = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const pt = (i: number, rad: number): [number, number] => [cx + Math.cos(ang(i)) * rad, cy + Math.sin(ang(i)) * rad]
  const poly = axes.map((a, i) => pt(i, (r * clamp01(a.pct / 100))).join(',')).join(' ')
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
      {[0.25, 0.5, 0.75, 1].map((g) => <circle key={g} className="pizza-grid" cx={cx} cy={cy} r={r * g} />)}
      {axes.map((_, i) => { const [ex, ey] = pt(i, r); return <line key={i} className="pizza-grid" x1={cx} y1={cy} x2={ex} y2={ey} /> })}
      <polygon className="pizza-slice" points={poly} />
      {axes.map((a, i) => {
        const [lx, ly] = pt(i, r + 18); const [vx, vy] = pt(i, r * clamp01(Math.max(a.pct, 9) / 100))
        return (
          <g key={i}>
            <text className="pizza-axis" x={lx} y={ly} textAnchor="middle" dominantBaseline="middle">{a.label}</text>
            <text className="pizza-val" x={vx} y={vy} textAnchor="middle" dominantBaseline="middle">{Math.round(a.pct)}</text>
          </g>
        )
      })}
    </svg>
  )
}
