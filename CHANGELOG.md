# Changelog

All notable changes to MailCull are documented here.

---

## [Unreleased]

### Unsubscribe overhaul
- **Fallback chain.** Each unsubscribe tries every method the sender offers until one works: one-click POST → mailto → headless browser on the unsubscribe page → plain GET → manual link. Results show each attempt, e.g. `one-click: HTTP 405 → mailto: sent to …`.
- **Headless browser (Playwright).** Opens link-only unsubscribe pages and clicks the opt-out control. It handles multi-step confirmations and "unsubscribe from all" checkboxes, and fills an empty email field. It never clicks subscribe, keep, cancel or login controls. Optional extra: `pip install ".[browser]"` plus `playwright install chromium`. It's included in the Docker image.
- **Unsubscribe links from email bodies.** Senders with no `List-Unsubscribe` header get their newest message body checked locally for an unsubscribe link (new capability: *Link in body*). Bodies are never stored. Toggle with `BODY_LINK_SCAN`.
- **"Still sending" verification.** Scans flag senders that keep mailing `UNSUB_GRACE_DAYS` (default 7) after an unsubscribe. The review list shows a banner with **Mute all**. Earlier unsubscribes are backfilled from the action log so they're covered too.
- **Fix: stale and mismatched unsubscribe links.** Links from every message were merged, and the executor POSTed an arbitrary one, which was often expired or not a one-click URL. This caused the HTTP 403/405 failures. Senders now keep the methods from their newest message, ordered by Gmail `internalDate`, and capability and links always update together.
- **Fix: mailto bodies corrupted.** `parse_qs` turned `+` into spaces, which broke token bodies (e.g. Cinch). mailto URIs are now parsed per RFC 6068.
- **Fix: mailto always failed without `gmail.send`.** The scope is now requested by default, and a missing grant shows a *Re-authorise* prompt instead of a silent 403.
- **Fix: one-click robustness.** Requests now send a browser User-Agent and no cookies. They retry 429/5xx and timeouts, re-POST on 307/308, and check the landing page after a 30x.
- **Fix: senders re-executed every batch.** Handled senders are skipped unless you use **Retry** (`force`). Dry runs no longer change a sender's status.
- **Mark done persists.** Manual link completions are saved and tracked by verification.

### Repo review fixes
- Archive and delete now paginate. They previously stopped at the first 500 messages.
- **Undo** works for mute (deletes the filter), archive, delete (untrash) and the transactional label. **Retry** works for failures.
- Settings for "Mute creates" and snooze length now reach the backend. The unimplemented "Permanent delete" option was removed.
- *Mark transactional* applies a real `MailCull/Transactional` Gmail label. Snooze hides the sender until the date passes.
- The OAuth token is now actually Fernet-encrypted at rest; the docs already claimed this. Legacy plaintext tokens are migrated on load. The OAuth `state` is validated, and revoke uses an async POST.
- Concurrent scans are rejected (409). Re-classify no longer overwrites scan data.
- The Ollama status check goes through the backend (`/api/settings/ollama-status`), so LAN Ollama hosts work. The top-bar button re-checks instead of faking the state.
- Docker: dependency install failures are no longer swallowed (`|| true`), dev dependencies are no longer shipped, and the built frontend is actually served. It was looked up at `/frontend/dist`.
- Confirm screen: one failing sender no longer aborts the rest of the batch. The mute preview shows the real filter (`from:address`).

### Added
- **Execute progress bar** — The confirm screen now executes senders one at a time and renders a real-time teal progress bar (`N of M complete`) so you can see work happening rather than staring at a spinner.
- **Senders removed after execution** — Once a batch completes, all processed senders are removed from the review and confirm queues immediately. You no longer need to manually dismiss or re-filter them.

### Changed
- **Dry run moved to `.env`-only** — The in-app "Global dry run" toggle has been removed. `DRY_RUN` is now set exclusively in `.env` and read by the backend at startup. This prevents accidental mid-session disabling and makes the safety posture explicit at deploy time. A `DRY RUN` badge in the TopBar is shown whenever it is active.
- **Execute button disabled during execution** — The "← Back" and "Execute N actions" buttons are now disabled while a batch is running to prevent duplicate submits.

### Fixed
- **Dry run flag was silently ignored** — The frontend `dryRun` toggle previously had no effect on the backend; the backend always read `settings.dry_run` from the cached config singleton. Now the backend correctly reflects the `.env` value, and the frontend no longer passes a stale in-memory flag.
- **Server must be restarted to pick up `.env` changes** — `get_settings()` uses a module-level singleton that is initialised once at startup. Changing `.env` without restarting the server had no effect. This is now documented behaviour; restart the server after editing `.env`.

---

## [0.1.0] — Initial release

### Added
- Gmail OAuth 2.0 flow (Desktop app credentials, loopback redirect)
- Header-only reads via `users.messages.get` with `format=metadata` — no message bodies ever fetched
- Batch Gmail API fetches (up to 100 messages per HTTP request)
- Sender aggregation: groups by address, normalises casing, tracks frequency, last-seen date, and message count
- Ollama-powered classification with JSON schema output; category + suggested action per sender
- Heuristic fallback when Ollama is unreachable (uses `List-Unsubscribe` presence, frequency, subject patterns)
- Action types: unsubscribe (one-click RFC 8058 POST / link / mailto), mute (Gmail filter), archive, delete (trash or permanent), keep, transactional, snooze
- Confirm screen: grouped batch preview before any action is taken
- Results screen: per-sender outcome with "needs link" walkthrough for manual unsubscribes
- Undo support for one-click unsubscribes (re-subscribes via the same endpoint)
- SQLite persistence (aiosqlite, WAL mode): senders, scan records, action log
- `DRY_RUN` mode: all write paths return synthetic success and log identically to real results
- React + TypeScript frontend with keyboard-first triage (j/k navigation, e/u/m/d/x shortcuts)
- Docker + docker-compose packaging with persistent data volume
- 33 unit tests: header parsing, sender aggregation, action-method selection
