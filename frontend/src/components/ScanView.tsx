import React, { useState } from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import type { ScanStatus } from '../types';

export function ScanView() {
  const { state, dispatch, startScan, scanRunning } = useStore();
  const scan = state.scanStatus;
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const onStart = async () => {
    setStarting(true);
    setStartError(null);
    try { await startScan(); } catch (err) { setStartError(String(err)); }
    finally { setStarting(false); }
  };

  const setDays = (v: string) => dispatch({ type: 'SET_SETTING', key: 'scanDays', value: Number(v) });

  return (
    <div style={{ overflow: 'auto', padding: '22px 24px' }}>
      <div style={{ maxWidth: 1100 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18 }}>
          <div>
            <h1 style={{ fontSize: 16, fontWeight: 600, marginBottom: 3 }}>{scanRunning ? 'Scanning mailbox' : 'Scan mailbox'}</h1>
            <div style={{ fontSize: 12, color: C.textFaint }}>
              Reads message headers, groups them by sender, finds unsubscribe links and classifies each sender.
            </div>
          </div>
          {!scanRunning && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <select value={String(state.settings.scanDays)} onChange={e => setDays(e.target.value)} disabled={starting}
                style={{ background: C.panel2, border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '6px 8px', borderRadius: 2, cursor: 'pointer' }}>
                {[['30', 'Last 30 days'], ['90', 'Last 90 days'], ['180', 'Last 180 days'], ['365', 'Last 365 days']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button onClick={onStart} disabled={starting}
                style={{ background: C.tealBg, border: `1px solid ${C.tealBorder}`, color: C.tealBright, fontSize: 12, fontWeight: 600, padding: '6px 15px', borderRadius: 2, cursor: starting ? 'wait' : 'pointer' }}
                onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealHov; b.style.borderColor = C.teal; }}
                onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.tealBg; b.style.borderColor = C.tealBorder; }}
              >{starting ? 'Starting…' : scan ? 'Scan again' : 'Start scan'}</button>
            </div>
          )}
        </div>

        {startError && (
          <div style={{ background: C.redBg, border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, borderRadius: 3, padding: '9px 13px', marginBottom: 14 }}>{startError}</div>
        )}

        {scanRunning && scan ? <Progress scan={scan} /> : <>
          {scan?.phase === 'error' && (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, background: C.redBg, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '9px 13px', marginBottom: 14 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: C.redBright }}>Latest scan didn't finish</span>
              <span style={{ fontSize: 12, color: C.redText }}>
                started {_timeAgo(scan.started_at)} · {scan.error}
              </span>
            </div>
          )}
          <LastScan scan={state.lastCompletedScan} />
        </>}
      </div>
    </div>
  );
}

function LastScan({ scan }: { scan: ScanStatus | null }) {
  const { dispatch } = useStore();
  if (!scan) {
    return (
      <Panel>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>No completed scans yet</div>
        <div style={{ fontSize: 12, color: C.textFaint }}>Choose a time window and start a scan. Nothing in Gmail is changed by scanning.</div>
      </Panel>
    );
  }
  const failed = scan.phase === 'error';
  const when = scan.finished_at ?? scan.started_at;
  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: failed ? C.red : C.green }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {failed ? 'Last scan failed' : 'Last scanned'} {_timeAgo(when)}
          </span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textDim }}>
            {_formatDate(when)} · window: last {scan.since_days} days
          </span>
        </div>
        {!failed && (
          <button onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'review' })}
            style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '5px 12px', borderRadius: 2, cursor: 'pointer' }}>
            Review senders →
          </button>
        )}
      </div>
      {failed ? (
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.redText, lineHeight: 1.5 }}>{scan.error}</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
            <StatCard value={scan.total_messages.toLocaleString()} label="messages read" />
            <StatCard value={scan.total_senders.toLocaleString()} label="unique senders" />
          </div>
          {scan.status_detail && (
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textDim, marginTop: 10 }}>{scan.status_detail}</div>
          )}
        </>
      )}
    </Panel>
  );
}

function Progress({ scan }: { scan: ScanStatus }) {
  const { state } = useStore();
  const pct = scan.progress_pct;
  const phaseName = PHASE_LABELS[scan.phase] ?? _capitalise(scan.phase);
  const model = state.ollamaUp ? state.settings.ollamaModel : 'heuristic mode';
  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 14, height: 14, borderWidth: 2, borderStyle: 'solid', borderColor: C.teal, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .8s linear infinite' }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>{phaseName}{scan.phase === 'classifying' ? ` · ${model}` : ''}</span>
        </div>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: C.teal }}>{pct}%</span>
      </div>
      {scan.status_detail && (
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textDim, marginBottom: 10, paddingLeft: 24 }}>{scan.status_detail}</div>
      )}
      <div style={{ height: 6, background: C.panel2, borderRadius: 1, overflow: 'hidden', marginBottom: 14 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: `repeating-linear-gradient(45deg,${C.teal} 0,${C.teal} 7px,#1E7268 7px,#1E7268 14px)`, backgroundSize: '28px 28px', animation: 'stripe 1s linear infinite', transition: 'width .3s' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
        <StatCard value={scan.total_messages.toLocaleString()} label="messages read" />
        <StatCard value={scan.total_senders.toLocaleString()} label="unique senders" />
        <StatCard value={_timeAgo(scan.started_at).replace(' ago', '')} label="running for" color={C.textMuted} />
      </div>
      <div style={{ fontSize: 11, color: C.textFaint, marginTop: 12, lineHeight: 1.55 }}>
        You can leave this page — the scan keeps running and the sidebar shows its progress.
        Large mailboxes take a while because MailCull stays under Gmail's rate limit rather than skipping messages.
      </div>
    </Panel>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, padding: 18, marginBottom: 14 }}>{children}</div>;
}

function StatCard({ value, label, color }: { value: string; label: string; color?: string }) {
  return (
    <div style={{ background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '10px 12px' }}>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 19, fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: color ?? C.text }}>{value}</div>
      <div style={{ fontSize: 11, color: C.textFaint }}>{label}</div>
    </div>
  );
}

const PHASE_LABELS: Record<string, string> = {
  scanning: 'Starting',
  reading: 'Reading messages',
  aggregating: 'Grouping by sender',
  links: 'Finding unsubscribe links',
  classifying: 'Classifying senders',
  saving: 'Saving',
};

function _capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Backend timestamps are UTC; older rows have no offset, so treat those as UTC too. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
}

export function _timeAgo(iso: string): string {
  const mins = Math.floor((Date.now() - parseUtc(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d !== 1 ? 's' : ''} ago`;
}

function _formatDate(iso: string): string {
  return parseUtc(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}
