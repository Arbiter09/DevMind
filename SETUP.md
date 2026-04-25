# DevMind — Setup Guide

This guide walks you through everything you need to get DevMind running — from zero to receiving automated AI code reviews on your pull requests.

---

## What You'll Need

Before starting, make sure you have the following installed:

- **Python 3.11 or 3.12** — [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 20+** — [nodejs.org](https://nodejs.org/)
- **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) (for Redis, Jaeger, Prometheus locally)
- **Git** — [git-scm.com](https://git-scm.com/)

You'll also need accounts on:
- **Anthropic** — for the Claude API (the AI brain)
- **GitHub** — for connecting to your repositories

---

## Step 1 — Get Your Anthropic (Claude) API Key

DevMind uses the Claude API to read and review your code.

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. In the left sidebar, click **API Keys**
4. Click **Create Key**, give it a name like `devmind-local`
5. Copy the key — it starts with `sk-ant-...`

> Keep this key secret. Never commit it to Git.

---

## Step 2 — Get Your GitHub Token

DevMind needs to read your pull requests and post review comments.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Fine-grained tokens** → **Generate new token**
3. Set a name like `devmind` and an expiration date
4. Under **Repository access**, select **Only select repositories** and choose the repo(s) you want DevMind to review
5. Under **Repository permissions**, enable:
   - **Contents** → Read-only
   - **Pull requests** → Read and write
   - **Metadata** → Read-only (required automatically)
6. Click **Generate token** and copy it — it starts with `github_pat_...`

> Keep this token secret. Never commit it to Git.

---

## Step 3 — Clone the Repository

```bash
git clone https://github.com/Arbiter09/DevMind.git
cd DevMind
```

---

## Step 4 — Configure Environment Variables

Copy the example env file and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` in any text editor and fill in:

```env
# Required — get from console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-...

# Required — get from github.com/settings/tokens
GITHUB_TOKEN=github_pat_...

# Required — you'll create this in Step 6 (pick any random string for now)
GITHUB_WEBHOOK_SECRET=pick-any-random-string-here

# These have sensible defaults — leave as-is for local dev
REDIS_URL=redis://localhost:6379
OTEL_SERVICE_NAME=devmind-backend
SELF_EVAL_THRESHOLD=3.5
MAX_EVAL_ITERATIONS=3
```

> **Tip:** For `GITHUB_WEBHOOK_SECRET`, just type any random string — e.g. `devmind-secret-123`. You'll paste the same string into GitHub in Step 6.

---

## Step 5 — Install Dependencies

Run this once to install everything:

```bash
make setup
```

This installs Python packages (via `pip`) and Node packages (via `npm`).

If you don't have `make`, run manually:

```bash
# Backend
cd backend && pip install -r requirements.txt && cd ..

# Frontend
cd frontend && npm install && cd ..
```

---

## Step 6 — Start the Infrastructure (Redis, Jaeger, Prometheus)

DevMind uses Redis as both a job queue and a cache. Start the local services with Docker:

```bash
make infra
```

This starts:
- **Redis** on `localhost:6379` — job queue + cache
- **Jaeger UI** on [localhost:16686](http://localhost:16686) — trace visualiser
- **Prometheus** on [localhost:9090](http://localhost:9090) — metrics

---

## Step 7 — Start the Application

Open two terminal windows:

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn api.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     worker_pool.started concurrency=4
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

You should see:
```
VITE v6.x.x  ready in 300ms
➜  Local:   http://localhost:5173/
```

Open [localhost:5173](http://localhost:5173) in your browser — you'll see the DevMind dashboard.

> **Shortcut:** If you have `make`, run `make dev` to start everything at once.

---

## Step 8 — Connect DevMind to GitHub

For DevMind to receive events when a PR is opened, GitHub needs to send a webhook to your running server.

### Expose your local server to the internet

GitHub can't reach `localhost`, so you need a tunnel. Install [ngrok](https://ngrok.com/download) and run:

```bash
ngrok http 8000
```

ngrok will print a public URL like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy that `https://...` URL.

### Add the webhook to your GitHub repository

1. Go to your repository on GitHub
2. Click **Settings** → **Webhooks** → **Add webhook**
3. Fill in:
   - **Payload URL:** `https://abc123.ngrok-free.app/webhooks/github`
   - **Content type:** `application/json`
   - **Secret:** the same value you set for `GITHUB_WEBHOOK_SECRET` in `backend/.env`
   - **Which events?** → Select **Let me select individual events** → check **Pull requests** only
4. Click **Add webhook**

GitHub will send a test ping. In your backend terminal you'll see it arrive.

---

## Step 9 — Test It

Open a pull request on your connected repository (or update an existing one). Within a few seconds you should see:

1. In the backend terminal:
   ```
   webhook.enqueued job_id=... pr=42 repo=your/repo
   phase.start phase=context_gathering
   phase.start phase=analysis
   phase.start phase=self_eval
   phase.start phase=posting
   job.completed avg_score=3.9 iterations=1
   ```

2. On GitHub — DevMind will have posted a review comment on the PR with structured feedback and a quality scorecard.

3. In the dashboard at [localhost:5173](http://localhost:5173) — the job appears in the **Live Feed** with status, token count, and eval score.

### Test without opening a real PR

You can trigger a review manually from the dashboard (enter `owner/repo` and PR number at the top of the Live Feed page), or via the API:

```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_number": 1, "repo": "your-username/your-repo"}'
```

---

## Verify Everything Is Working

Run a quick check to confirm all required env vars are set:

```bash
make env-check
```

Check the API health endpoint:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

Run the simulation to validate the agent logic without any real API calls:

```bash
make simulate-quick
```

This runs the agent against 50 synthetic PRs and prints the three headline metrics.

---

## Dashboard Pages

| Page | URL | What it shows |
|---|---|---|
| Live Feed | [localhost:5173/](http://localhost:5173/) | Real-time list of all review jobs |
| Review Inspector | [localhost:5173/inspect](http://localhost:5173/inspect) | Drill into any job — phase timeline, Claude output, eval scores |
| Cost Analytics | [localhost:5173/cost](http://localhost:5173/cost) | Token usage, cache hit rate, savings over time |
| Quality Metrics | [localhost:5173/quality](http://localhost:5173/quality) | Score distributions, per-dimension averages, iteration counts |

---

## Deployed Version (Vercel)

DevMind is also live at **[devmind-chi.vercel.app](https://devmind-chi.vercel.app)**.

To fully activate the deployed version, you need to:

1. **Add Vercel KV (Redis):**
   - Go to your Vercel project → **Storage** → **Connect Store → KV**
   - Create a store named `devmind-kv` and link it to the project

2. **Add environment variables** in Vercel project settings → **Environment Variables:**
   - `ANTHROPIC_API_KEY`
   - `GITHUB_TOKEN`
   - `GITHUB_WEBHOOK_SECRET`

3. **Update your GitHub webhook URL** to:
   ```
   https://devmind-chi.vercel.app/webhooks/github
   ```

4. **Deploy the worker on Railway** (needed for background job processing — see [`docs/deployment.md`](docs/deployment.md) for full instructions)

---

## Troubleshooting

**"Redis connection refused"**
→ Docker isn't running, or infra containers aren't started. Run `make infra`.

**"No module named 'anthropic'"**
→ Python dependencies aren't installed. Run `make backend-install` or `cd backend && pip install -r requirements.txt`.

**Webhook events not arriving**
→ Check that ngrok is running and the webhook URL in GitHub matches the ngrok URL exactly (including `/webhooks/github`). ngrok URLs change every time you restart — update GitHub when they change.

**Review posted but score is low**
→ Adjust `SELF_EVAL_THRESHOLD` in `.env` (default: `3.5` out of `5.0`). Lowering it reduces refinement iterations and token cost. Raising it produces higher-quality but more expensive reviews.

**"ANTHROPIC_API_KEY not set"**
→ Make sure `backend/.env` exists and contains your key. The file is gitignored and must be created manually.

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key from console.anthropic.com |
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with pull request read/write |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | HMAC secret shared with GitHub webhook |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection string |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | — | OTel collector endpoint (e.g. `http://localhost:4317`) |
| `OTEL_SERVICE_NAME` | No | `devmind-backend` | Service name shown in Jaeger traces |
| `SELF_EVAL_THRESHOLD` | No | `3.5` | Minimum avg score (out of 5) before posting review |
| `MAX_EVAL_ITERATIONS` | No | `3` | Max self-evaluation refinement cycles |
| `WORKER_CONCURRENCY` | No | `4` | Number of parallel review workers |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
