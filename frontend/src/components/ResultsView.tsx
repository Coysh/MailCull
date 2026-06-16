import React from 'react';
import { C, CAT_COLORS } from './tokens';
import { useStore } from '../store';
import type { ActionResult, Status } from '../types';

const STATUS_META: Record<Status, [string, string, string]> = {
  unsubscribed: ['Unsubscribed', C.teal,      '#0E2925'],
  muted:        ['Muted',        '#C3C8D0',   '#1B1E23'],
  archived:     ['Archived',     C.cyan,      '#0E2429'],
  deleted:      ['Deleted',      C.redBright, '#2A1416'],
  kept:         ['Kept',         C.green,     '#0F2417'],
  needs_link:   ['Needs link',   C.amber,     '#221E0C'],
  failed:       ['Failed',       C.redBright, '#2A1416'],
  transactional:['Tagged',       C.blue,      '#0F1B33'],
  snoozed:      ['Snoozed',      C.amber,     '#221E0C'],
  pending:      ['Pending',      C.textFaint, '#1B1E23'],
};

export function ResultsView() {
  const { state, dispatch } = useStore();
  const results = state.lastResults;

  const counts: Record<string, number> = {};
  results.forEach(r => { counts[r.status] = (counts[r.status] ?? 0) + 1; });

  const needsLink = results.filter(r => r.status === 'needs_link');
  const failures  = results.filter(r => r.status === 'failed');

  const now = new Date().toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
  const subtitle = `${results.length} actions · ${now}${state.dryRun ? ' · DRY RUN' : ''}`;

  const statEntries: [string, string][] = [
    ['unsubscribed', 'unsubscribed'],
    ['muted',        'muted'],
    ['archived',     'archived'],
    ['deleted',      'deleted'],
    ['kept',         'kept'],
    ['needs_link',   'needs link'],
    ['failed',       'failed'],
  ];

  return (
    <div style={{ overflow: 'auto', padding: '22px 24px' }}>
      <div style={{ maxWidth: 880 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <div style={{ width: 30, height: 30, borderRadius: '50%', background: C.tealBg, border: `1px solid ${C.tealBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 14 14" fill="none" stroke={C.tealBright} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7.2 L5.6 9.8 L11 4" />
              </svg>
            </div>
            <div>
              <h1 style={{ fontSize: 16, fontWeight: 600, marginBottom: 2 }}>Batch executed</h1>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textFaint }}>{subtitle}</div>
            </div>
          </div>
          <button
            onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'review' })}
            style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '6px 12px', borderRadius: 2, cursor: 'pointer' }}
            onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.borderHov; b.style.color = C.text; }}
            onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textMuted; }}
          >Back to review</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 8, marginBottom: 16 }}>
          {statEntries.map(([key, label]) => {
            const [, color] = STATUS_META[key as Status] ?? ['', C.textFaint, ''];
            return (
              <div key={key} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2, padding: '10px 11px' }}>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>{counts[key] ?? 0}</div>
                <div style={{ fontSize: 10, color: C.textFaint }}>{label}</div>
              </div>
            );
          })}
        </div>

        {failures.length > 0 && (
          <div style={{ background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, marginBottom: 14, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 13px', background: '#231114', borderBottom: `1px solid #3A1A1D` }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: C.redBright }}>FAILED</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.redBright, background: '#3A1A1D', padding: '0 6px', borderRadius: 9 }}>{failures.length}</span>
              <span style={{ fontSize: 11, color: '#9C6266', marginLeft: 'auto' }}>Network or API errors — safe to retry</span>
            </div>
            {failures.map(f => (
              <div key={f.sender_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', alignItems: 'center', gap: 12, padding: '8px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                <div>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{f.from_name}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, marginLeft: 8 }}>{f.error}</span>
                </div>
                <span style={{ fontSize: 10, color: C.textFaint }}>{f.method}</span>
                <button style={{ background: 'transparent', border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 11, padding: '3px 10px', borderRadius: 2, cursor: 'pointer' }}>Retry</button>
              </div>
            ))}
          </div>
        )}

        {needsLink.length > 0 && (
          <div style={{ background: C.panel, border: `1px solid ${C.amberBorder}`, borderRadius: 3, marginBottom: 14, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '10px 13px', background: '#1E1B0C', borderBottom: `1px solid #3A350F` }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: C.amber }}>NEEDS LINK · MANUAL STEP</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.amber, background: '#322B0F', padding: '0 6px', borderRadius: 9 }}>
                {needsLink.filter(n => state.needsLinkDoneIds.has(n.sender_id)).length}/{needsLink.length}
              </span>
              <span style={{ fontSize: 11, color: C.amberDim, marginLeft: 'auto' }}>Open each link, complete the flow, mark done</span>
            </div>
            {needsLink.map(n => {
              const done = state.needsLinkDoneIds.has(n.sender_id);
              return (
                <div key={n.sender_id} style={{ display: 'grid', gridTemplateColumns: '24px 1fr auto auto', alignItems: 'center', gap: 11, padding: '9px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                  <span style={{ width: 18, height: 18, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: done ? C.bg : C.textFaint, background: done ? C.teal : 'transparent', border: done ? 'none' : `1px solid #3A3F47` }}>
                    {done ? '✓' : ''}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: done ? '#6E7682' : C.text }}>{n.from_name}</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n.detail}</div>
                  </div>
                  <button
                    onClick={() => n.link && window.open(n.link, '_blank', 'noopener,noreferrer')}
                    disabled={!n.link}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'transparent', border: `1px solid ${n.link ? C.border : C.borderDark}`, color: n.link ? C.textMuted : C.textFaint, fontSize: 11, padding: '4px 10px', borderRadius: 2, cursor: n.link ? 'pointer' : 'default' }}
                  >
                    <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"><path d="M5.5 2.5H2.5v9h9v-3" /><path d="M8 2.5h3.5V6M11.5 2.5L6.5 7.5" /></svg>
                    Open
                  </button>
                  <button
                    onClick={() => dispatch({ type: 'TOGGLE_NEEDS_LINK_DONE', id: n.sender_id })}
                    style={{ background: done ? '#0E2925' : 'transparent', border: `1px solid ${done ? C.tealBorder : C.border}`, color: done ? C.teal : C.textMuted, fontSize: 11, padding: '4px 10px', borderRadius: 2, cursor: 'pointer' }}
                  >{done ? 'Done ✓' : 'Mark done'}</button>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ padding: '9px 13px', borderBottom: `1px solid ${C.borderSub}` }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: '.06em', color: C.textDim }}>PER-SENDER OUTCOMES</span>
          </div>
          {results.map(r => {
            const [label, color, bg] = STATUS_META[r.status] ?? ['Unknown', C.textFaint, C.panel2];
            return (
              <div key={r.sender_id} style={{ display: 'grid', gridTemplateColumns: '1fr 150px 120px 70px', alignItems: 'center', padding: '8px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{r.from_name}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.from_address}</span>
                </div>
                <div style={{ fontSize: 11, color: C.textFaint }}>{r.detail}</div>
                <div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 2, background: bg, color }}>
                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: color }} />
                    {label}
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  {r.can_undo && (
                    <button style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textFaint, fontSize: 11, padding: '2px 9px', borderRadius: 2, cursor: 'pointer' }}>Undo</button>
                  )}
                </div>
              </div>
            );
          })}
          {results.length === 0 && (
            <div style={{ padding: '40px', textAlign: 'center', color: C.textFaint }}>No results yet — execute a batch from Confirm.</div>
          )}
        </div>
      </div>
    </div>
  );
}
