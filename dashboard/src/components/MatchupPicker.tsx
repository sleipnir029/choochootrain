// Pick any two teams and jump to their head-to-head matchup prep view.
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getTeams, PRX_TEAM_ID, type TeamListItem } from '../lib/api'

export function MatchupPicker() {
  const { data: teams } = useQuery<TeamListItem[]>({ queryKey: ['teams'], queryFn: getTeams })
  const nav = useNavigate()
  const [t1, setT1] = useState<number>(PRX_TEAM_ID)
  const [t2, setT2] = useState<number | undefined>()
  if (!teams || teams.length === 0) return null

  const opp = t2 && t2 !== t1 ? t2 : teams.find((t) => t.team_id !== t1)?.team_id
  return (
    <div className="panel">
      <div className="sub">Scout a matchup — pick any two teams</div>
      <div className="picker-row">
        <select className="input select" value={t1} onChange={(e) => setT1(Number(e.target.value))}>
          {teams.map((t) => <option key={t.team_id} value={t.team_id}>{t.name}</option>)}
        </select>
        <span className="muted">vs</span>
        <select className="input select" value={opp} onChange={(e) => setT2(Number(e.target.value))}>
          {teams.filter((t) => t.team_id !== t1).map((t) => <option key={t.team_id} value={t.team_id}>{t.name}</option>)}
        </select>
        <button className="btn active" disabled={!opp} onClick={() => opp && nav(`/matchup/${t1}/${opp}`)}>
          Scout →
        </button>
      </div>
    </div>
  )
}
