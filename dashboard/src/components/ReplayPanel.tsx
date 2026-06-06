// Post-match replay panel (P6.T8): round-by-round prediction trace per map.
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getReplay, type Replay } from '../lib/api'

export function ReplayPanel({ matchId }: { matchId?: number }) {
  const enabled = matchId != null
  const q = useQuery<Replay>({
    queryKey: ['replay', matchId], queryFn: () => getReplay(matchId!), enabled,
  })

  if (!enabled) return <div className="panel muted">Enter a completed match ID to see its replay.</div>
  if (q.isLoading) return <div className="panel loading">Loading replay…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>

  const d = q.data!
  return (
    <div className="panel">
      <h2>Replay — match {d.match_id}</h2>
      <div className="sub">Pre-round win probability for team 1, round by round.</div>
      {d.maps.map((m) => {
        const data = m.rounds.map((r) => ({
          round: r.round,
          prob: r.pre_round_prob_team1,
          winner: r.winner,
        }))
        return (
          <div key={m.map_index} style={{ marginBottom: 22 }}>
            <div className="sub" style={{ marginBottom: 6 }}>
              Map {m.map_index + 1} — {m.map_name}
            </div>
            <div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="#2a3340" vertical={false} />
                  <XAxis dataKey="round" stroke="#8b949e" fontSize={11} />
                  <YAxis domain={[0, 1]} stroke="#8b949e" fontSize={11}
                    tickFormatter={(v) => `${Math.round(v * 100)}`} />
                  <ReferenceLine y={0.5} stroke="#3a4452" strokeDasharray="3 3" />
                  <Tooltip
                    contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }}
                    formatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
                    labelFormatter={(l) => `Round ${l}`}
                  />
                  <Line type="monotone" dataKey="prob" stroke="#4ea1ff" strokeWidth={2}
                    dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      })}
    </div>
  )
}
