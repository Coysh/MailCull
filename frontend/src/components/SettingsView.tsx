import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import type { SettingsSection } from '../types';
import * as api from '../api';

const NAV_ITEMS: [SettingsSection, string][] = [
  ['connection', 'Connection'],
  ['scanning', 'Scanning'],
  ['ai', 'AI · Ollama'],
  ['behaviour', 'Behaviour'],
  ['data', 'Data'],
  ['appearance', 'Appearance'],
  ['danger', 'Danger zone'],
];

export function SettingsView() {
  const { state, dispatch } = useStore();
  const sec = state.settingsSection;

  const setSec = (s: SettingsSection) => dispatch({ type: 'SET_SETTINGS_SECTION', section: s });

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Settings sidebar */}
      <div style={{ width: 178, borderRight: `1px solid ${C.border}`, background: '#101216', padding: '14px 0', flexShrink: 0, overflowY: 'auto' }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.1em', color: '#3C414B', padding: '0 16px 8px' }}>SETTINGS</div>
        {NAV_ITEMS.map(([id, label]) => {
          const active = sec === id;
          const danger = id === 'danger';
          return (
            <div key={id} onClick={() => setSec(id)}
              style={{ padding: '7px 16px', cursor: 'pointer', borderLeft: `2px solid ${active ? (danger ? C.red : C.teal) : 'transparent'}`, background: active ? (danger ? 'transparent' : C.tealBg) : 'transparent' }}
              onMouseEnter={e => { if (!active) (e.currentTarget as HTMLDivElement).style.background = C.panel2; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = active ? (danger ? 'transparent' : C.tealBg) : 'transparent'; }}
            >
              <span style={{ fontSize: 12, color: danger ? (active ? C.redBright : '#9C6266') : (active ? C.text : '#8990A0'), fontWeight: active ? 600 : 500 }}>{label}</span>
            </div>
          );
        })}
      </div>

      {/* Settings content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }}>
        <div style={{ maxWidth: 620 }}>
          {sec === 'connection' && <ConnectionSection />}
          {sec === 'scanning' && <ScanningSection />}
          {sec === 'ai' && <AISection />}
          {sec === 'behaviour' && <BehaviourSection />}
          {sec === 'data' && <DataSection />}
          {sec === 'appearance' && <AppearanceSection />}
          {sec === 'danger' && <DangerSection />}
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 3 }}>{title}</h2>
      <p style={{ fontSize: 12, color: C.textFaint, marginBottom: 18 }}>{subtitle}</p>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, padding: '13px 15px' }}>{children}</div>;
}

function Row({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3, padding: '13px 15px' }}>{children}</div>;
}

function Toggle({ on, onChange, danger }: { on: boolean; onChange: () => void; danger?: boolean }) {
  const c = danger ? C.amber : C.teal;
  return (
    <div onClick={onChange} style={{ width: 34, height: 19, borderRadius: 10, background: on ? c : '#2A2E36', position: 'relative', cursor: 'pointer', transition: 'background .15s', flexShrink: 0 }}>
      <div style={{ width: 15, height: 15, borderRadius: '50%', background: '#fff', position: 'absolute', top: 2, left: on ? 17 : 2, transition: 'left .15s' }} />
    </div>
  );
}

function Sel({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{ background: C.panel2, border: `1px solid ${C.border}`, color: C.text, fontSize: 12, padding: '5px 9px', borderRadius: 2, cursor: 'pointer' }}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

function GhostBtn({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{ background: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 12, padding: '6px 13px', borderRadius: 2, cursor: 'pointer' }}
      onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.borderHov; b.style.color = C.text; }}
      onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.borderColor = C.border; b.style.color = C.textMuted; }}
    >{label}</button>
  );
}

function DangerBtn({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{ background: 'transparent', border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, padding: '6px 13px', borderRadius: 2, cursor: 'pointer' }}
      onMouseEnter={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = C.redBg; b.style.borderColor = C.red; }}
      onMouseLeave={e => { const b = e.currentTarget as HTMLButtonElement; b.style.background = 'transparent'; b.style.borderColor = C.redBorder; }}
    >{label}</button>
  );
}

function RowLabel({ title, sub }: { title: string; sub: string }) {
  return <div><div style={{ fontSize: 13, fontWeight: 500 }}>{title}</div><div style={{ fontSize: 11, color: C.textFaint }}>{sub}</div></div>;
}

// ── Section components ────────────────────────────────────────────────────────

function ConnectionSection() {
  const { state, dispatch } = useStore();
  const { account } = state.authStatus;

  const handleDisconnect = async () => {
    await api.postDisconnect();
    dispatch({ type: 'SET_AUTH', status: { connected: false, account: null, scopes: [] } });
  };

  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Connection" subtitle="Google account and OAuth grant." />
      <Card>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 11 }}>CONNECTED ACCOUNT</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 13 }}>
          <span style={{ width: 8, height: 8, background: C.green, borderRadius: '50%' }} />
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: C.text }}>{account ?? '—'}</span>
          <span style={{ fontSize: 11, color: C.textFaint, marginLeft: 'auto' }}>Google Workspace</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', borderTop: `1px solid ${C.borderSub}` }}>
          {state.authStatus.scopes.map(scope => (
            <div key={scope} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: `1px solid ${C.borderSub}` }}>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted, flex: 1 }}>{scope.split('/').pop()}</span>
              <span style={{ fontSize: 11, color: C.green }}>✓ granted</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          <GhostBtn label="Re-authorise" onClick={async () => { const { consent_url } = await api.getAuthStartUrl(); window.location.href = consent_url; }} />
        </div>
      </Card>
    </div>
  );
}

function ScanningSection() {
  const { state, dispatch } = useStore();
  const setS = (k: keyof typeof state.settings, v: unknown) => dispatch({ type: 'SET_SETTING', key: k, value: v });
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Scanning" subtitle="What MailCull reads, and how far back." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Row><RowLabel title="Time window" sub="How far back to scan" />
          <Sel value={String(state.settings.scanDays)} onChange={v => setS('scanDays', Number(v))} options={[['30','Last 30 days'],['90','Last 90 days'],['180','Last 180 days'],['365','Last 365 days']]} />
        </Row>
        <Row><RowLabel title="Re-scan now" sub="Fetch messages since last scan" />
          <GhostBtn label="Scan now" onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'scanning' })} />
        </Row>
      </div>
    </div>
  );
}

function AISection() {
  const { state, dispatch } = useStore();
  const setS = (k: keyof typeof state.settings, v: unknown) => dispatch({ type: 'SET_SETTING', key: k, value: v });

  const saveUrl = () => api.patchSettings({ ollama_base_url: state.settings.ollamaUrl }).catch(() => {});
  const saveModel = () => api.patchSettings({ ollama_model: state.settings.ollamaModel }).catch(() => {});
  const testConnection = () => {
    dispatch({ type: 'SET_OLLAMA_UP', up: false, checking: true });
    fetch(state.settings.ollamaUrl + '/api/tags', { signal: AbortSignal.timeout(5000) })
      .then(r => dispatch({ type: 'SET_OLLAMA_UP', up: r.ok }))
      .catch(() => dispatch({ type: 'SET_OLLAMA_UP', up: false }));
  };

  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="AI · Ollama" subtitle="Local model used to classify senders and write rationales." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Card>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 9 }}>Base URL</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input type="text" value={state.settings.ollamaUrl} onChange={e => setS('ollamaUrl', e.target.value)}
              style={{ flex: 1, background: C.panel2, border: `1px solid ${C.border}`, color: C.text, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, padding: '7px 9px', borderRadius: 2, outline: 'none' }}
              onFocus={e => (e.currentTarget as HTMLInputElement).style.borderColor = C.teal}
              onBlur={e => { (e.currentTarget as HTMLInputElement).style.borderColor = C.border; saveUrl(); }}
            />
            <GhostBtn label="Test" onClick={testConnection} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 10 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: state.ollamaUp ? C.green : C.amber }} />
            <span style={{ fontSize: 11, color: state.ollamaUp ? C.green : C.amber }}>
              {state.ollamaUp ? `Connected · ${state.settings.ollamaModel}` : `Unreachable at ${state.settings.ollamaUrl} — using heuristic fallback`}
            </span>
          </div>
        </Card>
        <Card>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 9 }}>Model</div>
          <input type="text" value={state.settings.ollamaModel} onChange={e => setS('ollamaModel', e.target.value)}
            placeholder="e.g. qwen2.5:7b, llama3.2:3b, mistral:7b"
            style={{ width: '100%', boxSizing: 'border-box', background: C.panel2, border: `1px solid ${C.border}`, color: C.text, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, padding: '7px 9px', borderRadius: 2, outline: 'none' }}
            onFocus={e => (e.currentTarget as HTMLInputElement).style.borderColor = C.teal}
            onBlur={e => { (e.currentTarget as HTMLInputElement).style.borderColor = C.border; saveModel(); }}
          />
          <div style={{ fontSize: 11, color: C.textFaint, marginTop: 7 }}>Any model pulled in Ollama. Changes apply to the next scan.</div>
        </Card>
        <Row><RowLabel title="Heuristic fallback" sub="Use rules when Ollama is unreachable" />
          <Toggle on={state.settings.heuristicFallback} onChange={() => setS('heuristicFallback', !state.settings.heuristicFallback)} />
        </Row>
      </div>
    </div>
  );
}

function BehaviourSection() {
  const { state, dispatch } = useStore();
  const setS = (k: keyof typeof state.settings, v: unknown) => dispatch({ type: 'SET_SETTING', key: k, value: v });
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Behaviour" subtitle="How actions are executed and confirmed." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Row><RowLabel title="Require confirm step" sub="Always show the preview before executing" />
          <Toggle on={state.settings.confirmStep} onChange={() => setS('confirmStep', !state.settings.confirmStep)} />
        </Row>
        <Row><RowLabel title="Mute creates" sub="Gmail filter for future mail" />
          <Sel value={state.settings.muteAction} onChange={v => setS('muteAction', v)} options={[['archive','Skip inbox (archive)'],['trash','Move to Trash']]} />
        </Row>
        <Row><RowLabel title="Delete does" sub="For 'delete existing mail'" />
          <Sel value={state.settings.deleteMode} onChange={v => setS('deleteMode', v)} options={[['trash','Move to Trash'],['permanent','Permanent delete']]} />
        </Row>
        <Row><RowLabel title="Snooze default" sub="Re-surface snoozed senders after" />
          <Sel value={String(state.settings.snoozeDays)} onChange={v => setS('snoozeDays', Number(v))} options={[['7','7 days'],['14','14 days'],['30','30 days'],['90','90 days']]} />
        </Row>
      </div>
    </div>
  );
}

function DataSection() {
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Data" subtitle="Local database and exports." />
      <Card>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 10 }}>DATABASE</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted }}>/data/mailcull.db</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <GhostBtn label="Export JSON" />
          <GhostBtn label="Export CSV" />
        </div>
      </Card>
    </div>
  );
}

function AppearanceSection() {
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Appearance" subtitle="Theme and table density." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Row><RowLabel title="Theme" sub="Dark is the only console theme for now" />
          <Sel value="dark" onChange={() => {}} options={[['dark','Dark (console)']]} />
        </Row>
        <Row><RowLabel title="Row density" sub="Compact fits more senders per screen" />
          <Sel value="compact" onChange={() => {}} options={[['compact','Compact'],['comfortable','Comfortable']]} />
        </Row>
      </div>
    </div>
  );
}

function DangerSection() {
  const { dispatch } = useStore();
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 3, color: C.redBright }}>Danger zone</h2>
      <p style={{ fontSize: 12, color: C.textFaint, marginBottom: 18 }}>Irreversible. These do not touch already-sent actions.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '13px 15px' }}>
          <RowLabel title="Disconnect account" sub="Revoke OAuth token, clear credentials" />
          <DangerBtn label="Disconnect" onClick={async () => { await api.postDisconnect(); dispatch({ type: 'SET_AUTH', status: { connected: false, account: null, scopes: [] } }); }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '13px 15px' }}>
          <RowLabel title="Wipe local data" sub="Delete the local database. Gmail is untouched." />
          <DangerBtn label="Wipe data" />
        </div>
      </div>
    </div>
  );
}
