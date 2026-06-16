import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import type { Screen } from '../types';

interface NavItem {
  id: Screen;
  label: string;
  icon: React.ReactNode;
  badge?: React.ReactNode;
}

export function Sidebar() {
  const { state, dispatch, decided } = useStore();
  const pending = state.senders.filter(s => !s.decision);

  const navItem = (id: Screen) => {
    const active = state.screen === id;
    return {
      style: {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '7px 14px', cursor: 'pointer',
        borderLeft: `2px solid ${active ? C.teal : 'transparent'}`,
        background: active ? C.tealBg : 'transparent',
        margin: '1px 0',
      } as React.CSSProperties,
      iconColor: active ? C.teal : C.textDim,
      textColor: active ? C.text : '#8990A0',
      fw: active ? 600 : 500,
    };
  };

  const goto = (screen: Screen) => dispatch({ type: 'SET_SCREEN', screen });

  const navItems = [
    {
      id: 'review' as Screen,
      label: 'Review',
      icon: (c: string) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={c} strokeWidth="1.3" strokeLinecap="round"><line x1="1.5" y1="3" x2="12.5" y2="3" /><line x1="1.5" y1="7" x2="12.5" y2="7" /><line x1="1.5" y1="11" x2="8.5" y2="11" /></svg>,
      badge: pending.length > 0 ? (
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, background: C.panel2, color: C.textFaint, padding: '0 6px', borderRadius: 9, minWidth: 18, textAlign: 'center' as const }}>{pending.length}</span>
      ) : null,
    },
    {
      id: 'scanning' as Screen,
      label: 'Scan',
      icon: (c: string) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={c} strokeWidth="1.3" strokeLinecap="round"><circle cx="6" cy="6" r="4" /><line x1="9" y1="9" x2="12.5" y2="12.5" strokeWidth="1.7" /></svg>,
      badge: state.screen === 'scanning' ? (
        <span style={{ width: 6, height: 6, background: C.teal, borderRadius: '50%', animation: 'pulse 1.4s infinite' }} />
      ) : null,
    },
    {
      id: 'confirm' as Screen,
      label: 'Confirm',
      icon: (c: string) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={c} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="10" height="10" rx="1.5" /><path d="M4.6 7 L6.2 8.6 L9.4 5.2" /></svg>,
      badge: decided.length > 0 ? (
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, background: C.tealBg, color: C.tealBright, padding: '0 6px', borderRadius: 9, minWidth: 18, textAlign: 'center' as const }}>{decided.length}</span>
      ) : null,
    },
    {
      id: 'results' as Screen,
      label: 'Results',
      icon: (c: string) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={c} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3.2 L3.2 4.4 L5 2.4" /><path d="M2 8.2 L3.2 9.4 L5 7.4" /><line x1="7" y1="3.4" x2="12.5" y2="3.4" /><line x1="7" y1="8.4" x2="12.5" y2="8.4" /></svg>,
      badge: null,
    },
  ];

  return (
    <nav style={{ width: 186, background: C.panel, borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', flexShrink: 0, padding: '7px 0' }}>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.1em', color: '#3C414B', padding: '6px 14px 7px' }}>WORKFLOW</div>

      {navItems.map(item => {
        const n = navItem(item.id);
        return (
          <div key={item.id} onClick={() => goto(item.id)} style={n.style}
            onMouseEnter={e => { if (state.screen !== item.id) (e.currentTarget as HTMLDivElement).style.background = C.panel2; }}
            onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = state.screen === item.id ? C.tealBg : 'transparent'; }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {item.icon(n.iconColor)}
              <span style={{ fontSize: 12.5, fontWeight: n.fw, color: n.textColor }}>{item.label}</span>
            </div>
            {item.badge}
          </div>
        );
      })}

      <div style={{ flex: 1 }} />

      <div style={{ borderTop: `1px solid ${C.borderSub}`, paddingTop: 6, margin: '6px 0 0' }}>
        {(() => {
          const n = navItem('settings');
          return (
            <div onClick={() => goto('settings')} style={n.style}
              onMouseEnter={e => { if (state.screen !== 'settings') (e.currentTarget as HTMLDivElement).style.background = C.panel2; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = state.screen === 'settings' ? C.tealBg : 'transparent'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={n.iconColor} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="7" cy="7" r="2.1" /><path d="M7 1.4v1.6M7 11v1.6M1.4 7h1.6M11 7h1.6M3 3l1.1 1.1M9.9 9.9 L11 11M3 11l1.1-1.1M9.9 4.1 L11 3" />
                </svg>
                <span style={{ fontSize: 12.5, fontWeight: n.fw, color: n.textColor }}>Settings</span>
              </div>
            </div>
          );
        })()}
      </div>

      <div style={{ padding: '9px 14px 4px', borderTop: `1px solid ${C.borderSub}`, marginTop: 4 }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#3C414B', letterSpacing: '.05em', marginBottom: 4 }}>MAILBOX</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint, lineHeight: 1.7 }}>
          {state.senders.length} senders<br />
          {state.scanStatus ? `${state.scanStatus.total_messages.toLocaleString()} messages` : '—'}<br />
          {state.scanStatus?.finished_at ? `scanned ${_timeAgo(state.scanStatus.finished_at)}` : '—'}
        </div>
      </div>
    </nav>
  );
}

function _timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
