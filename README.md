# MailCull

**Self-hosted Gmail inbox triage. Reads sender metadata locally, classifies with a local AI model, lets you unsubscribe or mute in bulk — nothing leaves your machine.**

MailCull is a single-user tool for technical people who want to reclaim their inbox without handing email data to a third party. It reads only the headers of your Gmail messages (From, Subject, Date, List-Unsubscribe — never the body), runs classification through a local [Ollama](https://ollama.ai) model, and presents a dense batch-triage UI. You decide what happens; MailCull executes it.

---

## Why it exists

Existing unsubscribe tools work by reading your email on their servers and sending unsubscribe requests on your behalf. MailCull does neither. Every read goes through the Gmail API directly to your inbox. Every classification runs in a local LLM. The OAuth token never leaves the machine running MailCull. If Ollama is unreachable, a header-rules heuristic takes over so the pipeline never blocks.

---

## What it does

| Action | How |
|---|---|
| **Unsubscribe (one-click)** | HTTP POST to `List-Unsubscribe-Post` endpoint (RFC 8058). Fully automated, no browser. |
| **Unsubscribe (link)** | Surfaces the link for you to open and confirm manually. |
| **Unsubscribe (mailto)** | Sends a plain-text opt-out email via the Gmail API. |
| **Mute** | Creates a Gmail filter that archives or trashes future mail from that sender. Works for senders with no unsubscribe header at all. |
| **Delete existing mail** | Batch-trashes (or permanently deletes) all messages from a sender. Reversible by default. |
| **Keep / Mark transactional / Snooze** | Local-state decisions with optional Gmail label. |

Every action requires explicit confirmation. A real-time **progress bar** tracks each sender as it is processed. Once execution completes, processed senders are removed from the review queue. **Dry run** is controlled via `DRY_RUN` in `.env` — set `true` during initial setup to simulate everything and verify the plan before committing. A `DRY RUN` badge appears in the header whenever it is active.

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
pip install -e ".[dev]"

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
| `TOKEN_PATH` | `/data/token.json` | Where the refresh token is persisted (never commit this) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model name for classification |
| `SCAN_SINCE_DAYS` | `365` | How many days back to read (query: `newer_than:Nd`) |
| `DRY_RUN` | `true` | Simulate all actions; nothing changes in Gmail |
| `DB_PATH` | `/data/mailcull.db` | SQLite database path |
| `APP_PORT` | `8420` | Port to bind to |
| `APP_HOST` | `127.0.0.1` | Host to bind to — keep this as localhost |
| `INCLUDE_SEND_SCOPE` | `false` | Request `gmail.send` to enable automated mailto unsubscribes |

---

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

33 tests covering:

- RFC 2047-encoded From headers and display names
- Bare angle-bracket addresses, Unicode display names
- `List-Unsubscribe` header parsing: one-click (RFC 8058), link, mailto, none
- RFC 8058 edge case: `List-Unsubscribe-Post` present but no HTTPS link → not one-click
- Sender aggregation: grouping by address, case normalisation, date ranges, subject capping, capability priority
- Stable sender ID generation
- Action-method selection for every decision type (keep, unsubscribe × 4 capabilities, mute, delete, transactional)

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

**Metadata-only reads**: `users.messages.get` is called with `format=metadata` and an explicit `metadataHeaders` list. Message bodies, attachments, and thread content are never fetched. The Gmail API quota for metadata reads is also significantly higher than for full reads.

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
| `GET` | `/api/auth/status` | `{connected, account, scopes}` |
| `POST` | `/api/auth/disconnect` | Revokes token and clears credentials |
| `POST` | `/api/scan` | Starts a scan, returns `{scan_id}` |
| `GET` | `/api/scan/{id}` | Scan progress: phase, progress_pct, totals |
| `GET` | `/api/scan/latest/status` | Most recent scan record |
| `GET` | `/api/senders` | All senders; filterable by `category`, `capability`, `decision`; sortable by `count`, `sender`, `last` |
| `POST` | `/api/senders/classify` | Re-run LLM classification on all (or specified) senders |
| `POST` | `/api/senders/decisions` | Set user decisions: `[{sender_id, decision}]` |
| `POST` | `/api/actions/preview` | Per-sender plan for a given sender list — side-effect free |
| `POST` | `/api/actions/execute` | Execute actions; requires `confirm: true`; respects `DRY_RUN` |
| `GET` | `/api/actions/log` | Full action log |
| `GET` | `/api/health` | `{status, dry_run, version}` |

Full OpenAPI schema is available at `http://localhost:8420/docs` when the server is running.

---

## Security notes

- MailCull is designed for `127.0.0.1` only. The OAuth token in `TOKEN_PATH` grants full access to the Gmail scopes you authorised. Do not expose the app on a public interface.
- The token file is written with `0600` permissions (owner read/write only).
- No secrets are logged. `DRY_RUN=true` by default — you must explicitly disable it.
- The LLM sees only: sender name, address, domain, message count, sample subjects, and whether a `List-Unsubscribe` header was present. No message content is ever passed to Ollama.

---

## Limitations

- **One Gmail account per instance.** MailCull is single-user by design.
- **App Passwords / IMAP not supported.** Google Workspace disables App Passwords for accounts managed by an admin. The Gmail REST API with OAuth is the only reliable path.
- **`link` unsubscribes are manual.** When a sender's only unsubscribe mechanism is a hosted web page (no `List-Unsubscribe-Post` header), MailCull surfaces the link but cannot complete the flow — you open it yourself and mark it done.
- **`mailto` unsubscribes require `gmail.send`.** Disable by default. Enable via `INCLUDE_SEND_SCOPE=true` and re-authorise.
- **Ollama classification quality depends on your model.** `llama3.2:3b` works well for most cases. For difficult classifications (ambiguous senders, non-English subjects), a larger model like `mistral:7b` or `qwen2.5:7b` gives better rationales.

---

## License

MIT
