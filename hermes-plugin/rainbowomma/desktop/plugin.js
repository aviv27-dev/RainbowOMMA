// RainbowOMMA — the Desktop half: one pane that shows who holds what on the shared Mac, and the human's stop button.
// Plain disk-plugin ESM (no JSX, no build). Only the plugin SDK is used: the data is the plugin's own slash command,
// `/rainbow json`, run through the gateway JSON-RPC door (host.request → command.dispatch); pause and resume are
// `/rainbow pause` and `/rainbow resume` through the same door. No network, no files, no app markup.
import { host, atom, useValue, useQuery, queryClient, Button, Badge, EmptyState, ErrorState, Skeleton, StatusDot,
  PANES_AREA, PALETTE_AREA } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'rainbowomma'
const PANE = 'pane'
const REFRESH_MS = 10000
const SWATCH = /^#[0-9a-fA-F]{6}$/

// ---- the Python half ----------------------------------------------------------------------------------------------
async function rainbow(arg) {
  // the focused session (when there is one) binds the command to that chat's profile; without one the gateway runs it
  // for the active profile
  const res = await host.request('command.dispatch', { name: 'rainbow', arg, session_id: host.state.focusedSessionId.get() || '' })
  return String((res && (res.output ?? (res.result && res.result.output))) ?? '').trim()
}

async function readSnapshot() {
  const text = await rainbow('json')
  if (text[0] !== '{') return { notice: text || 'The rainbowomma plugin did not answer.' }   // e.g. not macOS
  const snap = JSON.parse(text)
  if (snap.error) throw new Error(String(snap.error))
  return snap
}

// ---- small pieces -------------------------------------------------------------------------------------------------
const el = (tag, style, children, props, key) => jsxs(tag, { style, ...props, children: [].concat(children) }, key)
const muted = { color: 'var(--ui-text-tertiary)' }
const soft = { color: 'var(--ui-text-secondary)' }
const line = { display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', minWidth: 0 }
const box = { border: '1px solid var(--ui-stroke-secondary)', borderRadius: '6px', padding: '8px 10px' }
const baseName = path => String(path ?? '').split(/[\\/]/).pop() || '—'
const who = v => (v && typeof v === 'object' ? v.agent : v) || 'unknown'

function clock(until) {
  const n = Number(until)
  if (Number.isNaN(n)) return String(until).slice(0, 40)        // already a readable time
  if (!n) return ''
  const d = new Date(n < 1e11 ? n * 1000 : n)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

function browserState(a) {
  if (a.closedByHuman) return { tone: 'warn', text: 'closed by the human' }
  if (a.browser === 'up') return { tone: 'good', text: 'up' }
  if (a.browser === 'down') return { tone: 'muted', text: 'down' }
  return { tone: a.browser === 'unknown' ? 'muted' : 'bad', text: String(a.browser || 'unknown') }
}

function Label({ children }) {
  return jsx('span', { className: 'text-xs', style: { ...muted, flex: '0 0 auto', minWidth: '64px' }, children })
}

function Chip({ children, title }) {
  return jsx(Badge, { variant: 'outline', title, style: { maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }, children })
}

function Row({ label, children }) {
  return el('div', { ...line, alignItems: 'baseline' }, [jsx(Label, { children: label }, 'l'),
    el('div', { ...line, flex: '1 1 0' }, children, null, 'v')])
}

function AgentCard({ agent }) {
  const state = browserState(agent)
  const ports = agent.ports || []
  const docs = agent.documents || []
  // the one colour that is not a theme token: the agent's own frame colour, straight from the registry
  const swatch = SWATCH.test(agent.color || '') ? agent.color : 'var(--ui-text-quaternary)'
  return el('li', { ...box, display: 'flex', gap: '10px', listStyle: 'none', ...(agent.me ? { borderColor: 'var(--ui-accent)' } : null) }, [
    jsx('span', { 'aria-hidden': true, title: agent.colorName || undefined, style: {
      flex: '0 0 auto', width: '6px', alignSelf: 'stretch', borderRadius: '3px', background: swatch } }, 'swatch'),
    el('div', { display: 'flex', flexDirection: 'column', gap: '4px', flex: '1 1 0', minWidth: 0 }, [
      el('div', line, [
        jsx('span', { className: 'text-sm font-medium', style: { overflow: 'hidden', textOverflow: 'ellipsis' },
          children: agent.label || agent.agent || 'agent' }, 'name'),
        agent.me ? jsx(Badge, { children: 'you' }, 'me') : null,
        agent.colorName ? jsx('span', { className: 'text-xs', style: muted, children: agent.colorName }, 'colour') : null,
      ], null, 'head'),
      jsx(Row, { label: 'Browser', children: [
        jsx(StatusDot, { tone: state.tone }, 'dot'),
        jsx('span', { className: 'text-xs', style: soft, children: state.text }, 'state'),
        agent.cdpPort ? jsx('span', { className: 'text-xs', style: muted, children: `CDP ${agent.cdpPort}` }, 'cdp') : null,
      ] }, 'browser'),
      jsx(Row, { label: 'Ports', children: [
        ...ports.map((p, i) => jsx(Chip, { children: p.name ? `${p.port} · ${p.name}` : String(p.port) }, `p${i}`)),
        ports.length ? null : jsx('span', { className: 'text-xs', style: muted, children: 'none leased' }, 'none'),
        agent.portRange ? jsx('span', { className: 'text-xs', style: muted,
          children: `range ${Array.isArray(agent.portRange) ? agent.portRange.join('–') : agent.portRange}` }, 'range') : null,
      ] }, 'ports'),
      docs.length ? jsx(Row, { label: 'Documents', children:
        docs.map((d, i) => jsx(Chip, { children: baseName(d) }, `d${i}`)) }, 'docs') : null,
    ], null, 'body'),
  ])
}

function Fact({ label, children }) {
  return el('div', { ...line, alignItems: 'baseline', padding: '2px 0' }, [jsx(Label, { children: label }, 'l'),
    el('div', { ...line, flex: '1 1 0' }, children, null, 'v')], { className: 'text-xs' })
}

function PausedBanner({ busy, onResume }) {
  return el('div', { ...box, ...line, justifyContent: 'space-between', borderColor: 'var(--ui-accent)',
    background: 'color-mix(in srgb, var(--ui-accent) 14%, transparent)' }, [
    el('div', { display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }, [
      jsx('strong', { className: 'text-sm', children: 'All agents are paused' }, 't'),
      jsx('span', { className: 'text-xs', style: soft, children: 'Every tool call is refused until you resume.' }, 'd'),
    ], null, 'copy'),
    jsx(Button, { type: 'button', size: 'sm', disabled: busy, onClick: onResume, children: 'Resume' }, 'resume'),
  ], { role: 'status', 'aria-live': 'polite' })
}

function Snapshot({ snap }) {
  const agents = snap.agents || []
  const screen = snap.screen || {}
  const logins = Object.entries(snap.logins || {})
  const apps = Object.entries(snap.apps || {})
  const errors = (snap.errors || []).filter(Boolean)
  const until = clock(screen.until)
  return el('div', { display: 'flex', flexDirection: 'column', gap: '10px' }, [
    agents.length
      ? jsx('ul', { style: { display: 'flex', flexDirection: 'column', gap: '6px', margin: 0, padding: 0 },
        children: agents.map((a, i) => jsx(AgentCard, { agent: a }, a.agent || i)) }, 'agents')
      : jsx(EmptyState, { className: 'min-h-24', title: 'No agents yet',
        description: 'An agent appears here once a Hermes profile with RainbowOMMA starts a session.' }, 'empty'),
    el('div', box, [
      jsx(Fact, { label: 'Screen', children: screen.holder
        ? [jsx(StatusDot, { tone: 'warn' }, 'dot'), jsx('span', { style: soft,
          children: `held by ${screen.holder}${until ? ` until ${until}` : ''}` }, 'who')]
        : [jsx(StatusDot, { tone: 'muted' }, 'dot'), jsx('span', { style: muted, children: 'free' }, 'free')] }, 'screen'),
      jsx(Fact, { label: 'Sign-ins', children: logins.length
        ? logins.map(([site, v]) => jsx(Chip, { children: `${site} · ${who(v)}` }, site))
        : jsx('span', { style: muted, children: 'none held' }, 'none') }, 'logins'),
      jsx(Fact, { label: 'Apps', children: apps.length
        ? apps.map(([name, by]) => jsx(Chip, { title: 'Launched by an agent', children: `${name} · ${who(by)}` }, name))
        : jsx('span', { style: muted, children: 'none launched by an agent' }, 'none') }, 'apps'),
    ], null, 'shared'),
    errors.length ? el('div', { ...box, display: 'flex', flexDirection: 'column', gap: '4px' }, [
      jsx(Badge, { variant: 'warn', children: 'Some owners did not answer' }, 'head'),
      ...errors.map((e, i) => jsx('span', { className: 'text-xs', style: { ...soft, overflowWrap: 'anywhere' }, children: String(e) }, i)),
    ], { role: 'alert' }, 'errors') : null,
  ])
}

// ---- the plugin ---------------------------------------------------------------------------------------------------
export default {
  id: ID,
  name: 'RainbowOMMA',
  register(ctx) {
    const cache = [ID, ctx.source]
    const refresh = () => queryClient.invalidateQueries({ queryKey: cache })
    // true while the pane is its zone's front tab; older Desktops have no such signal and poll while mounted
    const visible = typeof host.paneVisibility === 'function' ? host.paneVisibility(`${ID}:${PANE}`) : atom(true)

    async function setPaused(paused) {
      try {
        const said = await rainbow(paused ? 'pause' : 'resume')
        host.notify({ kind: 'info', message: said || (paused ? 'Pause requested.' : 'Resume requested.') })
      } catch (error) {
        host.notifyError(error, paused ? 'RainbowOMMA could not pause the agents.' : 'RainbowOMMA could not resume the agents.')
      }
      await refresh()
    }

    function RainbowPane() {
      const profile = useValue(host.state.profile) || 'default'
      const onScreen = useValue(visible)
      const [busy, setBusy] = useState(false)
      const query = useQuery({
        queryKey: [...cache, profile],
        queryFn: readSnapshot,
        retry: false,
        // only while the pane is on screen; React Query also holds the timer while the window is in the background
        refetchInterval: onScreen ? REFRESH_MS : false,
      })
      const snap = query.data
      const act = async paused => {
        setBusy(true)
        try { await setPaused(paused) } finally { setBusy(false) }
      }
      const ready = snap && !snap.notice

      let body
      if (query.isPending) {
        body = el('div', { display: 'flex', flexDirection: 'column', gap: '6px' }, [
          jsx(Skeleton, { className: 'h-16 w-full' }, 'a'), jsx(Skeleton, { className: 'h-16 w-full' }, 'b')],
        { role: 'status', 'aria-label': 'Loading RainbowOMMA' })
      } else if (query.isError && !snap) {
        body = jsx('div', { role: 'alert', children: jsx(ErrorState, {
          title: 'RainbowOMMA is unavailable',
          description: `${String((query.error && query.error.message) || query.error || 'No answer')}. `
            + 'Enable the rainbowomma plugin for this profile and check the gateway connection.',
          children: jsx(Button, { type: 'button', variant: 'outline', onClick: () => void query.refetch(), children: 'Retry' }),
        }) })
      } else if (snap.notice) {
        body = jsx(EmptyState, { title: 'Nothing to show', description: snap.notice })
      } else {
        body = jsx(Snapshot, { snap })
      }

      return el('div', { display: 'flex', flexDirection: 'column', gap: '10px', height: '100%', overflow: 'auto', padding: '12px' }, [
        el('div', { ...line, justifyContent: 'space-between' }, [
          el('div', { display: 'flex', flexDirection: 'column', minWidth: 0 }, [
            jsx('span', { className: 'text-sm font-medium', children: 'RainbowOMMA' }, 't'),
            jsx('span', { className: 'text-xs', style: muted, children: ready && snap.me ? `you are ${snap.me}` : 'who holds what' }, 's'),
          ], null, 'title'),
          el('div', line, [
            jsx(Button, { type: 'button', variant: 'ghost', size: 'sm', disabled: query.isFetching,
              onClick: () => void query.refetch(), children: query.isFetching ? 'Refreshing…' : 'Refresh' }, 'refresh'),
            ready && !snap.paused ? jsx(Button, { type: 'button', variant: 'outline', size: 'sm', disabled: busy,
              title: 'Every agent on this Mac stops: tool calls are refused until you resume',
              onClick: () => void act(true), children: 'Pause all' }, 'pause') : null,
          ], null, 'actions'),
        ], null, 'header'),
        ready && snap.paused ? jsx(PausedBanner, { busy, onResume: () => void act(false) }, 'paused') : null,
        jsx('div', { children: body }, 'body'),
        query.isError && snap ? jsx('span', { className: 'text-xs', style: muted, role: 'alert',
          children: 'The last refresh failed; showing the previous picture.' }, 'stale') : null,
        ready ? jsx('span', { className: 'text-xs', style: muted, children:
          `Updated ${clock(query.dataUpdatedAt)} · refreshes every ${REFRESH_MS / 1000} s while this pane is on screen` }, 'foot') : null,
      ], { className: 'text-(--ui-text-primary)' })
    }

    ctx.onDispose(() => {
      void queryClient.cancelQueries({ queryKey: cache })
      queryClient.removeQueries({ queryKey: cache })
    })
    ctx.registerMany([
      { id: PANE, area: PANES_AREA, title: 'RainbowOMMA', data: { placement: 'right', width: '320px' }, render: () => jsx(RainbowPane, {}) },
      { id: 'pause', area: PALETTE_AREA, data: { id: `${ID}.pause`, label: 'RainbowOMMA: Pause all agents',
        keywords: ['rainbow', 'pause', 'stop', 'agents'], run: () => void setPaused(true) } },
      { id: 'resume', area: PALETTE_AREA, data: { id: `${ID}.resume`, label: 'RainbowOMMA: Resume agents',
        keywords: ['rainbow', 'resume', 'agents'], run: () => void setPaused(false) } },
    ])
  },
}
