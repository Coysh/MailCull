import React, { useState } from 'react';
import { C, STATUS_META } from './tokens';
import { useStore } from '../store';
import * as api from '../api';
import type { ActionResult } from '../types';

export function ResultsView() {
  const { state, dispatch, reloadSenders } = useStore();
  const results = state.lastResults;
  const [busy, setBusy] = useState<Set<string>>(new Set());

  const ran = results.filter(r => !r.skipped);
  const skipped = results.filter(r => r.skipped);
  const counts: Record<string, number> = {};
  ran.forEach(r => { counts[r.status] = (counts[r.status] ?? 0) + 1; });

  const needsLink = ran.filter(r => r.status === 'needs_link' || (r.status === 'unsubscribed' && r.method === 'manual'));
  const failures  = ran.filter(r => r.status === 'failed');

  const now = new Date().toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
  const subtitle = `${ran.length} actions${skipped.length ? ` · ${skipped.length} already done` : ''} · ${now}${state.dryRun ? ' · DRY RUN' : ''}`;

  const statEntries: [string, string][] = [
    ['unsubscribed',  'unsubscribed'],
    ['unsub_pending', 'verifying'],
    ['muted',         'muted'],
    ['archived',      'archived'],
    ['deleted',       'deleted'],
    ['needs_link',    'needs link'],
    ['failed',        'failed'],
  ];

  const withBusy = async (id: string, fn: () => Promise<void>) => {
    setBusy(b => new Set(b).add(id));
    try { await fn(); } catch (err) { console.error(err); alert(String(err)); }
    finally { setBusy(b => { const n = new Set(b); n.delete(id); return n; }); }
  };

  const retry = (r: ActionResult) => withBusy(r.sender_id, async () => {
    const [fresh] = await api.postExecute([r.sender_id], {
      force: true, mute_action: state.settings.muteAction, snooze_days: state.settings.snoozeDays,
    });
    if (fresh) dispatch({ type: 'UPDATE_RESULT', senderId: r.sender_id, patch: fresh });
    reloadSenders();
  });

  const undo = (r: ActionResult) => withBusy(r.sender_id, async () => {
    if (r.action_id == null) return;
    const res = await api.postUndo(r.action_id);
    dispatch({ type: 'UPDATE_RESULT', senderId: r.sender_id, patch: { status: 'pending', detail: `undone — ${res.detail}`, can_undo: false } });
    reloadSenders();
  });

  const markDone = (r: ActionResult) => withBusy(r.sender_id, async () => {
    await api.postManualDone(r.sender_id);
    dispatch({ type: 'UPDATE_RESULT', senderId: r.sender_id, patch: { status: 'unsubscribed', method: 'manual', detail: 'marked done by you' } });
    reloadSenders();
  });

  return (
    <div style={{ overflow: 'auto', padding: '22px 24px' }}>
      <div style={{ maxWidth: 920 }}>
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

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 8, marginBottom: 16 }}>
          {statEntries.map(([key, label]) => {
            const [, color] = STATUS_META[key] ?? ['', C.textFaint, ''];
            return (
              <div key={key} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2, padding: '10px 11px' }}>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>{counts[key] ?? 0}</div>
                <div style={{ fontSize: 10, color: C.textFaint }}>{label}</div>
              </div>
            );
          })}
        </div>

        {(counts.unsub_pending ?? 0) > 0 && (
          <div style={{ fontSize: 11, color: C.textFaint, lineHeight: 1.55, marginBottom: 14 }}>
            <span style={{ color: C.teal, fontWeight: 600 }}>Verifying</span> — the unsubscribe form was submitted but the page didn't confirm it.
            MailCull checks on later scans. If mail keeps arriving more than {state.settings.graceDays} days later, the sender is flagged <span style={{ color: C.redBright }}>Still sending</span>.
          </div>
        )}

        {failures.length > 0 && (
          <div style={{ background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, marginBottom: 14, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 13px', background: '#231114', borderBottom: `1px solid #3A1A1D` }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: C.redBright }}>FAILED</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.redBright, background: '#3A1A1D', padding: '0 6px', borderRadius: 9 }}>{failures.length}</span>
              <span style={{ fontSize: 11, color: '#9C6266', marginLeft: 'auto' }}>If there's no unsubscribe method, Mute instead</span>
            </div>
            {failures.map(f => (
              <div key={f.sender_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: 12, padding: '8px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                <div style={{ minWidth: 0 }}>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{f.from_name}</span>
                  <Trail result={f} />
                </div>
                <button disabled={busy.has(f.sender_id)} onClick={() => retry(f)}
                  style={{ background: 'transparent', border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 11, padding: '3px 10px', borderRadius: 2, cursor: busy.has(f.sender_id) ? 'wait' : 'pointer' }}>
                  {busy.has(f.sender_id) ? 'Retrying…' : 'Retry'}
                </button>
              </div>
            ))}
          </div>
        )}

        {needsLink.length > 0 && (
          <div style={{ background: C.panel, border: `1px solid ${C.amberBorder}`, borderRadius: 3, marginBottom: 14, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '10px 13px', background: '#1E1B0C', borderBottom: `1px solid #3A350F` }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: C.amber }}>NEEDS LINK · MANUAL STEP</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.amber, background: '#322B0F', padding: '0 6px', borderRadius: 9 }}>
                {needsLink.filter(n => n.status === 'unsubscribed').length}/{needsLink.length}
              </span>
              <span style={{ fontSize: 11, color: C.amberDim, marginLeft: 'auto' }}>Automation couldn't finish these. Open each one, complete it, then mark it done.</span>
            </div>
            {needsLink.map(n => {
              const done = n.status === 'unsubscribed';
              return (
                <div key={n.sender_id} style={{ display: 'grid', gridTemplateColumns: '24px 1fr auto auto', alignItems: 'center', gap: 11, padding: '9px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                  <span style={{ width: 18, height: 18, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: done ? C.bg : C.textFaint, background: done ? C.teal : 'transparent', border: done ? 'none' : `1px solid #3A3F47` }}>
                    {done ? '✓' : ''}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: done ? C.textMono : C.text }}>{n.from_name}</div>
                    <Trail result={n} />
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
                    disabled={done || busy.has(n.sender_id)}
                    onClick={() => markDone(n)}
                    style={{ background: done ? '#0E2925' : 'transparent', border: `1px solid ${done ? C.tealBorder : C.border}`, color: done ? C.teal : C.textMuted, fontSize: 11, padding: '4px 10px', borderRadius: 2, cursor: done ? 'default' : 'pointer' }}
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
              <div key={r.sender_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 110px 70px', alignItems: 'center', gap: 10, padding: '8px 13px', borderBottom: `1px solid ${C.borderDark}`, opacity: r.skipped ? 0.55 : 1 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap' }}>{r.from_name}</span>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.from_address}</span>
                  </div>
                  <Trail result={r} />
                </div>
                <div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 2, background: bg, color }}>
                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: color }} />
                    {r.skipped ? 'Skipped' : label}
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  {r.can_undo && r.action_id != null && (
                    <button disabled={busy.has(r.sender_id)} onClick={() => undo(r)}
                      style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textFaint, fontSize: 11, padding: '2px 9px', borderRadius: 2, cursor: 'pointer' }}>
                      {busy.has(r.sender_id) ? '…' : 'Undo'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {results.length === 0 && (
            <div style={{ padding: '40px', textAlign: 'center', color: C.textFaint }}>No results yet. Execute a batch from Confirm.</div>
          )}
        </div>
      </div>
    </div>
  );
}

/** What was tried, in order, e.g. "one-click: HTTP 405 → mailto: sent to …" */
function Trail({ result: r }: { result: ActionResult }) {
  const steps = r.attempts?.length ? r.attempts : [r.detail];
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 6px', marginTop: 2 }}>
      {steps.map((step, i) => (
        <span key={i} title={step} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: i === steps.length - 1 ? C.textFaint : C.textDim, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {i > 0 && <span style={{ color: C.textGhost }}>→ </span>}{step}
        </span>
      ))}
    </div>
  );
}
