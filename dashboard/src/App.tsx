// App shell (P6 revision): PRX-centric, click-through routing — no ID inputs.
import { useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router-dom'
import { getLive, type Live } from './lib/api'
import { HomePage } from './pages/HomePage'
import { MatchPage } from './pages/MatchPage'
import { PlayerPage } from './pages/PlayerPage'

export default function App() {
  const live = useQuery<Live>({ queryKey: ['live'], queryFn: getLive })
  const isLive = live.data?.mode === 'live'
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand"><h1>PRX PREDICTOR</h1></Link>
        <span className={`mode-pill ${isLive ? 'live' : ''}`}>
          {live.isLoading ? 'detecting…' : isLive ? 'live' : 'no live match'}
        </span>
        <div className="spacer" />
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/match/:id" element={<MatchPage />} />
          <Route path="/player/:id" element={<PlayerPage />} />
        </Routes>
      </main>
    </>
  )
}
