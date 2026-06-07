// Visual primitives (Phase B): agent icons, role icons, team logos, map thumbnails.
// Each degrades gracefully to text when the asset isn't in the manifest.
import { agentAsset, mapAsset, teamLogo } from '../lib/assets'

export function AgentIcon({ agent, size = 26 }: { agent: string; size?: number }) {
  const a = agentAsset(agent)
  if (!a?.icon) return <span className="agent-fallback" title={agent} style={{ width: size, height: size }}>{agent.slice(0, 2)}</span>
  return <img className="agent-icon" src={a.icon} alt={agent} title={agent} width={size} height={size} loading="lazy" />
}

export function RoleIcon({ agent, size = 14 }: { agent: string; size?: number }) {
  const a = agentAsset(agent)
  if (!a?.roleIcon) return null
  return <img className="role-icon" src={a.roleIcon} alt={a.role ?? ''} title={a.role ?? ''} width={size} height={size} loading="lazy" />
}

export function RoleName({ role, size = 13 }: { role: string; size?: number }) {
  // Role emblem by role name (any agent of that role carries the same emblem).
  const a = ['Jett', 'Omen', 'Sova', 'Killjoy'].map(agentAsset).find((x) => x?.role === role)
  return (
    <span className="role-name">
      {a?.roleIcon && <img className="role-icon" src={a.roleIcon} alt="" width={size} height={size} loading="lazy" />}
      {role}
    </span>
  )
}

export function TeamLogo({ url, name, size = 30 }: { url?: string | null; name?: string | null; size?: number }) {
  const src = teamLogo(url)
  if (!src) return null
  return <img className="team-logo" src={src} alt={name ?? ''} width={size} height={size} loading="lazy" />
}

export function MapThumb({ map, h = 34 }: { map: string; h?: number }) {
  const m = mapAsset(map)
  const src = m?.listView || m?.minimap
  if (!src) return null
  return <img className="map-thumb" src={src} alt={map} title={map} height={h} loading="lazy" />
}

export function Comp({ comp, size = 26 }: { comp: string[]; size?: number }) {
  return (
    <span className="comp-row">
      {comp.map((a, i) => <AgentIcon key={`${a}-${i}`} agent={a} size={size} />)}
    </span>
  )
}
