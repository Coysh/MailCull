import React, { useEffect, useCallback } from 'react';
import { C, CAT_COLORS, CAP_COLORS, CAP_LABELS, DEC_LABELS } from './tokens';
import { useStore } from '../store';
import type { Sender, Decision, Capability } from '../types';
import * as api from '../api';

export function ReviewView() {
  const { state, dispatch, filtered, decided } = useStore();

  const decide = useCallback((id: string, d: Decision) => {
    dispatch({ type: 'UPDATE_SENDER_DECISION', id, decision: d });
    api.postDecisions([{ sender_id: id, decision: d }]).catch(console.error);
  }, [dispatch]);

  const bulkDecide = (d: Decision) => {
    const ids = Array.from(state.selectedIds);
    dispatch({ type: 'BULK_DECIDE', ids, decision: d });
    api.postDecisions(ids.map(id => ({ sender_id: id, decision: d }))).catch(console.error);
  };

  // Keyboard triage
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (state.showShortcuts && e.key === 'Escape') { dispatch({ type: 'TOGGLE_SHORTCUTS' }); return; }
      if (e.key === '?') { dispatch({ type: 'TOGGLE_SHORTCUTS' }); return; }
      if (state.screen !== 'review') return;
      const t = (e.target as HTMLElement).tagName;
      if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
      const cur = filtered[state.focusedIdx];
      switch (e.key) {
        case 'j': case 'ArrowDown': e.preventDefault(); dispatch({ type: 'SET_FOCUSED', idx: Math.min(state.focusedIdx + 1, filtered.length - 1) }); break;
        case 'k': case 'ArrowUp': e.preventDefault(); dispatch({ type: 'SET_FOCUSED', idx: Math.max(state.focusedIdx - 1, 0) }); break;
        case 'Enter': e.preventDefault(); if (cur) dispatch({ type: 'SET_EXPANDED', id: state.expandedId === cur.id ? null : cur.id }); break;
        case 'e': if (cur) decide(cur.id, cur.decision === 'keep' ? null : 'keep'); break;
        case 'u': if (cur) decide(cur.id, cur.decision === 'unsubscribe' ? null : 'unsubscribe'); break;
        case 'm': if (cur) decide(cur.id, cur.decision === 'mute' ? null : 'mute'); break;
        case 'a': if (cur) decide(cur.id, cur.decision === 'archive' ? null : 'archive'); break;
        case 'd': if (cur) decide(cur.id, cur.decision === 'delete' ? null : 'delete'); break;
        case 'x': if (cur) dispatch({ type: 'TOGGLE_SELECT', id: cur.id }); break;
        case 'Escape': dispatch({ type: 'SET_EXPANDED', id: null }); break;
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [state.focusedIdx, state.expandedId, state.screen, filtered, decide, dispatch]);

  const allSelected = filtered.length > 0 && filtered.every(s => state.selectedIds.has(s.id));

  const toggleSelectAll = () => {
    if (allSelected) dispatch({ type: 'DESELECT_ALL' });
    else dispatch({ type: 'SELECT_ALL', ids: filtered.map(s => s.id) });
  };

  const sortArrow = (col: string) => state.sortBy === col ? (state.sortDir === 'desc' ? '▾' : '▴') : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 14px', background: C.panel, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
          <span style={{ color: C.textFaint, fontVariantNumeric: 'tabular-nums' }}>{state.senders.length} senders</span>
          <span style={{ color: '#2D3138' }}>/</span>
          <span style={{ color: C.green, fontVariantNumeric: 'tabular-nums' }}>{decided.length} decided</span>
          <span style={{ color: '#2D3138' }}>/</span>
          <span style={{ color: C.textFaint, fontVariantNumeric: 'tabular-nums' }}>{state.senders.filter(s => !s.decision).length} pending</span>
        </div>
        <div style={{ width: 1, height: 15, background: C.border, margin: '0 3px' }} />

        <SelectEl value={state.filterCategory} onChange={v => dispatch({ type: 'SET_FILTER_CATEGORY', v })} options={[['all', 'All categories'], ['Marketing', 'Marketing'], ['Newsletter', 'Newsletter'], ['Transactional', 'Transactional'], ['Social', 'Social'], ['Spam', 'Spam'], ['Personal', 'Personal']]} />
        <SelectEl value={state.filterCapability} onChange={v => dispatch({ type: 'SET_FILTER_CAPABILITY', v })} options={[['all', 'All capabilities'], ['one_click', 'One-click'], ['link', 'Needs link'], ['mailto', 'Mailto'], ['none', 'Not possible']]} />
        <SelectEl value={state.filterDecision} onChange={v => dispatch({ type: 'SET_FILTER_DECISION', v })} options={[['all', 'All decisions'], ['undecided', 'Undecided'], ['keep', 'Keep'], ['unsubscribe', 'Unsubscribe'], ['mute', 'Mute'], ['archive', 'Archive'], ['delete', 'Delete']]} />

        <div style={{ flex: 1 }} />

        {state.selectedIds.size > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, animation: 'fadeIn .12s ease' }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted, fontVariantNumeric: 'tabular-nums' }}>{state.selectedIds.size} selected</span>
            <BulkBtn label="Keep" onClick={() => bulkDecide('keep')} hoverColor={C.green} />
            <BulkBtn label="Unsubscribe" onClick={() => bulkDecide('unsubscribe')} hoverColor={C.amber} />
            <BulkBtn label="Mute" onClick={() => bulkDecide('mute')} hoverColor={C.textMuted} />
            <BulkBtn label="Archive" onClick={() => bulkDecide('archive')} hoverColor={C.cyan} />
            <button onClick={() => bulkDecide('delete')} style={{ background: C.redBg, border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 11, fontWeight: 600, padding: '4px 9px', borderRadius: 2, cursor: 'pointer' }}>Delete</button>
            <div style={{ width: 1, height: 15, background: C.border }} />
            <button onClick={() => dispatch({ type: 'DESELECT_ALL' })} style={{ background: 'transparent', border: 'none', color: C.textDim, fontSize: 11, padding: '4px 4px', cursor: 'pointer' }}>Clear</button>
          </div>
        )}

        {decided.length > 0 && (
          <button
            onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'confirm' })}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: C.tealBg, border: `1px solid ${C.tealBorder}`, color: C.tealBright, fontSize: 12, fontWeight: 600, padding: '5px 13px', borderRadius: 2, cursor: 'pointer' }}
            onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealHov; b.style.borderColor = C.teal; }}
            onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealBg; b.style.borderColor = C.tealBorder; }}
          >Review {decided.length} actions →</button>
        )}
      </div>

      {/* Table header */}
      <div style={{ display: 'grid', gridTemplateColumns: '34px minmax(220px,1fr) 66px 78px 86px 108px 108px 96px 224px', alignItems: 'center', height: 30, background: '#101216', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} aria-label="Select all" style={{ accentColor: C.teal, width: 13, height: 13, cursor: 'pointer' }} />
        </div>
        <SortBtn label={`SENDER ${sortArrow('sender')}`} onClick={() => dispatch({ type: 'SET_SORT', by: 'sender' })} />
        <SortBtn label={`${sortArrow('count')} COUNT`} style={{ justifySelf: 'end', paddingRight: 8 }} onClick={() => dispatch({ type: 'SET_SORT', by: 'count' })} />
        <ColHdr>FREQ</ColHdr>
        <SortBtn label={`LAST ${sortArrow('last')}`} onClick={() => dispatch({ type: 'SET_SORT', by: 'last' })} />
        <ColHdr>CATEGORY</ColHdr>
        <ColHdr>CAPABILITY</ColHdr>
        <ColHdr>SUGGEST</ColHdr>
        <ColHdr>DECISION</ColHdr>
      </div>

      {/* Rows */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {filtered.map((s, i) => (
          <SenderRow key={s.id} sender={s} index={i} focused={i === state.focusedIdx} onDecide={decide} />
        ))}
        {filtered.length === 0 && !state.sendersLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', gap: 10 }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#31353D" strokeWidth="1.4" strokeLinecap="round"><circle cx="10" cy="10" r="7" /><line x1="15" y1="15" x2="21" y2="21" /></svg>
            <div style={{ fontSize: 13, color: C.textFaint }}>No senders match this filter</div>
            <button onClick={() => { dispatch({ type: 'SET_FILTER_CATEGORY', v: 'all' }); dispatch({ type: 'SET_FILTER_CAPABILITY', v: 'all' }); dispatch({ type: 'SET_FILTER_DECISION', v: 'all' }); }}
              style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '5px 12px', borderRadius: 2, cursor: 'pointer' }}>Clear filters</button>
          </div>
        )}
        {state.sendersLoading && filtered.length === 0 && (
          <div style={{ padding: '40px', textAlign: 'center', color: C.textFaint }}>Loading senders…</div>
        )}
      </div>

      {/* Keyboard footer */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '5px 14px', background: '#101216', borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: '#3C414B' }}>KEYS</span>
        {[['j/k','move'],['↵','expand'],['e','keep'],['u','unsub'],['m','mute'],['a','archive'],['d','delete'],['x','select'],['?','help']].map(([key, label]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <kbd style={{ fontSize: 10, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '0 5px', color: C.textMuted }}>{key}</kbd>
            <span style={{ fontSize: 10, color: C.textDim }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SenderRow({ sender: s, index, focused, onDecide }: { sender: Sender; index: number; focused: boolean; onDecide: (id: string, d: Decision) => void }) {
  const { state, dispatch } = useStore();
  const selected = state.selectedIds.has(s.id);
  const expanded = s.id === state.expandedId;

  const [catColor, catBg] = CAT_COLORS[s.category ?? 'Marketing'] ?? [C.textMuted, C.panel2];
  const [capColor, capBg] = CAP_COLORS[s.capability] ?? [C.textFaint, C.panel2];

  const rowBg = selected ? '#10231F' : focused ? '#12161C' : expanded ? '#101319' : 'transparent';
  const rowBorder = focused ? C.teal : selected ? C.tealBorder : 'transparent';

  const stopProp = (e: React.MouseEvent) => e.stopPropagation();
  const toggleExpand = () => dispatch({ type: 'SET_EXPANDED', id: expanded ? null : s.id });

  const btn = (action: Decision, label: string) => {
    const active = s.decision === action;
    const colors: Record<string, [string, string, string]> = {
      keep:        [C.green,    C.greenBg,  C.greenBorder],
      unsubscribe: [C.amber,    '#221E0C',  C.amberBorder],
      mute:        ['#C3C8D0',  C.panel2,   '#3A3F47'],
      archive:     [C.cyan,     C.cyanBg,   '#1E5A6A'],
      delete:      [C.redBright,C.redBg,    C.redBorder],
    };
    const [c, bg, bd] = colors[action as string] ?? [C.textMuted, 'transparent', C.border];
    const baseStyle: React.CSSProperties = { fontFamily: "'Hanken Grotesk',sans-serif", fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 2, cursor: 'pointer', border: '1px solid', lineHeight: 1.5, whiteSpace: 'nowrap' };
    return (
      <button
        key={action}
        onClick={e => { e.stopPropagation(); onDecide(s.id, s.decision === action ? null : action); }}
        style={active ? { ...baseStyle, color: c, background: bg, borderColor: bd } : { ...baseStyle, color: '#6E7682', background: 'transparent', borderColor: C.border }}
        onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.color = c; b.style.borderColor = c; }}
        onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; if (active) { b.style.color = c; b.style.borderColor = bd; } else { b.style.color = '#6E7682'; b.style.borderColor = C.border; } }}
      >{label}</button>
    );
  };

  return (
    <div style={{ borderBottom: `1px solid ${C.borderDark}` }}>
      <div
        style={{ display: 'grid', gridTemplateColumns: '34px minmax(220px,1fr) 66px 78px 86px 108px 108px 96px 224px', alignItems: 'center', height: 40, borderLeft: `2px solid ${rowBorder}`, background: rowBg, cursor: 'pointer' }}
        onClick={toggleExpand}
        onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = selected ? '#123028' : '#14181E'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = rowBg; }}
      >
        <div style={{ display: 'flex', justifyContent: 'center' }} onClick={stopProp}>
          <input type="checkbox" checked={selected} onChange={() => dispatch({ type: 'TOGGLE_SELECT', id: s.id })} aria-label="Select" style={{ accentColor: C.teal, width: 13, height: 13, cursor: 'pointer' }} />
        </div>
        <div style={{ minWidth: 0, paddingRight: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke={C.textDim} strokeWidth="1.5" strokeLinecap="round" style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform .12s', flexShrink: 0 }}>
            <path d="M3.5 2 L7 5 L3.5 8" />
          </svg>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.from_name}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.from_address}</div>
          </div>
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#C3C8D0', textAlign: 'right', paddingRight: 8, fontVariantNumeric: 'tabular-nums' }}>{s.message_count.toLocaleString()}</div>
        <div style={{ fontSize: 11, color: C.textFaint }}>{_frequency(s.message_count)}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint }}>{s.last_seen}</div>
        <div><span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: catBg, color: catColor }}>{s.category ?? '—'}</span></div>
        <div>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: capBg, color: capColor }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: capColor }} />
            {CAP_LABELS[s.capability]}
          </span>
        </div>
        <div style={{ fontSize: 11, color: '#6E7682' }}>{s.suggested_action ? DEC_LABELS[s.suggested_action] : '—'}</div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', paddingRight: 12 }}>
          {btn('keep', 'Keep')}
          {btn('unsubscribe', 'Unsub')}
          {btn('mute', 'Mute')}
          {btn('archive', 'Arch')}
          {btn('delete', 'Del')}
        </div>
      </div>

      {expanded && <ExpandedRow sender={s} onDecide={onDecide} />}
    </div>
  );
}

function ExpandedRow({ sender: s, onDecide }: { sender: Sender; onDecide: (id: string, d: Decision) => void }) {
  const { dispatch } = useStore();
  const [capColor, capBg] = CAP_COLORS[s.capability] ?? [C.textFaint, C.panel2];

  const pill = (action: Decision, label: string, color: string, bg: string, bd: string) => {
    const active = s.decision === action;
    return (
      <button
        onClick={() => onDecide(s.id, s.decision === action ? null : action)}
        style={{ fontFamily: "'Hanken Grotesk',sans-serif", fontSize: 11, fontWeight: 600, padding: '4px 9px', borderRadius: 2, cursor: 'pointer', border: '1px solid', ...(active ? { color, background: bg, borderColor: bd } : { color: '#6E7682', background: 'transparent', borderColor: C.border }) }}
        onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.color = color; b.style.borderColor = color; }}
        onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; if (active) { b.style.color = color; b.style.borderColor = bd; } else { b.style.color = '#6E7682'; b.style.borderColor = C.border; } }}
      >{label}</button>
    );
  };

  const capDetails: Record<string, string> = {
    one_click: 'A POST is sent to the List-Unsubscribe-Post endpoint. No email is opened, nothing is shown to the sender beyond the standard opt-out.',
    link: 'Opt-out is a hosted web page. MailCull cannot complete this automatically — you open the link and finish the flow, then mark it done.',
    mailto: 'A plain-text unsubscribe email is sent from your account to the listed address. Delivery is best-effort.',
    none: 'No List-Unsubscribe header or link was found in any sampled message. Use Mute to stop future mail.',
  };

  return (
    <div style={{ background: '#101319', borderTop: `1px solid ${C.borderSub}`, padding: '13px 16px 15px 56px', display: 'grid', gridTemplateColumns: '1fr 300px', gap: 22, animation: 'fadeIn .14s ease' }}>
      <div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 8 }}>SAMPLE SUBJECTS · {s.message_count.toLocaleString()} TOTAL</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          {s.sample_subjects.map((subj, i) => (
            <div key={i} style={{ display: 'flex', gap: 9, minWidth: 0, alignItems: 'baseline' }}>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3C414B', flexShrink: 0 }}>0{i + 1}</span>
              <span style={{ fontSize: 12, color: '#A8AEB8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{subj}</span>
            </div>
          ))}
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          {s.classification_degraded ? 'HEURISTIC RATIONALE' : 'LLM RATIONALE'}
          <span style={{ height: 1, flex: 1, background: C.borderSub }} />
        </div>
        {s.rationale && <div style={{ fontSize: 12, color: '#8990A0', lineHeight: 1.55, fontStyle: 'italic' }}>"{s.rationale}"</div>}
        <div style={{ display: 'flex', gap: 6, marginTop: 13 }}>
          {pill('transactional', 'Mark transactional', C.blue, C.blueBg, '#264a7a')}
          {pill('snooze', 'Snooze 30d', '#C3C8D0', C.panel2, '#3A3F47')}
          {s.decision && (
            <button onClick={() => onDecide(s.id, null)} style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textDim, fontSize: 11, padding: '4px 9px', borderRadius: 2, cursor: 'pointer' }}>Undo decision</button>
          )}
        </div>
      </div>
      <div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 8 }}>UNSUBSCRIBE DETAIL</div>
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 2, padding: '11px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: capBg, color: capColor }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: capColor }} />
              {CAP_LABELS[s.capability]}
            </span>
          </div>
          <div style={{ fontSize: 11, color: C.textFaint, lineHeight: 1.55, marginBottom: 9 }}>{capDetails[s.capability]}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDimmer, wordBreak: 'break-all', background: C.bg, border: `1px solid ${C.borderSub}`, borderRadius: 2, padding: '6px 8px' }}>
            {s.unsubscribe_links[0] ?? 'no List-Unsubscribe header found'}
          </div>
          {s.capability === 'none' && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7, marginTop: 9, paddingTop: 9, borderTop: `1px solid ${C.borderSub}` }}>
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke={C.teal} strokeWidth="1.3" style={{ marginTop: 1, flexShrink: 0 }}>
                <circle cx="7" cy="7" r="5.6" /><path d="M7 4.2v3.4M7 9.4v.3" strokeLinecap="round" />
              </svg>
              <span style={{ fontSize: 11, color: '#8990A0', lineHeight: 1.5 }}>No unsubscribe path — <span style={{ color: C.teal, fontWeight: 600 }}>Mute</span> creates a Gmail filter to auto-archive future mail.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function _frequency(count: number): string {
  if (count > 300) return 'Daily';
  if (count > 100) return 'Weekly';
  if (count > 30) return 'Monthly';
  return 'Sporadic';
}

function SelectEl({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{ background: C.panel2, border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '4px 7px', borderRadius: 2, cursor: 'pointer' }}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

function SortBtn({ label, onClick, style }: { label: string; onClick: () => void; style?: React.CSSProperties }) {
  return (
    <button onClick={onClick}
      style={{ background: 'none', border: 'none', textAlign: 'left', color: C.textDim, fontSize: 10, fontWeight: 600, letterSpacing: '.06em', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 4, ...style }}
      onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.color = C.textMuted}
      onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.color = C.textDim}
    >{label}</button>
  );
}

function ColHdr({ children }: { children: React.ReactNode }) {
  return <div style={{ color: C.textDim, fontSize: 10, fontWeight: 600, letterSpacing: '.06em' }}>{children}</div>;
}

function BulkBtn({ label, onClick, hoverColor }: { label: string; onClick: () => void; hoverColor: string }) {
  return (
    <button onClick={onClick}
      style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, fontWeight: 500, padding: '4px 9px', borderRadius: 2, cursor: 'pointer' }}
      onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = hoverColor; b.style.color = hoverColor; }}
      onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textMuted; }}
    >{label}</button>
  );
}
