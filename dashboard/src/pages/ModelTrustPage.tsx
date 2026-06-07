// Model trust (decision-grade Wave A): is the model calibrated, and WHERE is it
// actually sharp vs a coinflip? Honest, out-of-sample track record.
import { useQuery } from '@tanstack/react-query'
import {
  ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { getTrackRecord, type RegimeAgg, type TrackRecord } from '../lib/api'

const pc = (x: number) => `${(x * 100).toFixed(1)}%`

function RegimeTable({ rows, label }: { rows: RegimeAgg[]; label: string }) {
  return (
    <table className="stints">
      <thead><tr><th>{label}</th><th>n</th><th>Accuracy</th><th>vs Elo</th><th>Brier</th></tr></thead>
      <tbody>
        {rows.map((r, i) => {
          const name = r.confidence ?? r.tier ?? r.bucket ?? '—'
          const cls = r.confidence === 'sharp' ? 'over' : r.confidence === 'coinflip' ? 'under' : ''
          return (
            <tr key={i}>
              <td className={cls}>{name}</td>
              <td>{r.n}</td>
              <td className={cls}>{pc(r.acc)}</td>
              <td className="muted">{r.elo_sign_acc != null ? pc(r.elo_sign_acc) : '—'}</td>
              <td>{r.brier.toFixed(3)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function ModelTrustPage() {
  const q = useQuery<TrackRecord>({ queryKey: ['trackRecord'], queryFn: getTrackRecord })
  if (q.isLoading) return <div className="panel loading">Loading track record…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const d = q.data!
  if (!d.available) return <div className="panel muted">No track record yet — run <code>python -m models.backtest</code>. ({d.reason})</div>
  const o = d.overall!

  return (
    <>
      <div className="prx-head"><h2>Model trust</h2><span className="rank-chip">out-of-sample · n={o.n}</span></div>

      <div className="panel">
        <div className="insight tone-expected">
          <div className="insight-headline">Honest track record — accuracy {pc(o.acc)} (Elo baseline {pc(o.elo_sign_acc)}), Brier {o.brier.toFixed(3)}.</div>
          <ul className="insight-points">
            <li>The headline number is capped — the model essentially <em>is</em> Elo, so most maps are coinflips.</li>
            <li>The value is knowing <strong>where</strong> it's sharp: trust the <span className="over">sharp</span> regime, fade the <span className="under">coinflip</span> one.</li>
          </ul>
        </div>
      </div>

      <div className="panel">
        <div className="sub">Where the model is sharp vs a coinflip (this is what decisions key off)</div>
        <RegimeTable rows={d.by_confidence ?? []} label="Confidence" />
      </div>

      <div className="panel">
        <div className="sub">Calibration — predicted probability vs actual outcome frequency (on the diagonal = honest)</div>
        <ResponsiveContainer width="100%" height={300}>
          <ScatterChart margin={{ top: 10, right: 16, bottom: 6, left: -10 }}>
            <XAxis type="number" dataKey="predicted" domain={[0, 1]} stroke="#8b949e" fontSize={11}
              tickFormatter={(v) => `${Math.round(v * 100)}`} name="predicted" />
            <YAxis type="number" dataKey="actual" domain={[0, 1]} stroke="#8b949e" fontSize={11}
              tickFormatter={(v) => `${Math.round(v * 100)}`} name="actual" />
            <ZAxis type="number" dataKey="n" range={[40, 400]} name="n" />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#3a4452" strokeDasharray="4 4" />
            <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }}
              formatter={(v, n) => [pc(Number(v)), String(n)]} cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={d.reliability} fill="#4ea1ff" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="panel">
        <div className="sub">By tier</div>
        <RegimeTable rows={d.by_tier ?? []} label="Tier" />
      </div>

      <div className="panel">
        <div className="sub">By Elo gap — the real signal (bigger gap → sharper)</div>
        <RegimeTable rows={d.by_elo_bucket ?? []} label="|Elo diff|" />
      </div>

      <div className="panel">
        <div className="sub">Recent out-of-sample calls</div>
        <div className="recent-list">
          {(d.recent ?? []).map((r, i) => (
            <div key={i} className="recent-row" style={{ gridTemplateColumns: '92px 90px 1fr 90px 24px' }}>
              <span className="muted date">{r.date_utc.slice(0, 10)}</span>
              <span className={`res ${r.confidence === 'sharp' ? 'win' : ''}`}>{r.confidence}</span>
              <span className="opp muted">{r.tier}</span>
              <span className="pred">said {pc(r.team1_win_prob)}</span>
              <span className={`mark ${r.correct ? 'ok' : 'miss'}`}>{r.correct ? '✓' : '✗'}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
