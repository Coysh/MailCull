import React, { useState } from 'react';
import { C } from './tokens';

/**
 * Two-step button for irreversible actions: first click arms it, second confirms.
 * Replaces window.confirm so the prompt stays inside the console and says what will happen.
 */
export function InlineConfirm({ label, prompt, confirmLabel, onConfirm }: {
  label: string;
  prompt: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
}) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try { await onConfirm(); } finally { setBusy(false); setArmed(false); }
  };

  if (!armed) {
    return (
      <button className="btn btn-danger" onClick={() => setArmed(true)}
        style={{ background: 'transparent', border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, padding: '6px 13px', borderRadius: 2, cursor: 'pointer' }}>
        {label}
      </button>
    );
  }
  return (
    <div role="alertdialog" aria-label={prompt} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
      <span style={{ fontSize: 11, color: C.redText, maxWidth: 240, lineHeight: 1.4 }}>{prompt}</span>
      <button autoFocus disabled={busy} onClick={run}
        style={{ background: C.redBg, border: `1px solid ${C.redBright}`, color: C.redBright, fontSize: 12, fontWeight: 600, padding: '6px 13px', borderRadius: 2, cursor: busy ? 'wait' : 'pointer' }}>
        {busy ? 'Working…' : confirmLabel}
      </button>
      <button disabled={busy} onClick={() => setArmed(false)}
        style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '6px 11px', borderRadius: 2, cursor: 'pointer' }}>
        Cancel
      </button>
    </div>
  );
}
