import React from 'react';
import { C } from './tokens';
import { useStore } from '../store';
import type { SettingsSection } from '../types';
import * as api from '../api';
import { InlineConfirm } from './InlineConfirm';
import { ollamaLocality } from '../util';

const NAV_ITEMS: [SettingsSection, string][] = [
  ['connection', 'Connection'],
  ['scanning', 'Scanning'],
  ['ai', 'AI · Ollama'],
  ['behaviour', 'Behaviour'],
  ['data', 'Data'],
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
          <span style={{ fontSize: 11, color: C.textFaint, marginLeft: 'auto' }}>
            {account && !/@(gmail|googlemail)\.com$/i.test(account) ? 'Google Workspace' : 'Personal Gmail'}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', borderTop: `1px solid ${C.borderSub}` }}>
          {state.authStatus.scopes.map(scope => (
            <div key={scope} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: `1px solid ${C.borderSub}` }}>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted, flex: 1 }}>{scope.split('/').pop()}</span>
              <span style={{ fontSize: 11, color: C.green }}>✓ granted</span>
            </div>
          ))}
        </div>
        {(state.authStatus.missing_scopes ?? []).map(scope => (
          <div key={scope} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: `1px solid ${C.borderSub}` }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted, flex: 1 }}>{scope.split('/').pop()}</span>
            <span style={{ fontSize: 11, color: C.amber }}>not granted — re-authorise</span>
          </div>
        ))}
        <div style={{ marginTop: 14 }}>
          <GhostBtn label="Re-authorise" onClick={async () => { const { consent_url } = await api.getAuthStartUrl(); window.location.href = consent_url; }} />
        </div>
      </Card>
    </div>
  );
}

function ScanningSection() {
  const { state, dispatch, scanRunning, setPref } = useStore();
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Scanning" subtitle="What MailCull reads, and how far back." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Row><RowLabel title="Time window" sub="How far back to scan" />
          <Sel value={String(state.settings.scanDays)} onChange={v => setPref('scanDays', Number(v))} options={[['30','Last 30 days'],['90','Last 90 days'],['180','Last 180 days'],['365','Last 365 days']]} />
        </Row>
        <Row><RowLabel title="Run a scan" sub="Re-reads the whole time window — large mailboxes take a while" />
          <GhostBtn label={scanRunning ? 'View progress' : 'Go to Scan'} onClick={() => dispatch({ type: 'SET_SCREEN', screen: 'scanning' })} />
        </Row>
      </div>
    </div>
  );
}

function AISection() {
  const { state, dispatch } = useStore();
  const setS = (k: keyof typeof state.settings, v: unknown) => dispatch({ type: 'SET_SETTING', key: k, value: v });

  const { checkOllama } = useStore();
  const saveUrl = () => api.patchSettings({ ollama_base_url: state.settings.ollamaUrl }).then(checkOllama).catch(console.error);
  const saveModel = () => api.patchSettings({ ollama_model: state.settings.ollamaModel }).catch(console.error);
  const testConnection = () => { saveUrl(); };

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
          {(() => {
            const { locality, host } = ollamaLocality(state.settings.ollamaUrl);
            return locality === 'remote' ? (
              <div role="note" style={{ display: 'flex', gap: 8, marginTop: 10, background: C.amberBg, border: `1px solid ${C.amberBorder}`, borderRadius: 2, padding: '8px 10px' }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 600, color: C.amber, letterSpacing: '.07em', flexShrink: 0 }}>REMOTE</span>
                <span style={{ fontSize: 11, color: C.amberDim, lineHeight: 1.5 }}>
                  {host} is not this machine. Sender names, addresses and sample subjects are sent to it for classification
                  {state.settings.ollamaUrl.startsWith('http://') ? ', unencrypted (http)' : ''}. Message bodies are never sent.
                </span>
              </div>
            ) : null;
          })()}
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
        <Row><RowLabel title="Heuristic fallback" sub="If Ollama is unreachable, header rules classify instead so a scan never blocks" />
          <span style={{ fontSize: 12, color: C.textMuted }}>Always on</span>
        </Row>
      </div>
    </div>
  );
}

function BehaviourSection() {
  const { state, setPref } = useStore();
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Behaviour" subtitle="How actions are executed. These are saved." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Row><RowLabel title="Confirm step" sub="Every batch is previewed before it runs; this can't be turned off" />
          <span style={{ fontSize: 12, color: C.textMuted }}>Always on</span>
        </Row>
        <Row><RowLabel title="Dry run" sub="Set DRY_RUN in .env and restart. Deliberately not switchable from the UI" />
          <span style={{ fontSize: 12, color: state.dryRun ? C.amber : C.green }}>{state.dryRun ? 'On: actions are simulated' : 'Off: actions are live'}</span>
        </Row>
        <Row><RowLabel title="Mute creates" sub="Gmail filter for future mail" />
          <Sel value={state.settings.muteAction} onChange={v => setPref('muteAction', v as 'archive' | 'trash')} options={[['archive','Skip inbox (archive)'],['trash','Move to Trash']]} />
        </Row>
        <Row><RowLabel title="Delete does" sub="Moves all mail from the sender to Trash (Gmail empties it after 30 days)" />
          <span style={{ fontSize: 12, color: C.textMuted }}>Move to Trash</span>
        </Row>
        <Row><RowLabel title="Unsubscribe pages" sub="Pages that need a click are opened in a hidden browser" />
          <span style={{ fontSize: 12, color: state.settings.browserInstalled ? C.green : C.amber }}>
            {state.settings.browserInstalled ? 'Headless browser ready' : 'Browser not installed — manual links'}
          </span>
        </Row>
        <Row><RowLabel title="Snooze default" sub="Re-surface snoozed senders after" />
          <Sel value={String(state.settings.snoozeDays)} onChange={v => setPref('snoozeDays', Number(v))} options={[['7','7 days'],['14','14 days'],['30','30 days'],['90','90 days']]} />
        </Row>
      </div>
    </div>
  );
}

function DataSection() {
  const { state } = useStore();
  const download = (name: string, type: string, body: string) => {
    const url = URL.createObjectURL(new Blob([body], { type }));
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  };
  const exportJson = () => download('mailcull-senders.json', 'application/json', JSON.stringify(state.senders, null, 2));
  const exportCsv = () => {
    const cols = ['from_name', 'from_address', 'message_count', 'last_seen', 'category', 'capability', 'decision', 'status', 'unsubscribed_at', 'unsub_method'] as const;
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = state.senders.map(s => cols.map(c => esc(s[c])).join(','));
    download('mailcull-senders.csv', 'text/csv', [cols.join(','), ...rows].join('\n'));
  };
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <SectionHeader title="Data" subtitle="Local database and exports." />
      <Card>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: '.08em', color: C.textDimmer, marginBottom: 10 }}>DATABASE</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: C.textMuted }}>{state.settings.dbPath || '—'}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <GhostBtn label="Export JSON" onClick={exportJson} />
          <GhostBtn label="Export CSV" onClick={exportCsv} />
        </div>
      </Card>
    </div>
  );
}

function DangerSection() {
  const { dispatch, reloadSenders } = useStore();
  const [error, setError] = React.useState<string | null>(null);
  const wipe = async () => {
    setError(null);
    try { await api.postWipe(); await reloadSenders(); } catch (err) { setError(String(err)); }
  };
  const disconnect = async () => {
    setError(null);
    try { await api.postDisconnect(); dispatch({ type: 'SET_AUTH', status: { connected: false, account: null, scopes: [] } }); }
    catch (err) { setError(String(err)); }
  };
  return (
    <div style={{ animation: 'fadeIn .14s ease' }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 3, color: C.redBright }}>Danger zone</h2>
      <p style={{ fontSize: 12, color: C.textFaint, marginBottom: 18 }}>Irreversible. These do not touch already-sent actions.</p>
      {error && (
        <div role="alert" style={{ background: C.redBg, border: `1px solid ${C.redBorder}`, color: C.redBright, fontSize: 12, borderRadius: 3, padding: '9px 13px', marginBottom: 10 }}>{error}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '13px 15px' }}>
          <RowLabel title="Disconnect account" sub="Revoke OAuth token, clear credentials" />
          <InlineConfirm label="Disconnect" confirmLabel="Revoke & disconnect"
            prompt="This revokes MailCull's Google access. You'll need to sign in again." onConfirm={disconnect} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, background: C.panel, border: `1px solid ${C.redBorder}`, borderRadius: 3, padding: '13px 15px' }}>
          <RowLabel title="Wipe local data" sub="Delete the local database. Gmail is untouched." />
          <InlineConfirm label="Wipe data" confirmLabel="Wipe everything"
            prompt="Deletes all scans, decisions and the action log, including undo history. Gmail is not touched." onConfirm={wipe} />
        </div>
      </div>
    </div>
  );
}
