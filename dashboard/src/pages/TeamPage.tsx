// Team scouting (Wave B — analyst): map pool + side tendencies + economy + agent
// comps + opening duels, over the team's recent maps. Derived from existing data.
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getTeamScouting, type TeamScouting } from '../lib/api'

const pc = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`)

export function TeamPage() {
  const { id } = useParams()
  const teamId = Number(id)
  const q = useQuery<TeamScouting>({
    queryKey: ['scouting', teamId], queryFn: () => getTeamScouting(teamId), enabled: Number.isFinite(teamId),
  })
  if (q.isLoading) return <div className="panel loading">Loading scouting report…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const s = q.data!
  const econ = s.economy

  return (
    <>
      <div className="prx-head">
        <h2>{s.team.name}</h2>
        <span className="rank-chip">scouting · last {s.window_maps} maps</span>
      </div>

      <div className="panel">
        <div className="sub">Map pool & side tendencies</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Played</th><th>Win%</th><th>CT win%</th><th>T win%</th></tr></thead>
          <tbody>
            {s.map_pool.map((m) => (
              <tr key={m.map_name}>
                <td>{m.map_name}</td><td>{m.n}</td>
                <td className={(m.win_rate ?? 0) >= 0.6 ? 'over' : (m.win_rate ?? 1) <= 0.4 ? 'under' : ''}>{pc(m.win_rate)}</td>
                <td className="muted">{pc(m.ct_win_rate)}</td>
                <td className="muted">{pc(m.t_win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {econ && (
        <div className="panel">
          <div className="sub">Economy efficiency (win% by buy type)</div>
          <div className="roster-grid">
            {[['Pistol', econ.pistol], ['Eco', econ.eco], ['Semi-buy', econ.semi_buy], ['Full-buy', econ.full_buy]].map(([k, v]) => (
              <div className="roster-card" key={k as string}>
                <div className="rc-name muted">{k}</div>
                <div className="rc-skill">{v}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="sub">Most-run comp per map</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Comp</th><th>n</th><th>Win%</th></tr></thead>
          <tbody>
            {s.agents.comps_by_map.map((c) => (
              <tr key={c.map_name}>
                <td>{c.map_name}</td>
                <td>{c.comp.join(' · ')}</td>
                <td>{c.n}</td>
                <td className={(c.win_rate ?? 0) >= 0.6 ? 'over' : (c.win_rate ?? 1) <= 0.4 ? 'under' : ''}>{pc(c.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="sub">Opening duels — entry win rate (first kills vs first deaths)</div>
        {s.opening_duels.team && (
          <div className="muted" style={{ marginBottom: 8 }}>
            Team: {s.opening_duels.team.fk} FK / {s.opening_duels.team.fd} FD ·{' '}
            <strong>{pc(s.opening_duels.team.win_rate)}</strong> entry win rate
          </div>
        )}
        <table className="stints">
          <thead><tr><th>Player</th><th>FK</th><th>FD</th><th>Entry win%</th></tr></thead>
          <tbody>
            {s.opening_duels.by_player.map((d) => (
              <tr key={d.handle}>
                <td>{d.handle}</td><td>{d.fk}</td><td>{d.fd}</td>
                <td className={(d.win_rate ?? 0) >= 0.55 ? 'over' : (d.win_rate ?? 1) <= 0.45 ? 'under' : ''}>{pc(d.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="sub">Agent pools</div>
        <table className="stints">
          <thead><tr><th>Player</th><th>Agents (most played)</th></tr></thead>
          <tbody>
            {s.agents.by_player.map((p) => (
              <tr key={p.handle}>
                <td>{p.handle}</td>
                <td className="muted">{p.agents.slice(0, 6).map((a) => `${a.agent} (${a.n})`).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
