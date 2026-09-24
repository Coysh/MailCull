import React, { useCallback, useEffect, useState } from 'react';
import { C, CAP_COLORS, CAP_LABELS, STATUS_META } from './tokens';
import { useStore } from '../store';
import * as api from '../api';
import type { ActionResult, InboxMessage } from '../types';
import { parseUtc } from './ScanView';

type Filter = 'all' | 'unsubscribable' | 'unread';
type PendingAction = { messageId: string; action: 'unsubscribe' | 'mute' };

const COLS = '14px 62px minmax(180px,1.1fr) minmax(200px,2fr) 96px 100px 196px';

export function InboxView() {
  const { state, reloadSenders } = useStore();
  const [messages, setMessages] = useState<InboxMessage[]>([]);
  const [nextToken, setNextToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [confirming, setConfirming] = useState<PendingAction | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ActionResult>>({}); // by message_id

  const load = useCallback(async (token: string | null = null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.getInbox(token);
      setMessages(prev => token ? [...prev, ...page.messages] : page.messages);
      setNextToken(page.next_page_token);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = async ({ messageId, action }: PendingAction) => {
    setConfirming(null);
    setRunning(messageId);
    try {
      const result = await api.postInboxAction(messageId, action, state.settings.muteAction);
      setResults(r => ({ ...r, [messageId]: result }));
      // Every message from this sender now shares the new status
      if (!state.dryRun) {
        setMessages(ms => ms.map(m => m.sender_id === result.sender_id ? { ...m, sender_status: result.status } : m));
      }
      reloadSenders();
    } catch (err) {
      const m = messages.find(x => x.message_id === messageId);
      setResults(r => ({ ...r, [messageId]: {
        sender_id: m?.sender_id ?? '', from_name: m?.from_name ?? '', from_address: m?.from_address ?? '',
        decision: action, method: 'request', status: 'failed', detail: String(err), can_undo: false,
        link: null, error: String(err), http_status: null, attempts: [], action_id: null, skipped: false,
      } }));
    } finally {
      setRunning(null);
    }
  };

  const shown = messages.filter(m => {
    if (filter === 'unread') return m.unread;
    if (filter === 'unsubscribable') return m.capability !== 'none';
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 14px', background: C.panel, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Inbox</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textFaint }}>
          newest first · {messages.length} loaded
        </span>
        <div style={{ width: 1, height: 15, background: C.border, margin: '0 3px' }} />
        <select value={filter} onChange={e => setFilter(e.target.value as Filter)}
          style={{ background: C.panel2, border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '4px 7px', borderRadius: 2, cursor: 'pointer' }}>
          <option value="all">All messages</option>
          <option value="unsubscribable">Has unsubscribe header</option>
          <option value="unread">Unread</option>
        </select>
        <div style={{ flex: 1 }} />
        {state.dryRun && <span style={{ fontSize: 11, color: C.amber }}>Dry run — actions are simulated</span>}
        <button onClick={() => load()} disabled={loading}
          style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '4px 10px', borderRadius: 2, cursor: loading ? 'wait' : 'pointer' }}>
          {loading && !messages.length ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', height: 30, padding: '0 14px', background: '#101216', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <span />
        {['RECEIVED', 'FROM', 'SUBJECT', 'UNSUBSCRIBE', 'SENDER', ''].map((h, i) => (
          <span key={i} style={{ color: C.textDim, fontSize: 10, fontWeight: 600, letterSpacing: '.06em' }}>{h}</span>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {error && (
          <div style={{ margin: 14, background: C.redBg, border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, borderRadius: 3, padding: '9px 13px' }}>{error}</div>
        )}
        {shown.map(m => (
          <Row key={m.message_id} m={m}
            confirming={confirming?.messageId === m.message_id ? confirming.action : null}
            running={running === m.message_id}
            busy={running !== null}
            result={results[m.message_id]}
            onAsk={action => setConfirming({ messageId: m.message_id, action })}
            onCancel={() => setConfirming(null)}
            onConfirm={() => confirming && run(confirming)}
          />
        ))}
        {!loading && !error && shown.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: C.textFaint }}>
            {messages.length ? 'No messages match this filter' : 'Your inbox is empty'}
          </div>
        )}
        {nextToken && (
          <div style={{ padding: 14, display: 'flex', justifyContent: 'center' }}>
            <button onClick={() => load(nextToken)} disabled={loading}
              style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '6px 16px', borderRadius: 2, cursor: loading ? 'wait' : 'pointer' }}>
              {loading ? 'Loading…' : 'Load older messages'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ m, confirming, running, busy, result, onAsk, onCancel, onConfirm }: {
  m: InboxMessage;
  confirming: 'unsubscribe' | 'mute' | null;
  running: boolean;
  busy: boolean;
  result?: ActionResult;
  onAsk: (a: 'unsubscribe' | 'mute') => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [capColor, capBg] = CAP_COLORS[m.capability] ?? [C.textFaint, C.panel2];
  const status = result?.status ?? m.sender_status;
  const statusMeta = status && status !== 'pending' ? STATUS_META[status] : null;
  const capTitle = m.capability === 'none'
    ? 'No unsubscribe header on this email — MailCull will look for a link in its body'
    : 'Unsubscribe methods from this exact email (freshest token)';

  return (
    <div style={{ borderBottom: `1px solid ${C.borderDark}`, background: confirming ? '#14171C' : 'transparent' }}>
      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', minHeight: 40, padding: '0 14px' }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: m.unread ? C.teal : 'transparent' }} title={m.unread ? 'Unread' : undefined} />
        <span title={parseUtc(m.received_at).toLocaleString('en-GB')} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, color: C.textFaint }}>
          {_received(m.received_at)}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: m.unread ? 600 : 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.from_name}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.from_address}</div>
        </div>
        <div title={m.subject} style={{ fontSize: 12, color: m.unread ? C.text : '#A8AEB8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.subject || '(no subject)'}</div>
        <span title={capTitle} style={{ justifySelf: 'start', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: capBg, color: capColor, whiteSpace: 'nowrap' }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: capColor }} />
          {m.capability === 'none' ? 'No header' : CAP_LABELS[m.capability]}
        </span>
        <span>
          {statusMeta && (
            <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 2, background: statusMeta[2], color: statusMeta[1] }}>{statusMeta[0]}</span>
          )}
          {!statusMeta && m.message_count != null && (
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>{m.message_count.toLocaleString()} msgs</span>
          )}
        </span>
        <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
          {running ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.teal }}>
              <span style={{ width: 10, height: 10, border: `1.5px solid ${C.teal}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .8s linear infinite' }} />
              Working…
            </span>
          ) : confirming ? (
            <>
              <button onClick={onConfirm} style={btn(confirming === 'unsubscribe' ? C.amber : '#C3C8D0', true)}>
                Confirm {confirming === 'unsubscribe' ? 'unsubscribe' : 'mute'}
              </button>
              <button onClick={onCancel} style={btn(C.textDim)}>Cancel</button>
            </>
          ) : (
            <>
              <button disabled={busy} onClick={() => onAsk('unsubscribe')} style={btn(C.amber)}>Unsubscribe</button>
              <button disabled={busy} onClick={() => onAsk('mute')} style={btn('#C3C8D0')}
                title="Create a Gmail filter so future mail from this sender skips your inbox">Mute</button>
            </>
          )}
        </div>
      </div>
      {confirming && (
        <div style={{ padding: '0 14px 9px 100px', fontSize: 11, color: C.textFaint }}>
          {confirming === 'unsubscribe'
            ? `Unsubscribe from ${m.from_address} using this email's unsubscribe link${m.capability === 'none' ? ' (from its body)' : ''}.`
            : `Create a Gmail filter so future mail from ${m.from_address} skips your inbox.`}
        </div>
      )}
      {result && (
        <div style={{ padding: '0 14px 9px 100px', display: 'flex', flexWrap: 'wrap', gap: '2px 6px', alignItems: 'baseline' }}>
          {(result.attempts.length ? result.attempts : [result.detail]).map((step, i) => (
            <span key={i} title={step} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: result.status === 'failed' ? C.redText : C.textFaint, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {i > 0 && <span style={{ color: C.textGhost }}>→ </span>}{step}
            </span>
          ))}
          {result.status === 'needs_link' && result.link && (
            <a href={result.link} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: C.amber }}>Open unsubscribe page ↗</a>
          )}
        </div>
      )}
    </div>
  );
}

function btn(color: string, solid = false): React.CSSProperties {
  return {
    background: solid ? 'rgba(255,255,255,.04)' : 'transparent',
    border: `1px solid ${solid ? color : C.border}`,
    color: solid ? color : C.textMuted,
    fontSize: 11, fontWeight: solid ? 600 : 500, padding: '3px 9px', borderRadius: 2, cursor: 'pointer', whiteSpace: 'nowrap',
  };
}

function _received(iso: string): string {
  const d = parseUtc(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString('en-GB', sameYear ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: '2-digit' });
}
