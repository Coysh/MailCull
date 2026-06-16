import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import * as api from '../api';

export function NotConnected() {
  const { state, dispatch } = useStore();

  const handleConnect = async () => {
    try {
      const { consent_url } = await api.getAuthStartUrl();
      window.location.href = consent_url;
    } catch {
      dispatch({ type: 'SET_AUTH_ERROR', error: true });
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: '40px', gap: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <MailCullLogo size={22} />
        <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.4px' }}>MailCull</span>
      </div>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textDimmer, letterSpacing: '.06em', marginBottom: 30 }}>
        SELF-HOSTED · GMAIL · localhost:8420
      </div>

      {state.authError && (
        <div style={{ width: 380, display: 'flex', alignItems: 'flex-start', gap: 9, background: C.redBg, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '10px 12px', marginBottom: 12, animation: 'fadeIn .14s ease' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={C.red} strokeWidth="1.3" strokeLinecap="round" style={{ marginTop: 1, flexShrink: 0 }}>
            <path d="M7 1.8 L12.8 12 L1.2 12 Z" /><line x1="7" y1="5.3" x2="7" y2="8.4" /><circle cx="7" cy="10.2" r=".55" fill={C.red} />
          </svg>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.red, marginBottom: 1 }}>Authorisation failed</div>
            <div style={{ fontSize: 11, color: C.redText, lineHeight: 1.5 }}>The OAuth token was revoked or expired. Re-authorise to reconnect the mailbox.</div>
          </div>
        </div>
      )}

      <div style={{ width: 380, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3 }}>
        <div style={{ padding: '18px 20px', borderBottom: `1px solid ${C.borderSub}` }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 3 }}>Connect your mailbox</div>
          <div style={{ fontSize: 12, color: C.textFaint, lineHeight: 1.55 }}>
            Authorise read &amp; modify access through the official Gmail API. Classification runs locally via Ollama — no email content leaves this machine.
          </div>
        </div>
        <div style={{ padding: '18px 20px' }}>
          <button
            onClick={handleConnect}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '9px 16px', background: C.tealBg, border: `1px solid ${C.tealBorder}`, borderRadius: 2, color: C.tealBright, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = C.tealHov; (e.currentTarget as HTMLButtonElement).style.borderColor = C.teal; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = C.tealBg; (e.currentTarget as HTMLButtonElement).style.borderColor = C.tealBorder; }}
          >
            <GoogleIcon />
            Sign in with Google
          </button>

          <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
            <div style={{ flex: 1, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '10px 11px' }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 7 }}>REQUIRED SCOPES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {['gmail.readonly', 'gmail.modify', 'gmail.settings.basic'].map(s => (
                  <div key={s} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.textFaint }}>{s}</div>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 2, padding: '10px 11px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 7 }}>
                <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke={C.teal} strokeWidth="1.3"><rect x="2.5" y="6" width="9" height="6.5" rx="1" /><path d="M4.5 6 V4.3 a2.5 2.5 0 0 1 5 0 V6" /></svg>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer }}>LOCAL ONLY</span>
              </div>
              <div style={{ fontSize: 11, color: C.textFaint, lineHeight: 1.5 }}>Processed on-device. No third-party AI APIs are ever called.</div>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: 13 }}>
            <a href="https://github.com/mailcull/mailcull#oauth-setup" target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: C.textDim, textDecoration: 'none' }}
              onMouseEnter={e => (e.currentTarget as HTMLAnchorElement).style.color = C.teal}
              onMouseLeave={e => (e.currentTarget as HTMLAnchorElement).style.color = C.textDim}
            >Setup &amp; OAuth client documentation →</a>
          </div>
        </div>
      </div>
    </div>
  );
}

function MailCullLogo({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" stroke={C.teal} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="6" width="23" height="16" rx="2" />
      <path d="M3 9.5 L14 16.5 L25 9.5" />
      <path d="M19 22 L25.5 22 M22.5 18.5 L25.5 22 L22.5 25.5" stroke={C.red} />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  );
}
