// Player panel (P6.T7): profile + stats broken out by team stint (SPEC D2 — no
// cross-team pooling) + a per-stint ACS bar chart.
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getPlayer, getPlayerStats, type PlayerProfile, type PlayerStats } from '../lib/api'

export function PlayerPanel({ playerId }: { playerId?: number }) {
  const enabled = playerId != null
  const profile = useQuery<PlayerProfile>({
    queryKey: ['player', playerId], queryFn: () => getPlayer(playerId!), enabled,
  })
  const stats = useQuery<PlayerStats>({
    queryKey: ['playerStats', playerId], queryFn: () => getPlayerStats(playerId!), enabled,
  })

  if (!enabled) return <div className="panel muted">Enter a player ID to view their profile.</div>
  if (profile.isLoading || stats.isLoading) return <div className="panel loading">Loading player…</div>
  if (profile.isError) return <div className="panel error">{(profile.error as Error).message}</div>
  if (stats.isError) return <div className="panel error">{(stats.error as Error).message}</div>

  const p = profile.data!
  const stints = stats.data!.stints
  const chart = stints.map((s) => ({ team: s.team_tag || s.team_name || `#${s.team_id}`, acs: s.avg_acs ?? 0 }))

  return (
    <div className="panel">
      <div className="teams-row">
        <span className="team-name t1">{p.handle}</span>
        <span className="muted">
          {p.real_name ?? ''}{p.current_team_name ? ` · now ${p.current_team_name}` : ''}
        </span>
      </div>
      <div className="sub">Stats by team stint — each team kept separate (SPEC D2).</div>

      <table className="stints">
        <thead>
          <tr>
            <th>Team</th><th>Maps</th><th>Rating</th><th>ACS</th>
            <th>K</th><th>D</th><th>A</th><th>Span</th>
          </tr>
        </thead>
        <tbody>
          {stints.map((s) => (
            <tr key={s.team_id}>
              <td>{s.team_name ?? `#${s.team_id}`}{s.team_tag ? ` (${s.team_tag})` : ''}</td>
              <td>{s.n_maps}</td>
              <td>{s.avg_rating ?? '—'}</td>
              <td>{s.avg_acs ?? '—'}</td>
              <td>{s.avg_kills ?? '—'}</td>
              <td>{s.avg_deaths ?? '—'}</td>
              <td>{s.avg_assists ?? '—'}</td>
              <td className="muted">{s.first_date?.slice(0, 10)} → {s.last_date?.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {chart.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <div className="sub">Average ACS per stint</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chart} margin={{ top: 6, right: 6, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="#2a3340" vertical={false} />
              <XAxis dataKey="team" stroke="#8b949e" fontSize={12} />
              <YAxis stroke="#8b949e" fontSize={12} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }}
                cursor={{ fill: '#1c2330' }}
              />
              <Bar dataKey="acs" fill="#4ea1ff" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
