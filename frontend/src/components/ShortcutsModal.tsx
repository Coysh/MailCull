import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';

const SHORTCUTS = [
  { key: 'j / k',  desc: 'Move between sender rows' },
  { key: '↵',      desc: 'Expand / collapse the focused row' },
  { key: 'e',      desc: 'Keep' },
  { key: 'u',      desc: 'Unsubscribe' },
  { key: 'm',      desc: 'Mute (create filter)' },
  { key: 'd',      desc: 'Delete existing mail' },
  { key: 'x',      desc: 'Toggle selection' },
  { key: '?',      desc: 'Show / hide this help' },
];

export function ShortcutsModal() {
  const { dispatch } = useStore();
  const close = () => dispatch({ type: 'TOGGLE_SHORTCUTS' });

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(8,9,11,.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
      onClick={close}
    >
      <div
        style={{ background: C.panel, border: `1px solid #31353D`, borderRadius: 4, padding: '20px 22px', width: 380, animation: 'fadeIn .14s ease' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Keyboard shortcuts</span>
          <kbd style={{ fontSize: 10, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '1px 6px', color: C.textFaint }}>esc</kbd>
        </div>
        {SHORTCUTS.map(({ key, desc }) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', padding: '5px 0', borderBottom: `1px solid ${C.panel2}` }}>
            <kbd style={{ fontSize: 11, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '1px 7px', color: C.text, minWidth: 46, textAlign: 'center' }}>{key}</kbd>
            <span style={{ fontSize: 12, color: C.textMuted, marginLeft: 13 }}>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
