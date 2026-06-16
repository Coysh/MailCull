import React, { useState } from 'react';
import { C, CAT_COLORS, CAP_COLORS, CAP_LABELS } from './tokens';
import { useStore } from '../store';
import * as api from '../api';
import type { Sender } from '../types';

export function ConfirmView() {
  const { state, dispatch, decided } = useStore();
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });

  const gUnsub = decided.filter(s => s.decision === 'unsubscribe');
  const gMute  = decided.filter(s => s.decision === 'mute');
  const gArchive = decided.filter(s => s.decision === 'archive');
  const gDelete = decided.filter(s => s.decision === 'delete');
  const cKeep  = decided.filter(s => s.decision === 'keep').length;
  const cTrans = decided.filter(s => s.decision === 'transactional').length;
  const delMsgs = gDelete.reduce((a, s) => a + s.message_count, 0);

  const method = (s: Sender): [string, string] => {
    if (s.capability === 'one_click') return ['one-click POST', C.green];
    if (s.capability === 'link') return ['opens link', C.amber];
    if (s.capability === 'mailto') return ['mailto sent', C.blue];
    return ['no method', C.textFaint];
  };

  const handleExecute = async () => {
    const total = decided.length;
    setExecuting(true);
    setProgress({ done: 0, total });
    const allResults: import('../types').ActionResult[] = [];
    try {
      for (const sender of decided) {
        const results = await api.postExecute([sender.id]);
        allResults.push(...results);
        setProgress(p => ({ ...p, done: p.done + 1 }));
      }
      const executedIds = decided.map(s => s.id);
      dispatch({ type: 'SET_RESULTS', results: allResults });
      dispatch({ type: 'REMOVE_SENDERS', ids: executedIds });
      dispatch({ type: 'SET_SCREEN', screen: 'results' });
    } catch (err) {
      console.error(err);
      setExecuting(false);
    }
  };

  const deleteMode = state.settings.deleteMode === 'permanent' ? 'Permanent delete · irreversible' : 'Move to Trash · recoverable 30 days';
  const muteMode = state.settings.muteAction === 'trash' ? 'Move to Trash (future mail)' : 'Skip inbox (archive) · keeps future mail out';
  const destructiveWarning = [
    gDelete.length ? `${gDelete.length} sender${gDelete.length !== 1 ? 's' : ''} → ${delMsgs.toLocaleString()} messages moved to Trash.` : '',
    gArchive.length ? `${gArchive.length} sender${gArchive.length !== 1 ? 's' : ''} archived (removable from All Mail).` : '',
    gUnsub.length ? `${gUnsub.length} unsubscribe request${gUnsub.length !== 1 ? 's' : ''} sent.` : '',
    'These run against the live mailbox immediately.',
  ].filter(Boolean).join(' ');

  return (
    <div style={{ overflow: 'auto', padding: '22px 24px' }}>
      <div style={{ maxWidth: 840 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 6 }}>
          <div>
            <h1 style={{ fontSize: 16, fontWeight: 600, marginBottom: 3 }}>Confirm batch · {decided.length} actions</h1>
            <div style={{ fontSize: 12, color: C.textFaint }}>Review exactly what runs against the live mailbox before executing.</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn label="← Back" onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'review' })} disabled={executing} />
            <button onClick={handleExecute} disabled={executing}
              style={{ background: executing ? C.panel2 : C.tealBg, border: `1px solid ${executing ? C.border : C.tealBorder}`, color: executing ? C.textFaint : C.tealBright, fontSize: 12, fontWeight: 600, padding: '7px 15px', borderRadius: 2, cursor: executing ? 'not-allowed' : 'pointer' }}
              onMouseEnter={e => { if (!executing) { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealHov; b.style.borderColor = C.teal; } }}
              onMouseLeave={e => { if (!executing) { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealBg; b.style.borderColor = C.tealBorder; } }}
            >{executing ? `Executing ${progress.done} / ${progress.total}…` : `Execute ${decided.length} actions`}</button>
          </div>
        </div>

        {executing && (
          <div style={{ margin: '14px 0 6px' }}>
            <div style={{ height: 3, background: C.panel2, borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', background: C.teal, width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%`, transition: 'width 0.25s ease' }} />
            </div>
            <div style={{ fontSize: 11, color: C.textFaint, marginTop: 5 }}>{progress.done} of {progress.total} complete</div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, margin: '16px 0' }}>
          <StatCard count={gUnsub.length} label="unsubscribe" color={C.amber} />
          <StatCard count={gMute.length} label="mute" color="#C3C8D0" />
          <StatCard count={gArchive.length} label="archive" color={C.cyan} />
          <StatCard count={gDelete.length} label="delete" color={C.redBright} />
          <StatCard count={cKeep} label="keep" color={C.green} />
          <StatCard count={cTrans} label="transactional" color={C.blue} />
        </div>

        {gUnsub.length > 0 && (
          <GroupBlock title="UNSUBSCRIBE" count={gUnsub.length} headerBg="#1E1B0C" border={C.amberBorder} headerText={C.amber} subtitle="Sends opt-out via header, link, or mailto">
            {gUnsub.map(s => {
              const [m, mc] = method(s);
              return (
                <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', alignItems: 'center', gap: 12, padding: '7px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{s.from_name}</span>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.from_address}</span>
                  </div>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint, fontVariantNumeric: 'tabular-nums' }}>{s.message_count.toLocaleString()} msgs</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: CAP_COLORS[s.capability as string]?.[0] }}>{CAP_LABELS[s.capability]}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: mc, minWidth: 120, textAlign: 'right' }}>{m}</span>
                </div>
              );
            })}
          </GroupBlock>
        )}

        {gDelete.length > 0 && (
          <GroupBlock title="DELETE EXISTING MAIL" count={gDelete.length} headerBg="#231114" border={C.redBorder} headerText={C.redBright} subtitle={deleteMode} icon>
            {gDelete.map(s => {
              const [cc, cb] = CAT_COLORS[s.category ?? 'Marketing'] ?? [C.textMuted, C.panel2];
              return (
                <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', alignItems: 'center', gap: 12, padding: '7px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{s.from_name}</span>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>{s.from_address}</span>
                  </div>
                  <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: cb, color: cc }}>{s.category}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.redBright, fontVariantNumeric: 'tabular-nums' }}>{s.message_count.toLocaleString()} → Trash</span>
                </div>
              );
            })}
          </GroupBlock>
        )}

        {gArchive.length > 0 && (
          <GroupBlock title="ARCHIVE EXISTING MAIL" count={gArchive.length} headerBg={C.cyanBg} border='#1E5A6A' headerText={C.cyan} subtitle="Removes INBOX label — moves to All Mail, fully recoverable">
            {gArchive.map(s => (
              <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: 12, padding: '7px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{s.from_name}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>{s.from_address}</span>
                </div>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.cyan, fontVariantNumeric: 'tabular-nums' }}>{s.message_count.toLocaleString()} → All Mail</span>
              </div>
            ))}
          </GroupBlock>
        )}

        {gMute.length > 0 && (
          <GroupBlock title="MUTE · CREATE FILTER" count={gMute.length} headerBg={C.panel2} border={C.border} headerText="#C3C8D0" subtitle={muteMode}>
            {gMute.map(s => (
              <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: 12, padding: '7px 13px', borderBottom: `1px solid ${C.borderDark}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{s.from_name}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>{s.from_address}</span>
                </div>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint }}>filter: from:{s.domain}</span>
              </div>
            ))}
          </GroupBlock>
        )}

        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, background: C.redBg, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '11px 13px', marginTop: 14 }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={C.red} strokeWidth="1.3" strokeLinecap="round" style={{ marginTop: 1, flexShrink: 0 }}>
            <path d="M7 1.8 L12.8 12 L1.2 12 Z" /><line x1="7" y1="5.3" x2="7" y2="8.4" /><circle cx="7" cy="10.2" r=".55" fill={C.red} />
          </svg>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.redBright, marginBottom: 2 }}>Destructive actions</div>
            <div style={{ fontSize: 11, color: C.redText, lineHeight: 1.55 }}>{destructiveWarning}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ count, label, color }: { count: number; label: string; color: string }) {
  return (
    <div style={{ background: '#15171B', border: `1px solid ${C.border}`, borderRadius: 2, padding: '9px 11px' }}>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}>{count}</div>
      <div style={{ fontSize: 10, color: C.textFaint }}>{label}</div>
    </div>
  );
}

function GroupBlock({ title, count, headerBg, border, headerText, subtitle, icon, children }: {
  title: string; count: number; headerBg: string; border: string; headerText: string; subtitle: string; icon?: boolean; children: React.ReactNode;
}) {
  return (
    <div style={{ background: '#15171B', border: `1px solid ${border}`, borderRadius: 3, marginBottom: 11, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 13px', background: headerBg, borderBottom: `1px solid ${border}` }}>
        {icon && (
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke={headerText} strokeWidth="1.3" strokeLinecap="round">
            <path d="M2.5 3.5h9M5 3.5V2.3h4V3.5M3.4 3.5l.6 8h6l.6-8" />
          </svg>
        )}
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.04em', color: headerText }}>{title}</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: headerText, background: 'rgba(0,0,0,.3)', padding: '0 6px', borderRadius: 9 }}>{count}</span>
        <span style={{ fontSize: 11, color: C.textFaint, marginLeft: 'auto' }}>{subtitle}</span>
      </div>
      {children}
    </div>
  );
}

function Btn({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{ background: 'transparent', border: `1px solid ${C.border}`, color: disabled ? C.textFaint : C.textMuted, fontSize: 12, padding: '7px 13px', borderRadius: 2, cursor: disabled ? 'not-allowed' : 'pointer' }}
      onMouseEnter={e => { if (!disabled) { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.borderHov; b.style.color = C.text; } }}
      onMouseLeave={e => { if (!disabled) { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textMuted; } }}
    >{label}</button>
  );
}
