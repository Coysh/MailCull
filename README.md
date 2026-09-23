# MailCull

**Self-hosted Gmail inbox triage. Reads sender metadata locally, classifies with a local AI model, lets you unsubscribe or mute in bulk — nothing leaves your machine.**

MailCull is a single-user tool for technical people who want to reclaim their inbox without handing email data to a third party. It reads the headers of your Gmail messages (From, Subject, Date, List-Unsubscribe). For senders without an unsubscribe header it also reads the newest message's body, **locally and in memory only**, to find an unsubscribe link. It runs classification through a local [Ollama](https://ollama.ai) model, and presents a dense batch-triage UI. You decide what happens; MailCull executes it.

---

## Why it exists

Existing unsubscribe tools work by reading your email on their servers and sending unsubscribe requests on your behalf. MailCull does neither. Every read goes through the Gmail API directly to your inbox. Every classification runs in a local LLM. The OAuth token never leaves the machine running MailCull. If Ollama is unreachable, a header-rules heuristic takes over so the pipeline never blocks.

---

## What it does

| Action | How |
|---|---|
| **Unsubscribe** | Tries every method the sender offers, in order, until one works: **one-click** POST (RFC 8058) → **mailto** sent from your account → **headless browser** opens the unsubscribe page and clicks the opt-out button → **manual link** as a last resort. Each attempt is shown in Results. |
| **Unsubscribe verification** | Later scans check whether mail kept arriving more than `UNSUB_GRACE_DAYS` after you unsubscribed. If it did, the sender is flagged **Still sending**, with one-click **Mute all**. |
| **Mute** | Creates a Gmail filter that archives or trashes future mail from that sender. Works for senders with no unsubscribe header at all. |
| **Archive / Delete existing mail** | Archives or trashes *all* messages from a sender (paginated, no 500-message cap). **Undo** restores them. |
| **Keep / Mark transactional / Snooze** | Transactional applies a `MailCull/Transactional` label. Snooze hides the sender until the snooze ends. |

Every action requires explicit confirmation. A real-time **progress bar** tracks each sender as it is processed. Handled senders move out of the default **To do** list, and executing again skips them (use **Retry** to force a re-run). **Dry run** is controlled via `DRY_RUN` in `.env` — set `true` during initial setup to simulate everything and verify the plan before committing. A `DRY RUN` badge appears in the header whenever it is active.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn |
| Storage | SQLite via aiosqlite |
| Gmail access | Gmail REST API v1 over OAuth 2.0 (google-api-python-client) |
| Classification | Ollama (`/api/chat` with JSON schema output); heuristic fallback |
| Frontend | React 18, TypeScript, Vite |
| Packaging | Docker, docker-compose |

---

## Screenshots

The UI is a dark, dense ops console — no gradients, no rounded cards, no consumer SaaS aesthetic. Monospace data, tabular numbers, keyboard-first triage.

```
┌─ MailCull ── review ──────────────────────────────── ollama up · tim@example.com ─ ? keys ┐
│ WORKFLOW          │ 247 senders / 18 decided / 229 pending  [All categories ▾]  [Undecided ▾] │
│ ▶ Review      229 │──────────────────────────────────────────────────────────────────────────│
│   Scan            │ ☐  SENDER              COUNT  FREQ    LAST      CATEGORY    CAPABILITY   │
│   Confirm      18 │──────────────────────────────────────────────────────────────────────────│
│   Results         │ ☐▶ Groupon             1,847  Daily   2026-06   Spam        ● One-click  │
│                   │ ☐▶ Salesforce            523  Daily   2026-06   Marketing   ● One-click  │
│ ─────────────     │ ☐▶ LinkedIn              847  Daily   2026-06   Social      ● One-click  │
│   Settings        │ ☐▶ Product Hunt          289  Daily   2026-06   Marketing   ● One-click  │
│                   │ ☐▶ The Pragmatic Eng…     34  Bi-wkly 2026-06   Newsletter  ● One-click  │
│ MAILBOX           │──────────────────────────────────────────────────────────────────────────│
│ 247 senders       │ KEYS  j/k move  ↵ expand  e keep  u unsub  m mute  d delete  x select   │
└───────────────────┴──────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- **Python 3.12+**
- **Node.js 20+** (to build the frontend, or use the pre-built Docker image)
- **A Google Cloud project** with the Gmail API enabled and an OAuth client (see setup below)
- **[Ollama](https://ollama.ai)** running locally with a model pulled — `llama3.2:3b` is a good default

---

## Google Cloud OAuth setup

This is the most important part of the setup. Read it fully before starting.

### Why "Internal" matters

Google distinguishes between **Internal** and **External** OAuth app types:

- **Internal** apps are restricted to users in your own Google Workspace organisation. They issue **long-lived refresh tokens** (no expiry under normal use) and **do not require Google verification**. This is what MailCull is designed for.
- **External** apps in Testing mode issue refresh tokens that **expire after 7 days**, meaning you'd need to re-authorise every week. Do not use External/Testing for MailCull.

If you use a personal Gmail account (not Workspace), you'll need External mode — be aware of the 7-day token limitation.

---

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **New Project**
3. Name it `MailCull` (or anything you like)
4. Click **Create** and wait for it to provision

---

### Step 2 — Enable the Gmail API

1. In your new project, go to **APIs & Services → Library**
2. Search for **Gmail API**
3. Click it, then click **Enable**

---

### Step 3 — Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Under **User Type**, select **Internal**

   > ⚠️ If you see only **External** (you're on a personal Gmail account, not Workspace), select External, add yourself as a test user, and note that refresh tokens will expire every 7 days.

3. Click **Create**
4. Fill in the required fields:
   - **App name:** `MailCull`
   - **User support email:** your email
   - **Developer contact email:** your email
5. Click **Save and Continue**

**Scopes page:** Click **Add or Remove Scopes** and add:

| Scope | Purpose |
|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | Read message headers |
| `https://www.googleapis.com/auth/gmail.modify` | Trash/archive mail, apply labels |
| `https://www.googleapis.com/auth/gmail.settings.basic` | Create Gmail filters (mute) |

> **Note on restricted scopes:** `gmail.modify` and `gmail.settings.basic` are classified as "restricted" by Google. For an **Internal** Workspace app, this is fine — Google does not require verification. For **External** apps, restricted scopes require Google verification (a lengthy process) unless the app stays in Testing mode.

> **Workspace admin note:** If your Workspace admin has locked down API access, they may need to allow your internal app to use restricted Gmail APIs. The admin setting is at **Admin console → Security → API controls → Trust internal, domain-owned apps**. Most Workspace setups allow this by default.

6. Click **Save and Continue** through the summary, then **Back to Dashboard**

---

### Step 4 — Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Under **Application type**, select **Desktop app**

   > Desktop app credentials use a loopback redirect (`http://localhost:PORT/api/auth/callback`), which works without a publicly accessible server. This is the correct type for a self-hosted tool.

4. Name it `MailCull local`
5. Click **Create**
6. A dialog shows your **Client ID** and **Client Secret** — copy both now, or download the JSON

You'll put these values in your `.env` file as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.

---

### Step 5 — First authorisation

When you first open MailCull and click **Sign in with Google**, it redirects you to Google's consent screen. You'll see the three scopes listed and a warning that "this app isn't verified" — for an Internal app this is expected and safe to proceed through. Click **Continue**.

After consent, Google redirects back to `http://localhost:8420/api/auth/callback`, which completes the token exchange. The refresh token is stored at `TOKEN_PATH` (default `/data/token.json`) with `0600` permissions — only the process owner can read it.

---

## Running locally

### 1. Clone and configure

```bash
git clone https://github.com/yourname/mailcull
cd mailcull
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```env
GOOGLE_OAUTH_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET
DRY_RUN=true          # keep this true until you've verified everything looks right
TOKEN_PATH=./data/token.json
DB_PATH=./data/mailcull.db
```

Create the data directory:

```bash
mkdir -p data
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,browser]"
playwright install chromium    # headless browser for unsubscribe pages (optional)

# Run from the backend directory with the .env one level up
cd ..
python -m uvicorn mailcull.main:app --host 127.0.0.1 --port 8420 --reload --app-dir backend
```

Or from inside the backend directory with an explicit env file:

```bash
cd backend
uvicorn mailcull.main:app --host 127.0.0.1 --port 8420 --reload
```

### 3. Frontend (development, with hot reload)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — API calls proxy to port 8420 automatically.

### 4. Frontend (production build, served by FastAPI)

```bash
cd frontend
npm run build
# The dist/ folder is picked up automatically by the FastAPI static mount
```

Open **http://localhost:8420**

---

## Running with Docker

The Docker image builds the React frontend and installs the Python backend in one pass. The data volume persists the SQLite database and OAuth token across restarts.

```bash
# 1. Configure
cp .env.example .env
# Edit .env — fill in OAuth credentials

# 2. Build and start
docker compose up --build

# 3. Open the app
open http://localhost:8420
```

> The app binds to `127.0.0.1:8420` by default. The Docker `ports` mapping in `docker-compose.yml` also restricts to localhost. Do not expose MailCull on a public interface — it holds your Gmail OAuth token.

### Ollama with Docker

**Option A — Ollama already running on the host:**

```env
# .env
# macOS / Docker Desktop (host.docker.internal resolves to the host):
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Linux (Docker's default bridge gateway):
OLLAMA_BASE_URL=http://172.17.0.1:11434
```

On Linux, also add to the `mailcull` service in `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**Option B — Ollama as a Compose service:**

Uncomment the `ollama` block in `docker-compose.yml` and set:

```env
OLLAMA_BASE_URL=http://ollama:11434
```

Then pull a model:

```bash
docker compose exec ollama ollama pull llama3.2:3b
```

For GPU support, uncomment the `deploy.resources` block in `docker-compose.yml` (requires the NVIDIA Container Toolkit).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | *(required)* | OAuth 2.0 client ID from Google Cloud |
| `GOOGLE_OAUTH_CLIENT_SECRET` | *(required)* | OAuth 2.0 client secret |
| `TOKEN_PATH` | `/data/token.json` | Where the refresh token is persisted, Fernet-encrypted (never commit this) |
| `TOKEN_ENCRYPTION_KEY` | *(auto)* | Fernet key for the token file. If unset, a key is generated at `.token.key` next to the token (0600) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model name for classification |
| `SCAN_SINCE_DAYS` | `365` | How many days back to read (query: `newer_than:Nd`) |
| `DRY_RUN` | `true` | Simulate all actions; nothing changes in Gmail |
| `DB_PATH` | `/data/mailcull.db` | SQLite database path |
| `APP_PORT` | `8420` | Port to bind to |
| `APP_HOST` | `127.0.0.1` | Host to bind to — keep this as localhost |
| `INCLUDE_SEND_SCOPE` | `true` | Request `gmail.send` so mailto unsubscribes can be sent from your account |
| `BODY_LINK_SCAN` | `true` | During scans, look in the newest message body for an unsubscribe link when there's no header |
| `BROWSER_UNSUBSCRIBE` | `true` | Use a headless browser (Playwright/Chromium) for unsubscribe pages that need a click |
| `UNSUB_GRACE_DAYS` | `7` | Mail arriving this many days after unsubscribing flags the sender **Still sending** |

---

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

The suite covers:

- RFC 2047-encoded From headers, display names, and `List-Unsubscribe` parsing (folding, `&amp;`, bare URLs, RFC 8058 rules)
- Sender aggregation. The newest message's unsubscribe methods win, whatever order messages arrive in.
- mailto parsing (keeps `+` and JSON token bodies intact)
- One-click POST against a local HTTP server: 2xx, 303 follow, 307 re-POST, 4xx, and 5xx retry
- The full fallback chain (one-click → mailto → page → manual), idempotency, and dry-run safety
- "Still sending" verification and rescan upserts (real SQLite)
- Body-link extraction from HTML and plain text
- Headless-browser runs against local pages: multi-step confirmations, "unsubscribe from all" checkboxes, and never clicking "Keep me subscribed". Skipped if Chromium isn't installed.

---

## Architecture

```
mailcull/
├── design/                         # Vendored design bundle (source of truth for UI)
│   └── project/MailCull.dc.html
│
├── backend/
│   ├── mailcull/
│   │   ├── main.py                 # FastAPI app + lifespan (DB init, singleton setup)
│   │   ├── config.py               # Pydantic settings (reads from .env)
│   │   ├── models.py               # Shared Pydantic models (Sender, ScanRecord, etc.)
│   │   ├── db.py                   # SQLite persistence — aiosqlite, WAL, UPSERT
│   │   ├── state.py                # App-level singletons (GmailApi, OllamaClient)
│   │   │
│   │   ├── mail_source/
│   │   │   ├── base.py             # MailSource interface — clean adapter boundary
│   │   │   └── gmail.py            # GmailApi: OAuth flow, batch reads, header parsing
│   │   │
│   │   ├── aggregator.py           # Raw messages → per-sender records
│   │   ├── ollama_client.py        # LLM classification + heuristic fallback
│   │   ├── action_executor.py      # Unsubscribe / mute / delete / undo
│   │   │
│   │   └── api/
│   │       ├── auth.py             # GET /api/auth/start, /callback, /status; POST /disconnect
│   │       ├── scan.py             # POST /api/scan, GET /api/scan/{id}
│   │       ├── senders.py          # GET /api/senders, POST /classify, POST /decisions
│   │       └── actions.py          # POST /api/actions/preview, /execute; GET /log
│   │
│   └── tests/
│       ├── fixtures/headers.py     # Raw header fixture data
│       ├── test_headers.py         # Header parsing unit tests
│       ├── test_aggregator.py      # Aggregation unit tests
│       └── test_actions.py         # Action-method selection unit tests
│
├── frontend/
│   └── src/
│       ├── App.tsx                 # Root — screen routing
│       ├── store.tsx               # useReducer global state + API polling
│       ├── api.ts                  # Typed fetch client
│       ├── types.ts                # Shared TypeScript types
│       └── components/
│           ├── tokens.ts           # Design tokens (exact values from design file)
│           ├── NotConnected.tsx    # First-run / auth-error screen
│           ├── TopBar.tsx          # 42px header with Ollama status + account badge
│           ├── Sidebar.tsx         # Nav + mailbox stats
│           ├── OllamaBanner.tsx    # Amber banner when Ollama is unreachable
│           ├── ScanView.tsx        # Progress bars, streaming results
│           ├── ReviewView.tsx      # Dense triage table, keyboard shortcuts
│           ├── ConfirmView.tsx     # Batch preview grouped by action
│           ├── ResultsView.tsx     # Per-sender outcomes, needs-link walkthrough
│           ├── SettingsView.tsx    # 7-section settings panel
│           └── ShortcutsModal.tsx  # ? overlay
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

### Key design decisions

**MailSource interface** (`mail_source/base.py`): The Gmail adapter is behind a clean abstract interface. A future IMAP adapter (for personal Gmail without the API, or other providers) can implement the same four methods without touching the pipeline.

**Metadata-first reads**: Every message is read with `format=metadata` and an explicit `metadataHeaders` list. The only exception is the newest message from each sender *without* a `List-Unsubscribe` header. That one is fetched with `format=full` so an unsubscribe link can be extracted from its body. Bodies are parsed in memory and discarded. Only the chosen URL is stored, and nothing is sent to Ollama. Set `BODY_LINK_SCAN=false` to stay strictly metadata-only.

**Freshest unsubscribe token**: Unsubscribe URLs carry per-message tokens that expire. Each sender keeps the methods from its newest message that advertised any (ordered by Gmail's `internalDate`), and never mixes links from different messages.

**Batch API**: Message IDs are fetched first (cheap list calls), then metadata is fetched in batches of up to 100 using `service.new_batch_http_request()`. This reduces round-trips by ~100× on a large mailbox.

**Ollama structured output**: Classification uses `format: <json_schema>` in the `/api/chat` request, which constrains the model's output to valid JSON. Malformed responses are detected and repaired before being applied, and any sender that can't be classified falls back to the heuristic.

**Human-in-the-loop is enforced at the API layer**: `POST /api/actions/execute` requires `confirm: true` in the body. The LLM result (`suggested_action`) is stored separately from the user decision (`decision`) — the LLM never triggers an action.

**DRY_RUN is `.env`-only**: Dry run is configured in `.env` and read by the backend at startup. There is no in-app toggle — this is intentional to prevent accidental disabling mid-session. The TopBar shows a persistent `DRY RUN` badge when active. Every write path in `ActionExecutor` checks `self._dry_run` before making any Gmail API call and returns a synthetic success result that is logged identically to a real result.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/auth/start` | Returns `{consent_url}` to redirect the user to |
| `GET` | `/api/auth/callback` | Completes OAuth exchange (loopback redirect target) |
| `GET` | `/api/auth/status` | `{connected, account, scopes, missing_scopes}` |
| `POST` | `/api/auth/disconnect` | Revokes token and clears credentials |
| `POST` | `/api/scan` | Starts a scan, returns `{scan_id}` |
| `GET` | `/api/scan/{id}` | Scan progress: phase, progress_pct, totals |
| `GET` | `/api/scan/latest/status` | Most recent scan record |
| `GET` | `/api/senders` | All senders; filterable by `category`, `capability`, `decision`, `status`; sortable by `count`, `sender`, `last` |
| `POST` | `/api/senders/{id}/manual-done` | Record a manually completed link unsubscribe |
| `POST` | `/api/senders/classify` | Re-run LLM classification on all (or specified) senders |
| `POST` | `/api/senders/decisions` | Set user decisions: `[{sender_id, decision}]` |
| `POST` | `/api/actions/preview` | Per-sender plan for a given sender list — side-effect free |
| `POST` | `/api/actions/execute` | Execute actions; requires `confirm: true`; respects `DRY_RUN`; skips handled senders unless `force: true` |
| `POST` | `/api/actions/{id}/undo` | Undo a mute, archive, delete or transactional label |
| `GET` | `/api/actions/log` | Full action log |
| `GET` | `/api/settings/ollama-status` | Server-side Ollama reachability check |
| `POST` | `/api/settings/wipe?confirm=true` | Delete local scans, senders and action log (Gmail untouched) |
| `GET` | `/api/health` | `{status, dry_run, version}` |

Full OpenAPI schema is available at `http://localhost:8420/docs` when the server is running.

---

## Security notes

- MailCull is designed for `127.0.0.1` only. The OAuth token in `TOKEN_PATH` grants full access to the Gmail scopes you authorised. Do not expose the app on a public interface.
- The token file is Fernet-encrypted and written with `0600` permissions (owner read/write only).
- The OAuth `state` parameter is checked on callback.
- The headless browser uses a fresh, cookie-less context per page. It blocks images and media, and stores nothing.
- No secrets are logged. `DRY_RUN=true` by default — you must explicitly disable it.
- The LLM sees only: sender name, address, domain, message count, sample subjects, and whether an unsubscribe method was found. No message content is ever passed to Ollama.

---

## Limitations

- **One Gmail account per instance.** MailCull is single-user by design.
- **App Passwords / IMAP not supported.** Google Workspace disables App Passwords for accounts managed by an admin. The Gmail REST API with OAuth is the only reliable path.
- **Some unsubscribe pages still need you.** The headless browser handles single- and multi-step pages, email fields and "unsubscribe from all" checkboxes. It can't handle CAPTCHAs, logins, or preference centres with per-list toggles. Those fall back to a manual link that you open and mark done.
- **"Verifying" means unconfirmed.** If the browser submitted a form but the page never confirmed it, the sender is marked *Verifying*. The next scans settle it one way or the other.
- **`mailto` unsubscribes require `gmail.send`.** It's requested by default. Tokens granted before this change must be re-authorised: the header shows a *Re-authorise* button.
- **Ollama classification quality depends on your model.** `llama3.2:3b` works well for most cases. For difficult classifications (ambiguous senders, non-English subjects), a larger model like `mistral:7b` or `qwen2.5:7b` gives better rationales.

---

## License

MIT
