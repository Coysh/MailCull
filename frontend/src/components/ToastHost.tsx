import React, { useEffect } from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import type { Toast } from '../types';

export function ToastHost() {
  const { state } = useStore();
  if (!state.toasts.length) return null;
  return (
    <div style={{ position: 'fixed', right: 16, bottom: 16, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 200, maxWidth: 420 }}>
      {state.toasts.map(t => <ToastItem key={t.id} toast={t} />)}
    </div>
  );
}

function ToastItem({ toast: t }: { toast: Toast }) {
  const { dispatch } = useStore();
  const error = t.tone === 'error';
  const dismiss = () => dispatch({ type: 'DISMISS_TOAST', id: t.id });

  useEffect(() => {
    const id = setTimeout(dismiss, error ? 10_000 : 6_000);
    return () => clearTimeout(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div role={error ? 'alert' : 'status'}
      style={{ display: 'flex', alignItems: 'center', gap: 12, background: error ? C.redBg : C.panel2, border: `1px solid ${error ? C.redBorder : C.borderHov}`, borderRadius: 3, padding: '9px 12px', animation: 'fadeIn .14s ease', boxShadow: '0 4px 14px rgba(0,0,0,.4)' }}>
      <span style={{ fontSize: 12, color: error ? C.redBright : C.text, lineHeight: 1.45, flex: 1 }}>{t.text}</span>
      {t.actionLabel && (
        <button onClick={() => { t.onAction?.(); dismiss(); }}
          style={{ background: 'transparent', border: `1px solid ${error ? C.redBorder : C.tealBorder}`, color: error ? C.redBright : C.tealBright, fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 2, cursor: 'pointer' }}>
          {t.actionLabel}
        </button>
      )}
      <button onClick={dismiss} aria-label="Dismiss"
        style={{ background: 'transparent', border: 'none', color: C.textMuted, fontSize: 14, lineHeight: 1, cursor: 'pointer', padding: '0 2px' }}>×</button>
    </div>
  );
}
