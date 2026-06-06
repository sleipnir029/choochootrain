// Live panel (P6.T6): polls /api/predict/live every 30s; shows score, side,
// live win prob, and a sparkline of probability across score changes.
import { useQuery } from '@tanstack/react-query'
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { getLive, type Live } from '../lib/api'
import { WinProbBar } from './WinProbBar'

export function LivePanel() {
  const q = useQuery<Live>({
    queryKey: ['live'],
    queryFn: getLive,
    refetchInterval: 30_000, // ARCHITECTURE §7.1: live mode polls every 30s
  })

  if (q.isLoading) return <div className="panel loading">Checking for a live match…</div>
  if (q.isError) return <div className="panel error">Live feed error: {(q.error as Error).message}</div>

  const d = q.data!
  if (d.mode === 'no_live') {
    return (
      <div className="panel">
        <h2>No live match</h2>
        <div className="sub">
          No tier-1 match is currently live (poller source: {d.source}). The live feed needs the
          score poller running.
        </div>
      </div>
    )
  }

  const prob = d.team1_win_prob_current_map
  const history = d.probability_history.map((h, i) => ({ i, prob: h.prob }))

  return (
    <div className="panel">
      <div className="teams-row">
        <span className="mode-pill live">● Live</span>
        <span className="muted">map {d.current_map_index + 1}{d.current_map ? ` · ${d.current_map}` : ''}</span>
        <span className="muted">updated {new Date(d.last_updated).toLocaleTimeString()}</span>
      </div>

      <div className="scoreline" style={{ margin: '8px 0 16px' }}>
        <span className="t1">{d.team1_score ?? 0}</span>
        <span className="muted"> – </span>
        <span className="t2">{d.team2_score ?? 0}</span>
        <span className="muted" style={{ fontSize: 13, marginLeft: 12 }}>
          rounds {(d.team1_round_ct ?? 0) + (d.team1_round_t ?? 0)}–{(d.team2_round_ct ?? 0) + (d.team2_round_t ?? 0)}
        </span>
      </div>

      {prob != null ? (
        <>
          <div className="sub">Current-map win probability (team 1)</div>
          <WinProbBar p1={prob} />
          <div className="hdi">{(prob * 100).toFixed(0)}%</div>
        </>
      ) : (
        <div className="muted">No prediction yet for this map (match may not be ingested).</div>
      )}

      {history.length > 1 && (
        <div style={{ marginTop: 16 }}>
          <div className="sub">Probability trend</div>
          <ResponsiveContainer width="100%" height={90}>
            <LineChart data={history} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <YAxis domain={[0, 1]} hide />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }}
                formatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
                labelFormatter={() => ''}
              />
              <Line type="monotone" dataKey="prob" stroke="#4ea1ff" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
