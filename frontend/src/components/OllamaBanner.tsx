import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';

export function OllamaBanner() {
  const { state, dispatch } = useStore();
  if (state.ollamaUp) return null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: C.amberBg, borderBottom: `1px solid ${C.amberBorder}`, padding: '6px 16px', flexShrink: 0 }}>
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke={C.amber} strokeWidth="1.3" strokeLinecap="round">
        <path d="M7 1.8 L12.8 12 L1.2 12 Z" /><line x1="7" y1="5.3" x2="7" y2="8.4" /><circle cx="7" cy="10.2" r=".55" fill={C.amber} />
      </svg>
      <span style={{ fontSize: 12, fontWeight: 600, color: C.amber }}>Ollama unreachable</span>
      <span style={{ fontSize: 12, color: C.amberDim }}>— classifying with heuristics only (header rules, volume, known-sender list). Rationale quality is reduced.</span>
      <a href="#" onClick={e => { e.preventDefault(); dispatch({ type: 'SET_SCREEN', screen: 'settings' }); dispatch({ type: 'SET_SETTINGS_SECTION', section: 'ai' }); }}
        style={{ marginLeft: 'auto', fontSize: 11, color: C.amber, textDecoration: 'none' }}>Configure →</a>
    </div>
  );
}
