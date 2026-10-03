import React, { useEffect, useRef } from 'react';
import { C } from './tokens';
import { useStore } from '../store';

const SHORTCUTS = [
  { key: 'j / k',  desc: 'Move between sender rows' },
  { key: '↵',      desc: 'Expand / collapse the focused row' },
  { key: 'e',      desc: 'Keep (marks it handled, no confirm needed)' },
  { key: 'u',      desc: 'Unsubscribe' },
  { key: 'm',      desc: 'Mute (create filter)' },
  { key: 'a',      desc: 'Archive existing mail' },
  { key: 'd',      desc: 'Delete existing mail (to Trash)' },
  { key: 't',      desc: 'Mark transactional' },
  { key: 's',      desc: 'Snooze' },
  { key: 'x',      desc: 'Toggle selection' },
  { key: '?',      desc: 'Show / hide this help' },
  { key: 'esc',    desc: 'Close this help / collapse the row' },
];

export function ShortcutsModal() {
  const { dispatch } = useStore();
  const close = () => dispatch({ type: 'TOGGLE_SHORTCUTS' });
  const dialog = useRef<HTMLDivElement>(null);

  // Move focus into the dialog, trap Tab inside it, and hand focus back on close
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const closeBtn = dialog.current?.querySelector<HTMLElement>('button');
    closeBtn?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === 'Tab') { e.preventDefault(); closeBtn?.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { document.removeEventListener('keydown', trap); opener?.focus?.(); };
  }, []);

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(8,9,11,.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
      onClick={close}
    >
      <div
        ref={dialog} role="dialog" aria-modal="true" aria-labelledby="shortcuts-title"
        style={{ background: C.panel, border: `1px solid #31353D`, borderRadius: 4, padding: '20px 22px', width: 400, animation: 'fadeIn .14s ease' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span id="shortcuts-title" style={{ fontSize: 13, fontWeight: 600 }}>Keyboard shortcuts</span>
          <button onClick={close} aria-label="Close shortcuts"
            style={{ background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '1px 8px', color: C.textMuted, fontSize: 10, cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace" }}>esc</button>
        </div>
        {SHORTCUTS.map(({ key, desc }) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', padding: '5px 0', borderBottom: `1px solid ${C.panel2}` }}>
            <kbd style={{ fontSize: 11, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '1px 7px', color: C.text, minWidth: 46, textAlign: 'center' }}>{key}</kbd>
            <span style={{ fontSize: 12, color: C.textMuted, marginLeft: 13 }}>{desc}</span>
          </div>
        ))}
        <div style={{ fontSize: 11, color: C.textFaint, marginTop: 12, lineHeight: 1.5 }}>
          Pressing the same key again clears the decision. After a decision the focus moves to the next row.
        </div>
      </div>
    </div>
  );
}
