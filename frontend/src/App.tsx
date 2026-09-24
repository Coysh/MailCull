import React from 'react';
import { useStore } from './store';
import { NotConnected } from './components/NotConnected';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';
import { OllamaBanner } from './components/OllamaBanner';
import { ScanView } from './components/ScanView';
import { InboxView } from './components/InboxView';
import { ReviewView } from './components/ReviewView';
import { ConfirmView } from './components/ConfirmView';
import { ResultsView } from './components/ResultsView';
import { SettingsView } from './components/SettingsView';
import { ShortcutsModal } from './components/ShortcutsModal';

export default function App() {
  const { state } = useStore();

  if (!state.authStatus.connected) {
    return <NotConnected />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0E0F12', color: '#E2E5EA', fontFamily: "'Hanken Grotesk', system-ui, sans-serif" }}>
      <TopBar />
      <OllamaBanner />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <main style={{ flex: 1, overflow: 'hidden', background: '#0E0F12', display: 'flex', flexDirection: 'column' }}>
          {state.screen === 'inbox'     && <InboxView />}
          {state.screen === 'scanning'  && <ScanView />}
          {state.screen === 'review'    && <ReviewView />}
          {state.screen === 'confirm'   && <ConfirmView />}
          {state.screen === 'results'   && <ResultsView />}
          {state.screen === 'settings'  && <SettingsView />}
        </main>
      </div>
      {state.showShortcuts && <ShortcutsModal />}
    </div>
  );
}
