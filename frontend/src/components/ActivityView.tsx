import React, { useCallback, useEffect, useState } from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import * as api from '../api';
import type { ActivityEntry } from '../types';
import { parseUtc } from './ScanView';

const ACTION_LABEL: Record<string, string> = {
  unsubscribe: 'Unsubscribe', mute: 'Mute', archive: 'Archive', delete: 'Delete',
  transactional: 'Transactional', snooze: 'Snooze', keep: 'Keep',
};
const ACTION_COLOR: Record<string, string> = {
  unsubscribe: C.amber, mute: '#C3C8D0', archive: C.cyan, delete: C.redBright, transactional: C.blue, snooze: C.amber, keep: C.green,
};

const COLS = '118px minmax(160px,1fr) 104px minmax(200px,2fr) 70px';

/** Everything MailCull has done, newest first. Persistent, so Undo still works after a reload. */
export function ActivityView() {
  const { reloadSenders } = useStore();
  const [rows, setRows] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [hideDry, setHideDry] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setRows(await api.getActivity()); }
    catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const undo = async (r: ActivityEntry) => {
    setBusy(r.id);
    setError(null);
    try {
      await api.postUndo(r.id);
      await Promise.all([load(), reloadSenders()]);
    } catch (err) { setError(`Couldn't undo ${r.from_name}: ${String(err)}`); }
    finally { setBusy(null); }
  };

  const shown = hideDry ? rows.filter(r => !r.dry_run) : rows;
  const dryCount = rows.filter(r => r.dry_run).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 14px', background: C.panel, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Activity</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textFaint }}>newest first · {shown.length} shown</span>
        <div style={{ flex: 1 }} />
        {dryCount > 0 && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.textMuted, cursor: 'pointer' }}>
            <input type="checkbox" checked={hideDry} onChange={e => setHideDry(e.target.checked)} style={{ accentColor: C.teal }} />
            Hide {dryCount} dry run{dryCount !== 1 ? 's' : ''}
          </label>
        )}
        <button onClick={load} disabled={loading}
          style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '4px 10px', borderRadius: 2, cursor: loading ? 'wait' : 'pointer' }}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', height: 30, padding: '0 14px', background: '#101216', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        {['WHEN', 'SENDER', 'ACTION', 'OUTCOME', ''].map((h, i) => (
          <span key={i} style={{ color: C.textDim, fontSize: 10, fontWeight: 600, letterSpacing: '.06em' }}>{h}</span>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {error && <div role="alert" style={{ margin: 14, background: C.redBg, border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, borderRadius: 3, padding: '9px 13px' }}>{error}</div>}
        {shown.map(r => (
          <div key={r.id} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, alignItems: 'center', minHeight: 40, padding: '5px 14px', borderBottom: `1px solid ${C.borderDark}`, opacity: r.undone ? 0.55 : 1 }}>
            <span title={parseUtc(r.created_at).toLocaleString('en-GB')} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, color: C.textFaint }}>
              {parseUtc(r.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.from_name}</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.from_address}</div>
            </div>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: ACTION_COLOR[r.action] ?? C.textMuted }}>{ACTION_LABEL[r.action] ?? r.action}</span>
              {r.dry_run && <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, fontWeight: 600, color: C.amber, background: C.amberBg, border: `1px solid ${C.amberBorder}`, borderRadius: 2, padding: '0 4px' }}>DRY</span>}
            </span>
            <span title={r.result} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, color: C.textMuted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {r.undone ? 'undone · ' : ''}{r.result}
            </span>
            <span style={{ textAlign: 'right' }}>
              {r.can_undo && (
                <button disabled={busy !== null} onClick={() => undo(r)}
                  style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, padding: '2px 9px', borderRadius: 2, cursor: busy !== null ? 'wait' : 'pointer' }}>
                  {busy === r.id ? '…' : 'Undo'}
                </button>
              )}
            </span>
          </div>
        ))}
        {!loading && !error && shown.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: C.textFaint, fontSize: 12 }}>
            {rows.length ? 'Only dry runs so far.' : 'Nothing has been done yet. Actions you confirm in Review will be listed here, with Undo where possible.'}
          </div>
        )}
      </div>
    </div>
  );
}
