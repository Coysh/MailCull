import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import * as api from '../api';

export function TopBar() {
  const { state, dispatch, checkOllama } = useStore();
  const missing = state.authStatus.missing_scopes ?? [];

  const screenLabels: Record<string, string> = {
    inbox: 'inbox', review: 'review', scanning: 'scan', confirm: 'confirm', results: 'results', settings: 'settings',
  };

  return (
    <header style={{ height: 42, display: 'flex', alignItems: 'center', gap: 12, background: C.panel, borderBottom: `1px solid ${C.border}`, padding: '0 14px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width="17" height="17" viewBox="0 0 28 28" fill="none" stroke={C.teal} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2.5" y="6" width="23" height="16" rx="2" /><path d="M3 9.5 L14 16.5 L25 9.5" />
          <path d="M19 22 L25.5 22 M22.5 18.5 L25.5 22 L22.5 25.5" stroke={C.red} />
        </svg>
        <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-0.3px' }}>MailCull</span>
      </div>
      <div style={{ width: 1, height: 16, background: C.border }} />
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textFaint }}>{screenLabels[state.screen] || ''}</span>

      <div style={{ flex: 1 }} />

      {state.dryRun && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: C.amberBg, border: `1px solid ${C.amberBorder}`, borderRadius: 2, padding: '2px 9px' }}>
          <span style={{ width: 5, height: 5, background: C.amber, borderRadius: '50%', animation: 'pulse 1.8s infinite' }} />
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 600, color: C.amber, letterSpacing: '.07em' }}>DRY RUN</span>
        </div>
      )}

      <button
        title="Re-check Ollama"
        onClick={checkOllama}
        style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 2, padding: '3px 9px', cursor: 'pointer' }}
        onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.borderColor = C.borderHov}
        onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.borderColor = C.border}
      >
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: state.ollamaUp ? C.green : C.amber }} />
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint }}>ollama</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: state.ollamaUp ? C.green : C.amber }}>{state.ollamaUp ? 'up' : 'down'}</span>
      </button>

      {missing.length > 0 && (
        <button
          title={`Not granted: ${missing.map(s => s.split('/').pop()).join(', ')}`}
          onClick={async () => { const { consent_url } = await api.getAuthStartUrl(); window.location.href = consent_url; }}
          style={{ background: C.amberBg, border: `1px solid ${C.amberBorder}`, borderRadius: 2, padding: '3px 9px', cursor: 'pointer', color: C.amber, fontSize: 11 }}
        >Re-authorise for email unsubscribes</button>
      )}

      {state.authStatus.account && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '3px 9px' }}>
          <span style={{ width: 6, height: 6, background: C.green, borderRadius: '50%' }} />
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textMuted }}>{state.authStatus.account}</span>
        </div>
      )}

      <button
        onClick={() => dispatch({ type: 'TOGGLE_SHORTCUTS' })}
        aria-label="Keyboard shortcuts"
        style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 2, padding: '3px 8px', cursor: 'pointer', color: C.textFaint }}
        onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.borderHov; b.style.color = '#C3C8D0'; }}
        onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textFaint; }}
      >
        <kbd style={{ fontSize: 10 }}>?</kbd>
        <span style={{ fontSize: 11 }}>keys</span>
      </button>
    </header>
  );
}
