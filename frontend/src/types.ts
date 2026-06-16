export type Capability = 'one_click' | 'link' | 'mailto' | 'none';
export type Category = 'Marketing' | 'Newsletter' | 'Transactional' | 'Social' | 'Spam' | 'Personal';
export type Decision = 'keep' | 'unsubscribe' | 'mute' | 'delete' | 'archive' | 'transactional' | 'snooze' | null;
export type Status = 'pending' | 'kept' | 'unsubscribed' | 'needs_link' | 'muted' | 'deleted' | 'archived' | 'snoozed' | 'failed' | 'transactional';

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
  category: Category | null;
  rationale: string | null;
  suggested_action: Decision;
  classification_degraded: boolean;
  decision: Decision;
  status: Status;
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
}

export type Screen = 'not_connected' | 'review' | 'scanning' | 'confirm' | 'results' | 'settings';
export type SettingsSection = 'connection' | 'scanning' | 'ai' | 'behaviour' | 'data' | 'appearance' | 'danger';
