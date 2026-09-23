import React, { useEffect } from 'react';
import { C, CAT_COLORS } from './tokens';
import { useStore } from '../store';
import * as api from '../api';

export function ScanView() {
  const { state, dispatch } = useStore();
  const scan = state.scanStatus;

  useEffect(() => {
    if (!state.scanId && state.authStatus.connected) {
      dispatch({ type: 'SET_SENDERS', senders: [] }); // clear stale results from prior scan
      api.postStartScan(state.settings.scanDays).then(({ scan_id }) => {
        dispatch({ type: 'SET_SCAN_ID', id: scan_id });
      }).catch(console.error);
    }
  }, []);

  const pct = scan?.progress_pct ?? 0;
  const phase = scan?.phase ?? 'initialising';
  const phaseName = PHASE_LABELS[phase] ?? _capitalise(phase);
  const phaseLabel = state.ollamaUp
    ? `${phaseName} · ${state.settings.ollamaModel}`
    : `${phaseName} · heuristic mode`;

  const sampleSenders = state.senders.slice(0, 8);

  return (
    <div style={{ overflow: 'auto', padding: '22px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 18, maxWidth: 1100 }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 600, marginBottom: 3 }}>Scanning mailbox</h1>
          <div style={{ fontSize: 12, color: C.textFaint }}>Reading headers and classifying senders · window: last {state.settings.scanDays} days</div>
        </div>
        <button
          onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'review' })}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 2, color: C.textMuted, fontSize: 12, padding: '6px 12px', cursor: 'pointer' }}
          onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.borderHov; b.style.color = C.text; }}
          onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textMuted; }}
        >Use partial results →</button>
      </div>

      <div style={{ maxWidth: 1100, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, padding: 18, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 14, height: 14, borderWidth: 2, borderStyle: 'solid', borderColor: phase === 'error' ? C.red : C.teal, borderTopColor: 'transparent', borderRadius: '50%', animation: phase === 'done' || phase === 'error' ? 'none' : 'spin .8s linear infinite' }} />
            <span style={{ fontSize: 13, fontWeight: 600 }}>{phaseLabel}</span>
          </div>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: C.teal }}>{pct}%</span>
        </div>
        {scan?.status_detail && (
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textDim, marginBottom: 10, paddingLeft: 24 }}>{scan.status_detail}</div>
        )}
        <div style={{ height: 6, background: C.panel2, borderRadius: 1, overflow: 'hidden', marginBottom: 14 }}>
          <div style={{ height: '100%', width: `${pct}%`, background: `repeating-linear-gradient(45deg,${C.teal} 0,${C.teal} 7px,#1E7268 7px,#1E7268 14px)`, backgroundSize: '28px 28px', animation: 'stripe 1s linear infinite', transition: 'width .3s' }} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          <StatCard value={(scan?.total_messages ?? 0).toLocaleString()} label="messages read" />
          <StatCard value={(scan?.total_senders ?? 0).toLocaleString()} label="unique senders" />
          <StatCard value={_classified(scan?.status_detail)} label="classified" color={C.teal} />
          <StatCard value={_queued(scan)} label="queued" color={C.amber} />
        </div>
      </div>

      <div style={{ maxWidth: 1100, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', borderBottom: `1px solid ${C.borderSub}` }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: '.06em', color: C.textDim }}>RESULTS STREAMING IN</span>
          <span style={{ fontSize: 11, color: C.textFaint }}>Partial results are usable now — open Review anytime</span>
        </div>
        {sampleSenders.map((s, i) => {
          const [catColor, catBg] = CAT_COLORS[s.category ?? 'Marketing'] ?? [C.textMuted, C.panel2];
          const isClassifying = !s.category && i >= Math.floor(sampleSenders.length * 0.7);
          return (
            <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1fr 78px 116px 120px', alignItems: 'center', padding: '8px 14px', borderBottom: `1px solid ${C.borderDark}`, animation: 'rowIn .3s ease both' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 500 }}>{s.from_name}</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>{s.from_address}</div>
              </div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: C.textMuted, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{s.message_count.toLocaleString()}</div>
              <div>
                {s.category && <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 2, background: catBg, color: catColor }}>{s.category}</span>}
              </div>
              <div style={{ textAlign: 'right' }}>
                {isClassifying ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ width: 9, height: 9, border: `1.5px solid ${C.teal}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .8s linear infinite' }} />
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim }}>classifying</span>
                  </span>
                ) : s.category ? (
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.teal }}>✓ done</span>
                ) : null}
              </div>
            </div>
          );
        })}
        {sampleSenders.length === 0 && (
          <div style={{ padding: '20px 14px', textAlign: 'center', color: C.textFaint, fontSize: 12 }}>Waiting for first results…</div>
        )}
      </div>
    </div>
  );
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
  links: 'Finding unsubscribe links',
};

function _capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Parse "Classified 75/300 senders" from status_detail
function _classified(detail: string | null | undefined): string {
  if (!detail) return '0';
  const m = detail.match(/Classified (\d+)\/(\d+)/);
  return m ? Number(m[1]).toLocaleString() : '0';
}

function _queued(scan: { total_senders?: number; status_detail?: string | null } | null): string {
  if (!scan) return '0';
  const total = scan.total_senders ?? 0;
  const m = scan.status_detail?.match(/Classified (\d+)\/(\d+)/);
  const done = m ? Number(m[1]) : 0;
  return Math.max(0, total - done).toLocaleString();
}
