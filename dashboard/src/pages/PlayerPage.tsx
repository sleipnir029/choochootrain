// Player view (P6 revision): skill percentile + over/under-performance trend
// (expected vs actual ACS) + per-team-stint stats (SPEC D2).
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getPlayer, type PlayerView } from '../lib/api'

export function PlayerPage() {
  const { id } = useParams()
  const playerId = Number(id)
  const q = useQuery<PlayerView>({ queryKey: ['playerView', playerId], queryFn: () => getPlayer(playerId), enabled: Number.isFinite(playerId) })

  if (q.isLoading) return <div className="panel loading">Loading player…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const p = q.data!
  const chart = p.stints.map((s) => ({ team: s.team_tag || s.team_name || `#${s.team_id}`, acs: s.avg_acs ?? 0 }))

  return (
    <>
      <div className="panel">
        <div className="teams-row">
          <span className="team-name t1">{p.handle}</span>
          <span className="muted">{p.real_name ?? ''}{p.current_team_name ? ` · now ${p.current_team_name}` : ''}</span>
        </div>

        {p.skill && (
          <div style={{ marginTop: 8 }}>
            <div className="sub">Skill rating {p.skill.rating} — {p.skill.percentile}th percentile of {p.skill.rated_players} rated players</div>
            <div className="pctile"><div style={{ width: `${p.skill.percentile}%` }} /></div>
          </div>
        )}

        {p.recent_form.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="sub">Recent form — actual vs expected ACS (over/under his baseline)</div>
            <div className="form-list">
              {p.recent_form.map((f) => {
                const cls = f.delta_acs >= 25 ? 'over' : f.delta_acs <= -25 ? 'under' : ''
                return (
                  <div className="form-row" key={f.match_id}>
                    <span className="muted date">{f.date}</span>
                    <span className="opp">vs {f.opponent}</span>
                    <span>{f.actual_acs.toFixed(0)} ACS</span>
                    <span className="muted">exp {f.expected_acs.toFixed(0)}</span>
                    <span className={cls}>{f.delta_acs > 0 ? '+' : ''}{f.delta_acs.toFixed(0)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="sub">By team stint — each team kept separate (SPEC D2)</div>
        <table className="stints">
          <thead><tr><th>Team</th><th>Maps</th><th>Rating</th><th>ACS</th><th>K</th><th>D</th><th>A</th><th>Span</th></tr></thead>
          <tbody>
            {p.stints.map((s) => (
              <tr key={s.team_id}>
                <td>{s.team_name ?? `#${s.team_id}`}{s.team_tag ? ` (${s.team_tag})` : ''}</td>
                <td>{s.n_maps}</td><td>{s.avg_rating ?? '—'}</td><td>{s.avg_acs ?? '—'}</td>
                <td>{s.avg_kills ?? '—'}</td><td>{s.avg_deaths ?? '—'}</td><td>{s.avg_assists ?? '—'}</td>
                <td className="muted">{s.first_date?.slice(0, 10)} → {s.last_date?.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {chart.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="sub">Average ACS per stint</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chart} margin={{ top: 6, right: 6, bottom: 0, left: -20 }}>
                <CartesianGrid stroke="#2a3340" vertical={false} />
                <XAxis dataKey="team" stroke="#8b949e" fontSize={12} />
                <YAxis stroke="#8b949e" fontSize={12} />
                <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }} cursor={{ fill: '#1c2330' }} />
                <Bar dataKey="acs" fill="#4ea1ff" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </>
  )
}
