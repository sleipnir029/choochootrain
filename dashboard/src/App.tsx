// App shell (P6.T4) + default-view auto-detect (P6.T9 / SPEC D3).
// On mount we query /api/predict/live: if a tier-1 match is live, default to the
// Live panel; otherwise default to a Pre-match panel for PRX's next matchup. A
// manual switcher always overrides the auto-detected view.
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLive, PRX_TEAM_ID, type Live } from './lib/api'
import { PreMatchPanel } from './components/PreMatchPanel'
import { LivePanel } from './components/LivePanel'
import { PlayerPanel } from './components/PlayerPanel'
import { ReplayPanel } from './components/ReplayPanel'

type Mode = 'live' | 'pre' | 'player' | 'replay'
const DEFAULT_OPPONENT = 188 // Sentinels — representative PRX matchup until veto/schedule is known

const PLACEHOLDER: Record<Mode, string> = {
  live: '',
  pre: 'match ID (optional)',
  player: 'player ID',
  replay: 'match ID',
}

export default function App() {
  const live = useQuery<Live>({ queryKey: ['live'], queryFn: getLive })
  const [manualMode, setManualMode] = useState<Mode | null>(null)
  const [idText, setIdText] = useState('')
  const [applied, setApplied] = useState<Record<Mode, number | undefined>>({
    live: undefined, pre: undefined, player: undefined, replay: undefined,
  })

  const liveMode = live.data?.mode === 'live'
  const autoMode: Mode = liveMode ? 'live' : 'pre'
  const mode: Mode = manualMode ?? autoMode

  const apply = () => {
    const n = parseInt(idText, 10)
    setApplied((a) => ({ ...a, [mode]: Number.isFinite(n) ? n : undefined }))
  }

  const panel = useMemo(() => {
    switch (mode) {
      case 'live':
        return <LivePanel />
      case 'player':
        return <PlayerPanel playerId={applied.player} />
      case 'replay':
        return <ReplayPanel matchId={applied.replay} />
      case 'pre':
      default:
        return applied.pre != null
          ? <PreMatchPanel matchId={applied.pre} />
          : <PreMatchPanel team1Id={PRX_TEAM_ID} team2Id={DEFAULT_OPPONENT} />
    }
  }, [mode, applied])

  const modes: { key: Mode; label: string }[] = [
    { key: 'live', label: 'Live' },
    { key: 'pre', label: 'Pre-match' },
    { key: 'player', label: 'Player' },
    { key: 'replay', label: 'Replay' },
  ]

  return (
    <>
      <header className="topbar">
        <h1>PRX PREDICTOR</h1>
        <span className={`mode-pill ${liveMode ? 'live' : ''}`}>
          {live.isLoading ? 'detecting…' : liveMode ? 'live' : 'no live match'}
        </span>
        <div className="spacer" />
        {modes.map((m) => (
          <button
            key={m.key}
            className={`btn ${mode === m.key ? 'active' : ''}`}
            onClick={() => setManualMode(m.key)}
          >
            {m.label}
          </button>
        ))}
        {mode !== 'live' && (
          <>
            <input
              className="input"
              placeholder={PLACEHOLDER[mode]}
              value={idText}
              onChange={(e) => setIdText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && apply()}
            />
            <button className="btn" onClick={apply}>Go</button>
          </>
        )}
      </header>

      <main className="container">{panel}</main>
    </>
  )
}
