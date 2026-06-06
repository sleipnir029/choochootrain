// Typed API client (P6 revision). View-shaped endpoints: one call per screen.
// Relative URLs so the bundle works behind the dev proxy and served from FastAPI.
import axios from 'axios'

export const PRX_TEAM_ID = 624
const http = axios.create({ baseURL: '' })

// --- shared shapes ----------------------------------------------------------
export interface Insight { headline: string; points: string[]; tone: string }
export interface TeamBrief { id: number; name: string | null; logo: string | null }
export interface Factor { factor: string; weight: number; favors: 'team1' | 'team2' }
export interface MapPrediction {
  map_name: string; team1_win_prob: number; team1_win_prob_hdi: [number, number]; picked_by: number | null
}
export interface Prediction {
  team1_win_prob: number
  team1_win_prob_hdi: [number, number] | null
  series_win_prob: { team1: number; team2: number }
  map_predictions: MapPrediction[]
  top_factors: Factor[]
}
export interface ExpectedRow {
  player_id: number; handle: string; team_id: number; n_history: number
  expected_acs: number; actual_acs?: number; delta_acs?: number
  expected_kills: number; expected_deaths: number; expected_assists: number
}

// --- home -------------------------------------------------------------------
export interface RecentResult {
  match_id: number; date: string; opponent: string | null; opponent_id: number
  prx_score: number; opp_score: number; prx_won: boolean
  predicted_prx_win_prob: number; model_correct: boolean
}
export interface RosterPlayer {
  player_id: number; handle: string; real_name: string | null; country: string | null; skill: number | null
}
export type Hero =
  | { kind: 'live'; match_id: number; current_map: string | null; prx_win_prob: number | null; opponent: string | null; insight: Insight }
  | { kind: 'next'; schedule: Record<string, unknown>; prediction?: PreMatchLite; insight: Insight | null }
  | {
      kind: 'recent'; match_id: number; team1: TeamBrief; team2: TeamBrief
      team1_score: number; team2_score: number; winner_id: number | null
      prx_side: 'team1' | 'team2'; prediction: Prediction; insight: Insight | null
    }
export interface PreMatchLite extends Prediction { team1: TeamBrief; team2: TeamBrief; series_format: string }
export interface Home {
  prx: {
    team: { team_id: number; name: string; tag: string | null; region: string | null; logo_url: string | null }
    rank: { rank: number; of: number; rating: number } | null
    roster: RosterPlayer[]
  }
  hero: Hero | null
  recent: RecentResult[]
}

// --- match view -------------------------------------------------------------
export interface ReplayRound { round: number; team1_side: 'ct' | 't'; pre_round_prob_team1: number | null; winner: 'team1' | 'team2' }
export interface ReplayMap { map_index: number; map_name: string; rounds: ReplayRound[] }
export interface MatchView {
  match_id: number; completed: boolean; event: string | null; series_name: string | null; date: string; format: string
  team1: TeamBrief; team2: TeamBrief; team1_score: number; team2_score: number; winner_id: number | null
  prx_side: 'team1' | 'team2' | null
  prediction: Prediction
  prematch_insight: Insight | null
  expected_stats: ExpectedRow[]
  replay?: ReplayMap[]
  biggest_swing?: { map_name: string; round: number; delta: number } | null
  postmatch_insight?: Insight | null
}

// --- player view ------------------------------------------------------------
export interface Stint {
  team_id: number; team_name: string | null; team_tag: string | null; n_maps: number
  avg_rating: number | null; avg_acs: number | null; avg_kills: number | null
  avg_deaths: number | null; avg_assists: number | null; first_date: string; last_date: string
}
export interface FormRow { match_id: number; date: string; opponent: string | null; expected_acs: number; actual_acs: number; delta_acs: number }
export interface PlayerView {
  player_id: number; handle: string; real_name: string | null; country: string | null
  current_team_id: number | null; current_team_name: string | null; current_team_tag: string | null
  skill: { rating: number; percentile: number; rated_players: number } | null
  stints: Stint[]
  recent_form: FormRow[]
}

// --- live (for the top-bar pill) --------------------------------------------
export type Live = { mode: 'live'; [k: string]: unknown } | { mode: 'no_live'; [k: string]: unknown }

// --- calls ------------------------------------------------------------------
export const getHome = () => http.get<Home>('/api/home').then((r) => r.data)
export const getMatch = (id: number) => http.get<MatchView>(`/api/matches/${id}`).then((r) => r.data)
export const getPlayer = (id: number) => http.get<PlayerView>(`/api/players/${id}`).then((r) => r.data)
export const getLive = () => http.get<Live>('/api/predict/live').then((r) => r.data)
