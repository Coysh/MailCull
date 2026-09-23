import React, { createContext, useCallback, useContext, useReducer, useEffect } from 'react';
import type { Sender, Screen, SettingsSection, ScanStatus, AuthStatus, ActionResult, Decision } from './types';
import { DONE_STATUSES } from './types';
import * as api from './api';

interface State {
  screen: Screen;
  settingsSection: SettingsSection;
  authStatus: AuthStatus;
  authError: boolean;
  senders: Sender[];
  sendersLoading: boolean;
  selectedIds: Set<string>;
  expandedId: string | null;
  focusedIdx: number;
  filterCategory: string;
  filterCapability: string;
  filterDecision: string;
  /** 'active' hides senders that are already handled */
  filterStatus: string;
  sortBy: 'count' | 'sender' | 'last';
  sortDir: 'asc' | 'desc';
  showShortcuts: boolean;
  dryRun: boolean;
  ollamaUp: boolean;
  ollamaChecking: boolean;
  scanId: number | null;
  scanStatus: ScanStatus | null;
  lastResults: ActionResult[];
  needsLinkDoneIds: Set<string>;
  settings: {
    confirmStep: boolean;
    heuristicFallback: boolean;
    muteAction: 'archive' | 'trash';
    snoozeDays: number;
    ollamaUrl: string;
    ollamaModel: string;
    scanDays: number;
    browserInstalled: boolean;
    graceDays: number;
  };
}

type Action =
  | { type: 'SET_SCREEN'; screen: Screen }
  | { type: 'SET_SETTINGS_SECTION'; section: SettingsSection }
  | { type: 'SET_AUTH'; status: AuthStatus }
  | { type: 'SET_AUTH_ERROR'; error: boolean }
  | { type: 'SET_SENDERS'; senders: Sender[] }
  | { type: 'SET_SENDERS_LOADING'; loading: boolean }
  | { type: 'UPDATE_SENDER_DECISION'; id: string; decision: Decision }
  | { type: 'TOGGLE_SELECT'; id: string }
  | { type: 'SELECT_ALL'; ids: string[] }
  | { type: 'DESELECT_ALL' }
  | { type: 'BULK_DECIDE'; ids: string[]; decision: Decision }
  | { type: 'SET_EXPANDED'; id: string | null }
  | { type: 'SET_FOCUSED'; idx: number }
  | { type: 'SET_FILTER_CATEGORY'; v: string }
  | { type: 'SET_FILTER_CAPABILITY'; v: string }
  | { type: 'SET_FILTER_DECISION'; v: string }
  | { type: 'SET_FILTER_STATUS'; v: string }
  | { type: 'UPDATE_SENDER'; sender: Sender }
  | { type: 'UPDATE_RESULT'; senderId: string; patch: Partial<ActionResult> }
  | { type: 'SET_SORT'; by: 'count' | 'sender' | 'last' }
  | { type: 'TOGGLE_SHORTCUTS' }
  | { type: 'SET_DRY_RUN'; value: boolean }
  | { type: 'SET_OLLAMA_UP'; up: boolean; checking?: boolean }
  | { type: 'SET_SCAN_ID'; id: number | null }
  | { type: 'SET_SCAN_STATUS'; status: ScanStatus | null }
  | { type: 'SET_RESULTS'; results: ActionResult[] }
  | { type: 'TOGGLE_NEEDS_LINK_DONE'; id: string }
  | { type: 'SET_SETTING'; key: keyof State['settings']; value: unknown };

const initialState: State = {
  screen: 'not_connected',
  settingsSection: 'connection',
  authStatus: { connected: false, account: null, scopes: [] },
  authError: window.location.search.includes('auth_error=1'),
  senders: [],
  sendersLoading: false,
  selectedIds: new Set(),
  expandedId: null,
  focusedIdx: 0,
  filterCategory: 'all',
  filterCapability: 'all',
  filterDecision: 'all',
  filterStatus: 'active',
  sortBy: 'count',
  sortDir: 'desc',
  showShortcuts: false,
  dryRun: true,
  ollamaUp: false,
  ollamaChecking: false,
  scanId: null,
  scanStatus: null,
  lastResults: [],
  needsLinkDoneIds: new Set(),
  settings: {
    confirmStep: true,
    heuristicFallback: true,
    muteAction: 'archive',
    snoozeDays: 30,
    ollamaUrl: 'http://localhost:11434',
    ollamaModel: 'llama3.2:3b',
    scanDays: 365,
    browserInstalled: false,
    graceDays: 7,
  },
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_SCREEN': return { ...state, screen: action.screen };
    case 'SET_SETTINGS_SECTION': return { ...state, settingsSection: action.section };
    case 'SET_AUTH': return { ...state, authStatus: action.status, screen: action.status.connected ? (state.screen === 'not_connected' ? 'review' : state.screen) : 'not_connected' };
    case 'SET_AUTH_ERROR': return { ...state, authError: action.error };
    case 'SET_SENDERS': return { ...state, senders: action.senders, sendersLoading: false };
    case 'SET_SENDERS_LOADING': return { ...state, sendersLoading: action.loading };
    case 'UPDATE_SENDER_DECISION':
      return { ...state, senders: state.senders.map(s => s.id === action.id ? { ...s, decision: action.decision } : s) };
    case 'TOGGLE_SELECT': {
      const n = new Set(state.selectedIds);
      n.has(action.id) ? n.delete(action.id) : n.add(action.id);
      return { ...state, selectedIds: n };
    }
    case 'SELECT_ALL': return { ...state, selectedIds: new Set(action.ids) };
    case 'DESELECT_ALL': return { ...state, selectedIds: new Set() };
    case 'BULK_DECIDE': {
      const ids = new Set(action.ids);
      return {
        ...state,
        senders: state.senders.map(s => ids.has(s.id) ? { ...s, decision: action.decision } : s),
        selectedIds: new Set(),
      };
    }
    case 'SET_EXPANDED': return { ...state, expandedId: action.id };
    case 'SET_FOCUSED': return { ...state, focusedIdx: action.idx };
    case 'SET_FILTER_CATEGORY': return { ...state, filterCategory: action.v, focusedIdx: 0 };
    case 'SET_FILTER_CAPABILITY': return { ...state, filterCapability: action.v, focusedIdx: 0 };
    case 'SET_FILTER_DECISION': return { ...state, filterDecision: action.v, focusedIdx: 0 };
    case 'SET_FILTER_STATUS': return { ...state, filterStatus: action.v, focusedIdx: 0 };
    case 'UPDATE_SENDER':
      return { ...state, senders: state.senders.map(s => s.id === action.sender.id ? action.sender : s) };
    case 'UPDATE_RESULT':
      return { ...state, lastResults: state.lastResults.map(r => r.sender_id === action.senderId ? { ...r, ...action.patch } : r) };
    case 'SET_SORT': {
      const sameCol = state.sortBy === action.by;
      const newDir = sameCol ? (state.sortDir === 'desc' ? 'asc' : 'desc') : (action.by === 'count' ? 'desc' : 'asc');
      return { ...state, sortBy: action.by, sortDir: newDir };
    }
    case 'TOGGLE_SHORTCUTS': return { ...state, showShortcuts: !state.showShortcuts };
    case 'SET_DRY_RUN': return { ...state, dryRun: action.value };
    case 'SET_OLLAMA_UP': return { ...state, ollamaUp: action.up, ollamaChecking: action.checking ?? false };
    case 'SET_SCAN_ID': return { ...state, scanId: action.id };
    case 'SET_SCAN_STATUS': return { ...state, scanStatus: action.status };
    case 'SET_RESULTS': return { ...state, lastResults: action.results };
    case 'TOGGLE_NEEDS_LINK_DONE': {
      const n = new Set(state.needsLinkDoneIds);
      n.has(action.id) ? n.delete(action.id) : n.add(action.id);
      return { ...state, needsLinkDoneIds: n };
    }
    case 'SET_SETTING': return { ...state, settings: { ...state.settings, [action.key]: action.value } };
    default: return state;
  }
}

interface Ctx {
  state: State;
  dispatch: React.Dispatch<Action>;
  filtered: Sender[];
  /** Senders with a decision that still needs executing */
  decided: Sender[];
  reloadSenders: () => Promise<void>;
  checkOllama: () => void;
}

const StoreCtx = createContext<Ctx>(null!);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const filtered = filterAndSort(state);
  const decided = state.senders.filter(s => s.decision && !DONE_STATUSES.has(s.status));

  const reloadSenders = useCallback(async () => {
    dispatch({ type: 'SET_SENDERS_LOADING', loading: true });
    try {
      dispatch({ type: 'SET_SENDERS', senders: await api.getSenders() });
    } catch {
      dispatch({ type: 'SET_SENDERS_LOADING', loading: false });
    }
  }, []);

  // Checked by the backend: the browser can't reach a LAN Ollama (CORS)
  const checkOllama = useCallback(() => {
    dispatch({ type: 'SET_OLLAMA_UP', up: false, checking: true });
    api.getOllamaStatus()
      .then(r => dispatch({ type: 'SET_OLLAMA_UP', up: r.reachable }))
      .catch(() => dispatch({ type: 'SET_OLLAMA_UP', up: false }));
  }, []);

  // Poll auth status on mount
  useEffect(() => {
    api.getAuthStatus().then(status => dispatch({ type: 'SET_AUTH', status })).catch(() => {});
  }, []);

  // Load backend settings on mount
  useEffect(() => {
    api.getSettings().then(s => {
      dispatch({ type: 'SET_SETTING', key: 'ollamaUrl', value: s.ollama_base_url });
      dispatch({ type: 'SET_SETTING', key: 'ollamaModel', value: s.ollama_model });
      dispatch({ type: 'SET_SETTING', key: 'scanDays', value: s.scan_since_days });
      dispatch({ type: 'SET_SETTING', key: 'browserInstalled', value: s.browser_installed && s.browser_unsubscribe });
      dispatch({ type: 'SET_SETTING', key: 'graceDays', value: s.unsub_grace_days });
      dispatch({ type: 'SET_DRY_RUN', value: s.dry_run });
    }).catch(() => {});
  }, []);

  // Load senders when connected and on review screen
  useEffect(() => {
    if (state.authStatus.connected && (state.screen === 'review' || state.screen === 'confirm' || state.screen === 'results')) {
      reloadSenders();
    }
  }, [state.authStatus.connected, state.screen, reloadSenders]);

  // Check Ollama reachability
  useEffect(() => {
    checkOllama();
    const id = setInterval(checkOllama, 30_000);
    return () => clearInterval(id);
  }, [state.settings.ollamaUrl, checkOllama]);

  // Poll scan status when scanning
  useEffect(() => {
    if (state.screen !== 'scanning' || !state.scanId) return;
    const id = setInterval(() => {
      api.getScanStatus(state.scanId!).then(status => {
        dispatch({ type: 'SET_SCAN_STATUS', status });
        if (status.phase === 'done') {
          clearInterval(id);
          dispatch({ type: 'SET_SCREEN', screen: 'review' });
        } else if (status.phase === 'error') {
          clearInterval(id);
        }
      }).catch(() => {});
    }, 1500);
    return () => clearInterval(id);
  }, [state.screen, state.scanId]);

  return (
    <StoreCtx.Provider value={{ state, dispatch, filtered, decided, reloadSenders, checkOllama }}>
      {children}
    </StoreCtx.Provider>
  );
}

export const useStore = () => useContext(StoreCtx);

function filterAndSort(state: State): Sender[] {
  let list = state.senders.filter(s => {
    if (state.filterStatus === 'active' && DONE_STATUSES.has(s.status)) return false;
    if (state.filterStatus === 'done' && !DONE_STATUSES.has(s.status)) return false;
    if (!['active', 'done', 'all'].includes(state.filterStatus) && s.status !== state.filterStatus) return false;
    if (state.filterCategory !== 'all' && s.category !== state.filterCategory) return false;
    if (state.filterCapability !== 'all' && s.capability !== state.filterCapability) return false;
    if (state.filterDecision === 'undecided' && s.decision !== null) return false;
    if (state.filterDecision !== 'all' && state.filterDecision !== 'undecided' && s.decision !== state.filterDecision) return false;
    return true;
  });
  list.sort((a, b) => {
    let av: string | number, bv: string | number;
    if (state.sortBy === 'count') { av = a.message_count; bv = b.message_count; }
    else if (state.sortBy === 'last') { av = a.last_seen; bv = b.last_seen; }
    else { av = a.from_name.toLowerCase(); bv = b.from_name.toLowerCase(); }
    const c = av < bv ? -1 : av > bv ? 1 : 0;
    return state.sortDir === 'desc' ? -c : c;
  });
  return list;
}
