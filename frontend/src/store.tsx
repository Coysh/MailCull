import React, { createContext, useCallback, useContext, useReducer, useEffect, useRef } from 'react';
import type { Sender, Screen, SettingsSection, ScanStatus, AuthStatus, ActionResult, Decision, Toast } from './types';
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
  /** Most recent scan that finished successfully (may be older than scanStatus) */
  lastCompletedScan: ScanStatus | null;
  lastResults: ActionResult[];
  /** The first-run landing decision (Scan vs Review) has been made */
  landed: boolean;
  toasts: Toast[];
  settings: {
    muteAction: 'archive' | 'trash';
    snoozeDays: number;
    ollamaUrl: string;
    ollamaModel: string;
    scanDays: number;
    browserInstalled: boolean;
    graceDays: number;
    dbPath: string;
  };
}

export interface DecisionItem { id: string; decision: Decision }

type PrefKey = 'muteAction' | 'snoozeDays' | 'scanDays';
const PREF_FIELD = { muteAction: 'mute_action', snoozeDays: 'snooze_days', scanDays: 'scan_since_days' } as const;

type Action =
  | { type: 'SET_SCREEN'; screen: Screen }
  | { type: 'SET_SETTINGS_SECTION'; section: SettingsSection }
  | { type: 'SET_AUTH'; status: AuthStatus }
  | { type: 'SET_AUTH_ERROR'; error: boolean }
  | { type: 'SET_SENDERS'; senders: Sender[] }
  | { type: 'SET_SENDERS_LOADING'; loading: boolean }
  | { type: 'SET_DECISIONS'; items: DecisionItem[]; clearSelection?: boolean }
  | { type: 'RESTORE_SENDERS'; senders: Sender[] }
  | { type: 'TOGGLE_SELECT'; id: string }
  | { type: 'SELECT_ALL'; ids: string[] }
  | { type: 'DESELECT_ALL' }
  | { type: 'LAND'; hasScan: boolean }
  | { type: 'ADD_TOAST'; toast: Toast }
  | { type: 'DISMISS_TOAST'; id: number }
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
  | { type: 'SET_LAST_COMPLETED_SCAN'; status: ScanStatus | null }
  | { type: 'SET_RESULTS'; results: ActionResult[] }
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
  lastCompletedScan: null,
  lastResults: [],
  landed: false,
  toasts: [],
  settings: {
    dbPath: '',
    muteAction: 'archive',
    snoozeDays: 30,
    ollamaUrl: 'http://localhost:11434',
    ollamaModel: 'llama3.2:3b',
    scanDays: 365,
    browserInstalled: false,
    graceDays: 7,
  },
};

/** Mirrors the backend: choosing Keep marks the sender kept; changing or clearing it reopens it. */
function withDecision(s: Sender, decision: Decision): Sender {
  const status = decision === 'keep' ? 'kept' : s.status === 'kept' ? 'pending' : s.status;
  return { ...s, decision, status };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_SCREEN': return { ...state, screen: action.screen };
    case 'SET_SETTINGS_SECTION': return { ...state, settingsSection: action.section };
    case 'SET_AUTH': return { ...state, authStatus: action.status, screen: action.status.connected ? (state.screen === 'not_connected' ? 'review' : state.screen) : 'not_connected' };
    case 'SET_AUTH_ERROR': return { ...state, authError: action.error };
    case 'SET_SENDERS': return { ...state, senders: action.senders, sendersLoading: false };
    case 'SET_SENDERS_LOADING': return { ...state, sendersLoading: action.loading };
    case 'SET_DECISIONS': {
      const byId = new Map(action.items.map(i => [i.id, i.decision]));
      return {
        ...state,
        senders: state.senders.map(s => byId.has(s.id) ? withDecision(s, byId.get(s.id)!) : s),
        selectedIds: action.clearSelection ? new Set() : state.selectedIds,
      };
    }
    case 'RESTORE_SENDERS': {
      const byId = new Map(action.senders.map(s => [s.id, s]));
      return { ...state, senders: state.senders.map(s => byId.get(s.id) ?? s) };
    }
    case 'LAND': {
      if (state.landed) return state;
      // First run: nothing to review until a scan has finished, so start on Scan
      const goScan = !action.hasScan && state.screen === 'review';
      return { ...state, landed: true, screen: goScan ? 'scanning' : state.screen };
    }
    case 'ADD_TOAST': return { ...state, toasts: [...state.toasts.slice(-3), action.toast] };
    case 'DISMISS_TOAST': return { ...state, toasts: state.toasts.filter(t => t.id !== action.id) };
    case 'TOGGLE_SELECT': {
      const n = new Set(state.selectedIds);
      n.has(action.id) ? n.delete(action.id) : n.add(action.id);
      return { ...state, selectedIds: n };
    }
    case 'SELECT_ALL': return { ...state, selectedIds: new Set(action.ids) };
    case 'DESELECT_ALL': return { ...state, selectedIds: new Set() };
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
    case 'SET_SCAN_STATUS':
      return { ...state, scanStatus: action.status, ...(action.status?.phase === 'done' ? { lastCompletedScan: action.status } : {}) };
    case 'SET_LAST_COMPLETED_SCAN': return { ...state, lastCompletedScan: action.status };
    case 'SET_RESULTS': return { ...state, lastResults: action.results };
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
  startScan: () => Promise<void>;
  scanRunning: boolean;
  /** Optimistically set decisions; reverts and toasts if the save fails. */
  decide: (items: DecisionItem[], opts?: { clearSelection?: boolean; toast?: boolean }) => void;
  pushToast: (t: Omit<Toast, 'id'>) => void;
  /** Set a persisted preference (Behaviour / Scanning settings). */
  setPref: <K extends PrefKey>(key: K, value: State['settings'][K]) => void;
}

export const isScanRunning = (s: ScanStatus | null) => !!s && s.phase !== 'done' && s.phase !== 'error';

const StoreCtx = createContext<Ctx>(null!);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;
  const toastId = useRef(0);

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

  const scanRunning = isScanRunning(state.scanStatus);

  const pushToast = useCallback((t: Omit<Toast, 'id'>) => {
    dispatch({ type: 'ADD_TOAST', toast: { ...t, id: ++toastId.current } });
  }, []);

  const decide = useCallback<Ctx['decide']>((items, opts = {}) => {
    if (!items.length) return;
    const ids = new Set(items.map(i => i.id));
    const before = stateRef.current.senders.filter(s => ids.has(s.id));
    dispatch({ type: 'SET_DECISIONS', items, clearSelection: opts.clearSelection });
    api.postDecisions(items.map(i => ({ sender_id: i.id, decision: i.decision }))).catch(err => {
      console.error(err);
      dispatch({ type: 'RESTORE_SENDERS', senders: before });
      pushToast({ tone: 'error', text: `Couldn't save ${items.length === 1 ? 'that decision' : `${items.length} decisions`} — reverted. ${String(err).slice(0, 80)}` });
    });
    // Keep needs no Confirm step, so give a one-click way back
    if (opts.toast !== false && items.length === 1 && items[0].decision === 'keep' && before[0]) {
      const { id } = items[0];
      pushToast({ tone: 'info', text: `Kept ${before[0].from_name}`, actionLabel: 'Undo',
        onAction: () => decide([{ id, decision: null }], { toast: false }) });
    }
  }, [pushToast]);

  const setPref = useCallback<Ctx['setPref']>((key, value) => {
    dispatch({ type: 'SET_SETTING', key, value });
    api.patchSettings({ [PREF_FIELD[key]]: value }).catch(err => {
      console.error(err);
      pushToast({ tone: 'error', text: `Couldn't save that setting: ${String(err).slice(0, 80)}` });
    });
  }, [pushToast]);

  const startScan = useCallback(async () => {
    const { scan_id } = await api.postStartScan(state.settings.scanDays);
    dispatch({ type: 'SET_SCAN_ID', id: scan_id });
    dispatch({ type: 'SET_SCAN_STATUS', status: await api.getScanStatus(scan_id) });
  }, [state.settings.scanDays]);

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
      dispatch({ type: 'SET_SETTING', key: 'muteAction', value: s.mute_action });
      dispatch({ type: 'SET_SETTING', key: 'snoozeDays', value: s.snooze_days });
      dispatch({ type: 'SET_SETTING', key: 'dbPath', value: s.db_path });
      dispatch({ type: 'SET_DRY_RUN', value: s.dry_run });
    }).catch(() => {});
  }, []);

  // Load senders when connected and on review screen
  useEffect(() => {
    if (state.authStatus.connected && ['review', 'confirm', 'results', 'scanning'].includes(state.screen)) {
      reloadSenders();
    }
  }, [state.authStatus.connected, state.screen, reloadSenders]);

  // Check Ollama reachability
  useEffect(() => {
    checkOllama();
    const id = setInterval(checkOllama, 30_000);
    return () => clearInterval(id);
  }, [state.settings.ollamaUrl, checkOllama]);

  // Load the most recent scan on connect, and re-attach if one is still running
  useEffect(() => {
    if (!state.authStatus.connected) return;
    Promise.all([api.getLastCompletedScan(), api.getLatestScan()]).then(([done, latest]) => {
      dispatch({ type: 'SET_LAST_COMPLETED_SCAN', status: done });
      dispatch({ type: 'SET_SCAN_STATUS', status: latest });
      if (latest && isScanRunning(latest)) dispatch({ type: 'SET_SCAN_ID', id: latest.id });
      dispatch({ type: 'LAND', hasScan: !!done || (!!latest && isScanRunning(latest)) });
    }).catch(() => dispatch({ type: 'LAND', hasScan: true }));
  }, [state.authStatus.connected]);

  // Poll a running scan from any screen (the sidebar shows its progress)
  useEffect(() => {
    if (!state.scanId || !scanRunning) return;
    const id = setInterval(() => {
      api.getScanStatus(state.scanId!).then(status => {
        dispatch({ type: 'SET_SCAN_STATUS', status });
        if (status.phase === 'done') reloadSenders();
      }).catch(() => {});
    }, 1500);
    return () => clearInterval(id);
  }, [state.scanId, scanRunning, reloadSenders]);

  return (
    <StoreCtx.Provider value={{ state, dispatch, filtered, decided, reloadSenders, checkOllama, startScan, scanRunning, decide, pushToast, setPref }}>
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
