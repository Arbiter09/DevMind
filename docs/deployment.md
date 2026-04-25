# DevMind Deployment Guide

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Vercel                        │
│                                                 │
│  ┌────────────────┐   ┌──────────────────────┐  │
│  │ React Frontend │   │  FastAPI API          │  │
│  │ (Static Build) │   │  (Serverless Python)  │  │
│  │                │   │  /webhooks/github     │  │
│  │  Live Feed     │   │  /api/jobs            │  │
│  │  Inspector     │   │  /api/metrics         │  │
│  │  Cost/Quality  │   │  /api/review          │  │
│  └────────────────┘   └──────────────────────┘  │
└───────────────────────────┬─────────────────────┘
                            │ Redis Streams (enqueue)
                            ▼
            ┌───────────────────────────┐
            │       Vercel KV           │
            │   (Upstash Redis TLS)     │
            │   • Job queue             │
            │   • MCP result cache      │
            │   • Job state storage     │
            └───────────┬───────────────┘
                        │ XREADGROUP (consume)
                        ▼
            ┌───────────────────────────┐
            │        Railway            │
            │   Background Worker       │
            │   (worker.Dockerfile)     │
            │   • Agentic loop          │
            │   • Claude API calls      │
            │   • GitHub MCP tools      │
            └───────────────────────────┘
```

---

## Step 1 — Set up Vercel KV (Redis)

Vercel KV is Upstash Redis under the hood — it's free up to 256MB.

1. Go to [vercel.com/dashboard](https://vercel.com/dashboard) → **Storage** → **Create → KV**
2. Name it `devmind-kv`
3. After creation, go to the KV dashboard → **`.env.local`** tab
4. Copy `KV_URL`, `KV_REST_API_URL`, `KV_REST_API_TOKEN` — you'll need these

---

## Step 2 — Deploy the API + Frontend to Vercel

### Connect the repository

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import the `Arbiter09/DevMind` GitHub repository
3. **Framework Preset:** Other
4. **Root Directory:** `.` (the repo root)
5. **Build Command:** `cd frontend && npm install && npm run build`
6. **Output Directory:** `frontend/dist`

### Add environment variables

In Vercel project settings → **Environment Variables**, add:

| Variable | Value | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | From console.anthropic.com |
| `GITHUB_TOKEN` | `ghp_...` | GitHub PAT with `pull_requests: write` |
| `GITHUB_WEBHOOK_SECRET` | random string | Must match your GitHub webhook config |
| `KV_URL` | `rediss://...` | Auto-populated if you link Vercel KV |
| `OTEL_SERVICE_NAME` | `devmind-api` | Optional |
| `SELF_EVAL_THRESHOLD` | `3.5` | Optional |
| `MAX_EVAL_ITERATIONS` | `3` | Optional |

**Link Vercel KV to your project:**
- In Vercel project settings → **Storage** → connect the `devmind-kv` store
- This automatically adds `KV_URL`, `KV_REST_API_URL`, `KV_REST_API_TOKEN`

### Deploy

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy (from repo root)
vercel --prod
```

Or just push to `main` — Vercel will auto-deploy on every push.

Your app will be live at `https://devmind-<your-username>.vercel.app`

---

## Step 3 — Deploy the Worker to Railway

The background worker is the Redis Streams consumer — it can't run on Vercel (serverless), so it runs as a persistent process on Railway.

### Create a Railway project

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select `Arbiter09/DevMind`
3. Railway will detect `railway.json` and `worker.Dockerfile` automatically

### Add environment variables in Railway

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `GITHUB_TOKEN` | `ghp_...` |
| `KV_URL` | Your Vercel KV `KV_URL` value (copy from Vercel) |
| `OTEL_SERVICE_NAME` | `devmind-worker` |
| `WORKER_CONCURRENCY` | `4` |
| `SELF_EVAL_THRESHOLD` | `3.5` |
| `MAX_EVAL_ITERATIONS` | `3` |

> **Important:** Both Vercel and Railway must use the **same** `KV_URL`. The Vercel API enqueues jobs to Redis; the Railway worker consumes them from the same queue.

### Deploy

Railway auto-deploys on push to `main`. You can also trigger manually:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway up
```

---

## Step 4 — Update Your GitHub Webhook

After Vercel deployment, update your GitHub webhook URL:

1. Go to your repo → **Settings → Webhooks → Edit**
2. Set **Payload URL** to: `https://devmind-<your-username>.vercel.app/webhooks/github`
3. Keep the same **Secret** (matches `GITHUB_WEBHOOK_SECRET`)

---

## Step 5 — Verify the Deployment

### Test the API
```bash
curl https://devmind-<your-username>.vercel.app/health
# → {"status":"ok","mode":"serverless"}

curl https://devmind-<your-username>.vercel.app/api/metrics
# → {"message":"No jobs recorded yet"}
```

### Trigger a manual review
```bash
curl -X POST https://devmind-<your-username>.vercel.app/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_number": 1, "repo": "owner/repo"}'
# → {"job_id":"...","status":"queued"}
```

Then check the dashboard — the job should appear in Live Feed and complete within seconds (Railway worker picks it up from Redis).

---

## Environment Summary

| Service | URL | What it runs |
|---|---|---|
| Vercel | `https://devmind-xxx.vercel.app` | Frontend + API (webhooks, jobs, metrics) |
| Vercel KV | Internal | Redis cache + job queue |
| Railway | Internal | Background worker (agentic loop) |
| GitHub | `github.com/Arbiter09/DevMind` | Source + CI |

---

## Scaling

| Concern | Solution |
|---|---|
| More concurrent reviews | Increase `WORKER_CONCURRENCY` on Railway, or add more Railway replicas |
| Higher API throughput | Vercel auto-scales serverless functions |
| Redis memory | Upgrade Vercel KV tier, or use a dedicated Upstash instance |
| Token cost | Tune `SELF_EVAL_THRESHOLD` lower to reduce refinement iterations |

---

## Monitoring

- **Vercel Dashboard** → Functions → see invocation counts, errors, and latency per route
- **Railway** → Logs → tail the worker in real-time
- **Jaeger** (local dev only) → `http://localhost:16686`
- **DevMind Dashboard** → Cost Analytics and Quality Metrics pages show aggregated metrics from all jobs stored in Redis

---

## Cost Estimate (free tiers)

| Service | Free tier | Typical DevMind usage |
|---|---|---|
| Vercel Hobby | 100GB bandwidth, unlimited deployments | Well within limits |
| Vercel KV | 256MB storage, 30K commands/day | ~500 PRs/day within limits |
| Railway Starter | $5 credit/month | Worker idles between PRs, very low cost |
| Anthropic API | Pay per token | ~3K tokens/PR → ~$0.003/review at Sonnet pricing |
