export type Capability = 'one_click' | 'mailto' | 'link' | 'body_link' | 'none';
export type Category = 'Marketing' | 'Newsletter' | 'Transactional' | 'Social' | 'Spam' | 'Personal';
export type Decision = 'keep' | 'unsubscribe' | 'mute' | 'delete' | 'archive' | 'transactional' | 'snooze' | null;
export type Status =
  | 'pending' | 'kept' | 'unsubscribed' | 'unsub_pending' | 'still_sending' | 'needs_link'
  | 'muted' | 'deleted' | 'archived' | 'snoozed' | 'failed' | 'transactional';

/** Already handled — hidden from the default review list and skipped on execute. */
export const DONE_STATUSES: ReadonlySet<Status> = new Set<Status>([
  'kept', 'unsubscribed', 'unsub_pending', 'muted', 'deleted', 'archived', 'transactional', 'snoozed',
]);

export interface Sender {
  id: string;
  from_name: string;
  from_address: string;
  domain: string;
  message_count: number;
  first_seen: string;
  last_seen: string;
  sample_subjects: string[];
  capability: Capability;
  unsubscribe_links: string[];
  one_click_url: string | null;
  mailto_links: string[];
  http_links: string[];
  unsubscribe_source: 'header' | 'body' | null;
  category: Category | null;
  rationale: string | null;
  suggested_action: Decision;
  classification_degraded: boolean;
  decision: Decision;
  status: Status;
  unsubscribed_at: string | null;
  unsub_method: string | null;
  snooze_until: string | null;
}

export interface ScanStatus {
  id: number;
  started_at: string;
  finished_at: string | null;
  since_days: number;
  total_messages: number;
  total_senders: number;
  phase: string;
  progress_pct: number;
  status_detail: string | null;
  error: string | null;
}

export interface AuthStatus {
  connected: boolean;
  account: string | null;
  scopes: string[];
  missing_scopes?: string[];
}

export interface ActionPreview {
  sender_id: string;
  from_name: string;
  from_address: string;
  decision: Decision;
  method: string;
  description: string;
  can_automate: boolean;
  needs_manual: boolean;
}

export interface ActionResult {
  sender_id: string;
  from_name: string;
  from_address: string;
  decision: Decision;
  method: string;
  status: Status;
  detail: string;
  can_undo: boolean;
  link: string | null;
  error: string | null;
  http_status: number | null;
  attempts: string[];
  action_id: number | null;
  skipped: boolean;
}

export type Screen = 'not_connected' | 'inbox' | 'review' | 'scanning' | 'confirm' | 'results' | 'settings';

export interface InboxMessage {
  message_id: string;
  received_at: string;
  unread: boolean;
  from_name: string;
  from_address: string;
  subject: string;
  /** Unsubscribe capability advertised by this specific message */
  capability: Capability;
  sender_id: string;
  /** null = sender hasn't been seen by a scan yet */
  sender_status: Status | null;
  sender_decision: Decision;
  message_count: number | null;
}

export interface InboxPage { messages: InboxMessage[]; next_page_token: string | null; }
export type SettingsSection = 'connection' | 'scanning' | 'ai' | 'behaviour' | 'data' | 'appearance' | 'danger';
