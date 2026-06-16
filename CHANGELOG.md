# Changelog

All notable changes to MailCull are documented here.

---

## [Unreleased]

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
