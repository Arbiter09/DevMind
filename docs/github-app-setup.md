# GitHub App Setup Guide

This guide walks through connecting DevMind to a real GitHub repository so it receives webhook events and can post review comments.

You have two options:
- **Option A: Personal Access Token** — simpler, good for personal repos
- **Option B: GitHub App** — recommended for teams, gives fine-grained permissions

---

## Option A: Personal Access Token (Quickest)

### 1. Create a token

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set expiration and select the target repository
4. Grant these permissions:
   - **Repository permissions:**
     - `Contents` → Read-only
     - `Pull requests` → Read and write
     - `Metadata` → Read-only

5. Copy the token value

### 2. Configure DevMind

```bash
# In backend/.env
GITHUB_TOKEN=github_pat_...
GITHUB_WEBHOOK_SECRET=pick-a-random-string
```

### 3. Add the webhook to your repository

1. Go to your repo → **Settings → Webhooks → Add webhook**
2. **Payload URL:** your ngrok or public URL + `/webhooks/github`
3. **Content type:** `application/json`
4. **Secret:** the same value as `GITHUB_WEBHOOK_SECRET`
5. **Which events?** → Select: `Pull requests`
6. Click **Add webhook**

---

## Option B: GitHub App (Recommended)

A GitHub App is better because:
- It authenticates as an app, not a user
- You can install it on any repo without sharing your personal token
- Fine-grained permissions with audit trail

### 1. Create the GitHub App

1. Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App**
2. Fill in:
   - **App name:** `DevMind` (or your preferred name)
   - **Homepage URL:** `https://github.com/Arbiter09/DevMind`
   - **Webhook URL:** your server URL + `/webhooks/github` (use ngrok for local dev — see below)
   - **Webhook secret:** generate a random string (save it)
3. **Permissions** (Repository):
   - `Contents` → Read-only
   - `Pull requests` → Read and write
   - `Metadata` → Read-only
4. **Subscribe to events:** ✅ Pull request
5. **Where can this GitHub App be installed?** → Only on this account (for now)
6. Click **Create GitHub App**

### 2. Generate a private key

1. After creating the app, scroll to **Private keys**
2. Click **Generate a private key** — downloads a `.pem` file
3. Place it at `backend/github_app.pem` (add to `.gitignore`)

### 3. Install the app on your repository

1. In your GitHub App settings → **Install App**
2. Select the repository you want DevMind to review
3. Note the **Installation ID** from the URL: `github.com/settings/installations/{INSTALLATION_ID}`

### 4. Configure DevMind

```bash
# In backend/.env
GITHUB_APP_ID=123456
GITHUB_APP_INSTALLATION_ID=78901234
GITHUB_APP_PRIVATE_KEY_PATH=./github_app.pem
GITHUB_WEBHOOK_SECRET=your-webhook-secret
```

> The `github_client.py` can be updated to use JWT-based App authentication
> instead of a PAT by using the `PyJWT` library to sign tokens with the private key.

---

## Local Development with ngrok

When developing locally, GitHub can't reach `localhost:8000`. Use ngrok to create a public tunnel.

### Install ngrok

```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

### Create a free ngrok account

Sign up at [ngrok.com](https://ngrok.com) and get your auth token:

```bash
ngrok config add-authtoken <your-token>
```

### Start the tunnel

```bash
# Option 1: via Makefile
make tunnel

# Option 2: directly
ngrok http 8000
```

ngrok will print something like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Use `https://abc123.ngrok-free.app/webhooks/github` as your GitHub webhook URL.

> **Note:** Free ngrok URLs change on every restart. Update your GitHub webhook URL each time,
> or upgrade to a paid plan for a stable domain.

### Verify the webhook is working

1. Start DevMind: `make dev`
2. Start tunnel: `make tunnel` (in a separate terminal)
3. Open a PR on your connected repository
4. Watch the backend logs — you should see:
   ```
   webhook.enqueued job_id=... pr=42 repo=owner/repo
   phase.start phase=context_gathering
   phase.start phase=analysis
   phase.start phase=self_eval
   phase.start phase=posting
   job.completed avg_score=3.9 iterations=1
   ```
5. Check the PR on GitHub — DevMind should have posted a review comment

---

## Testing Without a Real Repository

Use the manual trigger endpoint to test the full agent loop without GitHub webhooks:

```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_number": 1, "repo": "owner/repo"}'
```

Or use the **Review Inspector** page in the dashboard (the input box at the top lets you enter `owner/repo` and a PR number).

---

## Security Checklist

- [ ] `GITHUB_WEBHOOK_SECRET` is set and matches the GitHub webhook configuration
- [ ] `github_app.pem` is in `.gitignore` and never committed
- [ ] `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` are only in `.env`, never in code
- [ ] The `.env` file is in `.gitignore`
- [ ] Webhook signature verification is enabled (it is, by default, when `GITHUB_WEBHOOK_SECRET` is set)
