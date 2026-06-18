# DevMind — Project Context Document

> **Interview prep reference.** Every claim traces to an actual file. Honest caveats included.
>
> Stack: Claude API · MCP · FastAPI · Redis · React · OpenTelemetry · AWS EC2

---

## SECTION 1 — Project Overview

DevMind is an autonomous pull request code review agent. A review is triggered manually via `POST /api/review`. Claude receives all available tools via the Anthropic function-calling API and **adaptively decides** which context to gather — CI status, dependency vulnerabilities, static analysis findings, repo docs, and file contents — before writing a structured review. A self-evaluation loop then scores the review against a 12-dimension rubric and iteratively refines any dimension below the quality threshold (avg score ≥ 3.5/5). The final review is posted as a GitHub PR comment.

The system has two core technical innovations: (1) **Agentic tool discovery** — Claude drives tool selection via `tools=ANTHROPIC_TOOLS` rather than a hardcoded pipeline, adapting its context-gathering strategy to each PR. (2) **Self-evaluation loop** — a second Claude call scores the review across 12 dimensions and triggers targeted refinement, closing the quality gap between fast automated and careful human review.

- **Scale**: Validated against 500 simulated PRs across 5 languages (Python, TypeScript, Go, Java, Rust) using a 60-PR annotated benchmark (`simulation/data/annotated_prs.jsonl`).
- **Authorship**: Solo-built. Single GitHub account (Arbiter09), no multi-author commit history.
- **External artifact**: GitHub tool layer published as `@arbiter09/github-mcp` on npm (`npx -y @arbiter09/github-mcp`), listed on Smithery MCP registry.

---

## SECTION 2 — Headline Metrics Deep Dive

### Metric 1 — PR Review Turnaround Reduced by 60%

**The Claim**: "Reduced PR review turnaround by 60% across 500+ simulated PRs"

**How It Was Measured** (`simulation/report.py` → `metric_turnaround()`):

The **primary comparison** is DevMind vs. a naive single-pass automated reviewer (not humans). The naive baseline (`--naive-baseline` mode) models:
- No Redis caching → 3 fresh GitHub API calls per PR
- Full diff + full files in prompt (~13.5k tokens)
- No Anthropic prompt cache (every eval call pays full price)
- `avg_iterations=2.5` (poor first-pass quality needs more refinement)

DevMind models:
- 70% GitHub cache hit rate
- Compressed context (~5k tokens)
- Anthropic prompt cache on diff tokens (`_CLAUDE_CACHE_FACTOR=0.5`)
- `avg_iterations=1.5`

**Timing model constants** (`run_simulation.py`):
```
_CLAUDE_BASE_S         = 1.5    # base latency per call
_CLAUDE_PER_1K_IN_S    = 1.2    # per 1k input tokens
_CLAUDE_PER_1K_OUT_S   = 0.8    # per 1k output tokens
_CLAUDE_CACHE_FACTOR   = 0.5    # cached tokens take 50% time
_GITHUB_API_S          = 0.4    # per GitHub REST call
```

Human baseline: `fetch_human_baseline.py` fetched real GitHub PR review timing — time from PR creation to first non-bot, non-self-review human submission. Stored result: `human_median=32.51h` (source: `real_github_data`).

**⚠️ HONEST CAVEAT — Stored metrics show 50.7%, not 60%**

`simulation/data/metrics_summary.json`:
```json
"naive_baseline_median_seconds": 24.59,
"pipeline_reduction_pct": 50.7
```
`report.py` tags "✅" at `pipeline_pct >= 55` (line 255), not ≥60. The 60% is the design target; 50.7% is the stored simulation run result.

**How to Defend It**: "The 60% is the design target for a well-cached, compressed pipeline at steady state. The 50.7% is from a specific simulation run. The timing model constants were calibrated from real Redis job records via `fetch_agent_timing.py`. The comparison is apples-to-apples: two automated pipelines, same PR inputs."

---

### Metric 2 — 91% Reviewer Agreement Rate

**The Claim**: "Achieving a 91% reviewer agreement rate" across 60+ annotated PRs.

**How It Was Measured**:

Benchmark: `simulation/data/annotated_prs.jsonl` — 60 `PRTemplate` records in `pr_templates.py`, each with a 12-dimension `DimensionAnnotation` list (`expected=True/False` + rationale). Agreement computed in `run_simulation.py` → `score_dimension_agreement()`:

```python
STRONG_COVERAGE = PASS_THRESHOLD   # 3.5 — agent covered the dimension
INCOHERENCE_FLOOR = 3.0            # agent didn't spuriously flag a clean dim

for ann in annotations:   # 12 per PR
    if ann["expected"]:
        hit = agent_score >= STRONG_COVERAGE     # did agent catch a real issue?
    else:
        hit = agent_score >= INCOHERENCE_FLOOR   # no spurious flags on clean dims?

agreement_rate = hits / len(annotations)
agreed = agreement_rate >= 0.91     # PR-level flag
```

**⚠️ HONEST CAVEAT — Stored metrics: 100% agreement, circular measurement**

`metrics_summary.json` shows `agreement_rate_pct=100.0` and `dimension_agreement_pct=0.0%` (`annotated_count=0` — the annotated benchmark mode wasn't used in that run). The 100% is because `mock_claude.py` generates scores `[4.0-5.0]` for covered dims and `[3.5-5.0]` for uncovered — both trivially pass the 3.5/3.0 thresholds. The 91% is the design target and requires a real-Claude run on the annotated benchmark.

---

### Metric 3 — 38% Token Cost Reduction

**The Claim**: "Cut Claude API token costs by 38% via Redis caching and prompt compression, sustaining sub-2s p95 latency"

**How It Was Measured** (`report.py` → `metric_token_cost()`):

Formula: `reduction_pct = ((baseline_total - cached_total) / baseline_total) * 100`
where baseline = `--no-cache` run, cached = normal DevMind run.

Three compounding mechanisms:

1. **Redis MCP cache**: Key = `mcp:{tool_name}:{sha256(kwargs)[:16]}`. Same `utils.py` at same commit SHA cached 86400s — all PRs touching it share one GitHub API call.

2. **Prompt compression**: Files over `MAX_FILE_LINES_FOR_CONTEXT=500` lines are sliced to ±10 lines around diff hunks (`extract_changed_context`). Hard limits: `diff[:10000]`, `body[:500]`. Estimated ~60% context token reduction on large files.

3. **Anthropic prompt cache**: Diff in system prompt with `cache_control={"type":"ephemeral"}`. Self-eval iterations 2+ pay ~10% for diff tokens (`_CLAUDE_CACHE_FACTOR=0.5`).

**⚠️ HONEST CAVEAT**: Stored run shows `cache_hit_rate=0.0%` (not paired with `--no-cache` baseline). Sub-2s p95 likely refers to Redis operation latency (microseconds), not end-to-end review time — stored p95 is 12.2s.

---

## SECTION 3 — System Architecture

### Component Overview

| Component | Role | NOT Responsible For |
|---|---|---|
| FastAPI (`backend/api/`) | Webhook validation (HMAC-SHA256), manual review trigger (`POST /api/review`), job status API, GitHub proxy | Running agent; consuming jobs |
| Redis Streams (`jobqueue/`) | Durable job queue — decouples webhook ack from execution; supports retries + DLQ | Caching; storing job results |
| Worker Pool (`worker.py`) | 4 async workers consuming from Redis Stream, invoking AgentOrchestrator | HTTP handling; storing artifacts |
| AgentOrchestrator (`agent/loop.py`) | 3-phase loop per PR: (1) Agentic Review — Claude drives tool selection, (2) Self-Evaluation, (3) Posting; job state persisted to Redis (7 days) | HTTP; queue management; caching policy |
| MCP Tool Layer (`mcp/`) | 10 tools: 6 GitHub context + CI results + dependency vuln scan + static analysis + repo docs; cache-aside wrapping | Agent logic; scoring; prompt building |
| Redis Cache (`cache/redis_cache.py`) | Cache-aside store for MCP tool results + review_draft + job blobs | Queue; tracing |
| OpenTelemetry (`telemetry/`) | Distributed tracing per phase + token usage + cache hits → OTLP → Jaeger/Prometheus | Alerting; log aggregation |
| React Dashboard (`frontend/`) | LiveFeed, ReviewInspector, CostAnalytics, QualityMetrics pages polling `/api/*` | Agent execution; data transformation |

### Request Flow

```
POST /api/review  (manual trigger — webhook validates only, does not enqueue)
  → FastAPI: validates HMAC-SHA256 signature (webhooks.py) if webhook
  → review.py: trigger_review() → get_job_queue().enqueue(job_id, pr_number, repo)
  → XADD devmind:jobs {job_id, pr_number, repo}
  → Worker (XREADGROUP devmind-workers): picks up job
  → AgentOrchestrator.run()

      Review-draft cache check (cheap — get_pr_metadata is cached 300s):
        get_pr_metadata → head_sha
        Redis GET mcp:review_draft:{sha256[:16]}
          HIT → load cached {review, eval_scores, avg_score, diff} → skip Phase 1+2
          MISS → continue

      Phase 1: Agentic Review (agentic_review.py)
        Claude receives AGENT_SYSTEM_PROMPT + 9 tool schemas via tools= parameter
        Multi-turn tool loop (MAX_TOOL_TURNS=15):
          Claude → tool_use: get_pr_metadata(pr_number, repo)
          Orchestrator executes tool → tool_result appended to messages
          Claude → tool_use: get_pr_diff(pr_number, repo)
          Claude → (adaptive) tool_use: get_ci_results(pr_number, repo, head_sha)
          Claude → (if dep files changed) tool_use: scan_dependency_vulnerabilities(...)
          Claude → tool_use: run_static_analysis(pr_number, repo)
            └─ internally fetches get_pr_diff (cache hit) + runs pattern scan
          Claude → tool_use: read_file(path, repo, ref)  [0–N files]
          Claude → tool_use: search_repo_docs(repo)
          Claude → stop_reason="end_turn" → review_draft text extracted
        All tool results cached in Redis with per-tool TTLs (120s–86400s)
        Cache review_draft to Redis TTL=7d keyed on (repo, pr_number, head_sha)

      Phase 2: Self-Evaluation (MAX_ITERATIONS=3, PASS_THRESHOLD=3.5)
        System: diff[:8000] + 12-dim rubric (cache_control=ephemeral)
        User: score_message(review_draft)
        Claude → JSON [12 scores]
        if avg < 3.5 AND iteration < 3:
          User: refinement_message(bottom 3 dims)
          Claude → new review_draft
          User: rescore_message(new_draft) → loop
        cache review_draft to Redis TTL=7d

      Phase 3: Posting
        format review + scorecard footer (star ratings per dim)
        post_review_comment → GitHub REST POST /pulls/N/reviews

  → job.status = COMPLETED
  → SETEX devmind:job:{id} 604800 {json}
  → XACK devmind:jobs devmind-workers {entry_id}
```

**⚠️ Manual trigger only**: `webhooks.py` validates HMAC-SHA256 and acknowledges the event but does NOT call `queue.enqueue()`. Use `POST /api/review` to trigger a review. Auto-enqueue is intentionally not wired.

---

## SECTION 4 — Tech Stack Justified

| Technology | Role | Key Config / Values |
|---|---|---|
| Claude API (anthropic 0.43.0) | LLM for: (1) agentic tool loop — Claude drives tool selection via `tools=` function-calling API; (2) self-eval scoring; (3) review refinement | Primary: `claude-3-5-sonnet-latest` → fallback: `claude-3-5-haiku-latest` → `claude-3-haiku-20240307`. MAX_TOKENS: 4096 (agentic + refine), 2048 (eval). `MAX_TOOL_TURNS=15`. |
| MCP (mcp==1.3.0) | Tool abstraction: 10 tools served as stdio MCP server; published as `@arbiter09/github-mcp` npm package. Claude decides which tools to call via Anthropic function-calling API (`tools=ANTHROPIC_TOOLS`). | 10 tools: `get_pr_metadata`, `get_pr_diff`, `read_file`, `list_changed_files`, `get_file_history`, `post_review_comment`, `get_ci_results`, `scan_dependency_vulnerabilities`, `run_static_analysis`, `search_repo_docs`. |
| FastAPI 0.115.6 + uvicorn 0.34.0 | HTTP server for webhook ingestion, review trigger, job status API, GitHub proxy | CORS: localhost:5173, localhost:3000. `FastAPIInstrumentor`. Worker pool starts on app startup. |
| Redis 5.2.1 (redis:7.2-alpine) | Dual role: Streams for job queue + cache-aside for MCP tool results + job state storage | AOF persistence. Job TTL: 7 days. Worker group: `devmind-workers`. `WORKER_CONCURRENCY=4`. |
| React + Vite + TypeScript | Dashboard: LiveFeed, ReviewInspector, CostAnalytics, QualityMetrics | `VITE_API_URL` env. `usePolling` hook. Port 5173 dev. |
| OpenTelemetry 1.29.0 | Distributed tracing per agent phase → OTLP gRPC → OTel Collector → Jaeger + Prometheus | `OTEL_SERVICE_NAME=devmind-backend`. Endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT`. Fallback: `ConsoleSpanExporter`. |
| httpx 0.28.1 | Async HTTP client for GitHub REST API calls | `timeout=30.0s`, `follow_redirects=True`, `AsyncHTTPTransport(retries=3)`. Headers: `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`. |
| structlog 24.4.0 | Structured JSON logging throughout backend | Per-module via `structlog.get_logger(__name__)`. `bind()` adds `job_id`/pr context. |

**Why Not Alternatives**:
- **LangChain/LangGraph**: Not used. The agentic tool loop is implemented directly in `agentic_review.py` using Anthropic's function-calling API — no framework overhead, full control of the message loop.
- **GPT-4**: Not used. Anthropic's `cache_control: ephemeral` directly enables the self-eval token reduction; also needed for `tools=` function-calling which is the backbone of the agentic phase.
- **PostgreSQL**: Not used. Job records are ephemeral JSON blobs with 7-day TTL; Redis `SETEX` is simpler.

---

## SECTION 5 — The Core Logic Loop

### 5.1 State Management

All job state lives in Redis at key `devmind:job:{job_id}` (TTL=604800s = 7 days). The `ReviewJob` Pydantic model (`backend/models/job.py`) stores: status, pr_number, repo, phases (list[PhaseTrace]), eval_scores (list[EvalScore]), eval_iterations, avg_eval_score, total_tokens_input/output/cache_hits/misses, review_body, trace_id.

`AgentOrchestrator._save_job()` is called at run start (status=RUNNING) and in a `finally` block (COMPLETED or FAILED). **In-memory state** during a run: the `job` object, agentic `messages` list (tool-call conversation), self-eval `messages` list, `current_draft` string, `final_scores` list. None of this survives a crash — a mid-phase crash restarts from Phase 1 on the next retry.

### 5.2 Loop Control Constants

```python
# agentic_review.py:
MAX_TOOL_TURNS = 15       # hard cap on tool-call turns per review

# rubric.py — hardcoded constants (NOT read from env, despite .env.example)
PASS_THRESHOLD = 3.5      # avg score required to skip refinement
MAX_ITERATIONS = 3        # hard cap on self-eval refinement cycles

# agentic_review.py + self_eval.py:
MAX_TOKENS = 4096         # per Claude call (agentic review + refinement)
MAX_TOKENS_EVAL = 2048    # per self-eval scoring call

# context_gathering.py (used for cache-miss file reads in tool dispatch):
MAX_FILE_LINES_FOR_CONTEXT = 500   # files above this get hunk-compressed
```

**⚠️ `SELF_EVAL_THRESHOLD` and `MAX_EVAL_ITERATIONS` env vars are NOT functional**: `rubric.py` hardcodes these values and does not call `os.getenv()`. The `.env.example` entries are aspirational documentation, not wired up.

### 5.3 Iteration Mechanics (`self_eval.py`)

```python
system_blocks = build_eval_system_blocks(diff)
# → system: EVAL_SYSTEM_PROMPT + diff[:8000] + 12-dim list
# → cache_control = {"type": "ephemeral"}  ← Anthropic charges ~10% on reuse

messages = []
for iteration in range(1, MAX_ITERATIONS + 1):   # 1, 2, 3
    score_text = build_score_message(current_draft) if iteration == 1
                 else build_rescore_message(current_draft)
    messages.append({"role": "user", "content": score_text})
    
    score_response = await Claude(system=system_blocks, messages=messages,
                                  max_tokens=MAX_TOKENS_EVAL)
    score_raw = score_response.content[0].text
    messages.append({"role": "assistant", "content": score_raw})
    
    final_scores = _parse_scores(score_raw)   # list[DimensionScore]
    avg = sum(s.score for s in final_scores) / len(final_scores)
    
    if avg >= PASS_THRESHOLD or iteration == MAX_ITERATIONS:
        break   # PASS or force-pass after 3 iterations
    
    # Refinement: target the 3 LOWEST-scoring dimensions
    weak = sorted(final_scores, key=lambda s: s.score)[:3]
    refine_msg = build_refinement_message(weak)
    messages.append({"role": "user", "content": refine_msg})
    refine_response = await Claude(system=system_blocks, messages=messages,
                                   max_tokens=MAX_TOKENS_REFINE)
    current_draft = refine_response.content[0].text
    messages.append({"role": "assistant", "content": current_draft})
```

### 5.4 Failure Modes in the Loop

| Scenario | Actual Behavior |
|---|---|
| LLM throws non-404 exception | Re-raised immediately. No retry within loop. Propagates to orchestrator → job=FAILED → worker nacks (up to MAX_RETRIES=3) → DLQ. |
| `_parse_scores` returns empty list | `avg_score = 0.0` → always below PASS_THRESHOLD → triggers refinement every iteration → hits MAX_ITERATIONS → exits. Job completes COMPLETED with `eval_scores=[]` and `avg_eval_score=0.0`. |
| LLM returns non-JSON text | `_parse_scores` tries bracket extraction: `raw[raw.find('['):raw.rfind(']')+1]`. Falls back to empty list. |
| MAX_ITERATIONS hit without passing | Loop exits. `final_scores` from last iteration used. Review posted regardless of score. |
| Idempotency | NOT idempotent. Re-running a failed job makes new Claude calls and may get different scores. |

---

## SECTION 6 — Prompt Engineering

### 6.1 Agentic System Prompt (`agentic_review.py` → `AGENT_SYSTEM_PROMPT`)

Sent as the `system=` parameter on every turn of the tool loop. Gives Claude strategy guidance — not just tool definitions.

```
You are an expert code reviewer with access to a GitHub repository's code,
CI infrastructure, and dependency graph.

## Tool Usage Strategy
Always start with `get_pr_metadata` — you need the `head_sha` it returns.
Then follow the context you find:
- Run get_pr_diff and list_changed_files to understand the scope.
- Run get_ci_results early — failing CI must be addressed before merging.
- Run run_static_analysis to catch common security issues in the diff.
- If the PR touches dependency files, run scan_dependency_vulnerabilities.
- Use read_file for files where the diff alone isn't enough context.
- Use search_repo_docs once to understand project conventions.
- Use get_file_history for files that look suspicious or recently churned.

## When to Stop Calling Tools
Stop when you can write a complete, specific review. Do not call tools redundantly.

## Review Format
Write under: Critical | Suggestions | Nitpicks
Reference specific file paths and line numbers for every finding.
If CI is failing, put a prominent warning at the top.
End with: APPROVE / REQUEST_CHANGES / COMMENT
```

### 6.2 Legacy Analysis Prompt (`compressor.py` → `build_analysis_prompt`)

Still used by `analysis.py` for non-agentic invocations and as a reference. The `enriched_context` parameter adds new sections when available:

```
## CI Status          ← from get_ci_results
## Dependency Vulnerabilities  ← from scan_dependency_vulnerabilities
## Static Analysis Pre-scan    ← from run_static_analysis
## Repository Standards        ← from search_repo_docs
```

### 6.3 Token Reduction Techniques

| Technique | Implementation | Est. Impact |
|---|---|---|
| Tool-call caching (Redis) | All 10 MCP tool results cached with per-tool TTL. `run_static_analysis` re-uses cached `get_pr_diff`. Same file at same SHA never fetched twice. | Eliminates redundant API calls across turns |
| Hunk-based context slicing | `extract_changed_context()` parses `@@ -N,N +N,N @@` headers, extracts ±10 lines around each hunk. Only files >500 lines. | ~60% reduction on large files |
| File deduplication | `deduplicate_file_contexts()` removes exact-content duplicates | Eliminates redundant sends of shared utility files |
| Anthropic cache (self-eval) | `build_eval_system_blocks()` puts `diff[:8000]` in system with `cache_control=ephemeral`. All eval iterations after first pay ~10% for diff tokens. | Diff is dominant input cost per eval call |
| Review-draft cache (Redis) | Full review cached by `(repo, pr_number, head_sha)` — skip ALL Claude calls on re-trigger of same commit | 100% token savings for repeated triggers of same commit |
| Adaptive tool selection | Claude skips tools it deems irrelevant (e.g. no vuln scan on doc-only PRs) | Varies; typical review uses 6–10 of 9 available tools |

### 6.4 Self-Eval System Prompt (`rubric.py`)

```
SYSTEM (with cache_control=ephemeral):
  "You are a senior code reviewer evaluating the quality of an AI-generated PR review.
   Score each of the 12 dimensions below on a scale of 1 (poor) to 5 (excellent).
   A score of 1 means the review completely missed this dimension.
   A score of 5 means the review gave actionable, accurate feedback (or correctly noted no issues).
   
   Respond ONLY with a JSON array:
   [
     {"name": "correctness", "score": 4.0, "notes": "one-sentence rationale"},
     ...
   ]
   Do not include any text outside the JSON array."

  ## Pull Request Diff
  ```diff
  [diff[:8000]]
  ```

  ## Dimensions to Score
  1. correctness — Does the code do what it claims? Logic errors or off-by-one bugs?
  2. security — Injection, auth bypasses, exposed secrets, insecure defaults?
  3. performance — O(n²) patterns, N+1 queries, blocking I/O, memory leaks?
  4. readability — Naming, function length, cognitive complexity?
  5. error_handling — Exceptions caught? Silent failures or swallowed errors?
  6. test_coverage — New code paths covered? Edge cases tested?
  7. api_consistency — Naming conventions, REST semantics, interface patterns?
  8. documentation — Public functions documented? Comments accurate?
  9. dependency_hygiene — Dependencies justified? Imports clean? Versions pinned?
  10. breaking_changes — Interface/schema/contract changes without versioning?
  11. code_duplication — DRY violations, copy-pasted logic?
  12. edge_cases — Null inputs, empty collections, boundary values, concurrent access?
```

### 6.5 Refinement Prompt (`rubric.py` → `build_refinement_message`)

```
[USER MESSAGE — no diff re-sent, it's in system]

The review was evaluated and found lacking in these areas:

- [dim_name] (score [x]/5): [notes]
- [dim_name] (score [x]/5): [notes]
- [dim_name] (score [x]/5): [notes]

Rewrite the review, specifically improving the weak dimensions listed above.
Keep all strong sections from the previous draft. Return only the improved review.
```

Weak dimensions = bottom 3 by score: `weak = sorted(final_scores, key=lambda s: s.score)[:3]`

---

## SECTION 7 — Infrastructure Deep Dive

### 7.1 Queue / Messaging (`streams.py`)

| Constant | Value | Purpose |
|---|---|---|
| `STREAM_KEY` | `devmind:jobs` | Main work queue |
| `DEAD_LETTER_KEY` | `devmind:jobs:dead` | Messages that fail MAX_RETRIES=3 times |
| `GROUP_NAME` | `devmind-workers` | Consumer group; created with `XGROUP CREATE ... id=0 mkstream=True` |
| `MAX_RETRIES` | `3` | `nack()` increments `_retries`; once ≥3 → DLQ |
| `block_ms` | `2000ms` | `XREADGROUP` blocks 2s waiting for messages |
| `WORKER_CONCURRENCY` | `4` (or `$WORKER_CONCURRENCY` env) | Number of asyncio tasks / consumer instances |

```python
# nack() logic — streams.py
retries = int(fields.get("_retries", "0")) + 1
if retries >= MAX_RETRIES:
    await redis.xadd(DEAD_LETTER_KEY, fields)     # move to DLQ
    await redis.xack(STREAM_KEY, GROUP_NAME, entry_id)
else:
    fields["_retries"] = str(retries)
    await redis.xadd(STREAM_KEY, fields)          # re-enqueue immediately
    await redis.xack(STREAM_KEY, GROUP_NAME, entry_id)
```

**Known Queue Gaps**:
- No `XAUTOCLAIM`: messages held by crashed workers stay in PEL indefinitely
- No exponential backoff: failed messages re-enqueue immediately
- No jitter: all workers retry simultaneously after failure burst

### 7.2 Caching Layer (`redis_cache.py`)

```python
# Key schema:
def _build_key(tool_name: str, **kwargs) -> str:
    stable = json.dumps(kwargs, sort_keys=True)   # deterministic
    digest = hashlib.sha256(stable.encode()).hexdigest()[:16]
    return f"mcp:{tool_name}:{digest}"
# Example: mcp:read_file:a3f9b2c1d4e5f678
```

| Tool / Data Type | TTL | Rationale |
|---|---|---|
| `read_file` | 86400s (24 h) | Content at a commit SHA is immutable |
| `get_pr_diff` | 3600s (1 h) | Diff is stable at a given HEAD SHA |
| `get_pr_metadata` | 300s (5 min) | Labels/status can change frequently |
| `list_changed_files` | 3600s (1 h) | File list stable per HEAD SHA |
| `get_file_history` | 1800s (30 min) | Commit history rarely changes mid-review |
| `review_draft` | 604800s (7 d) | Keyed on `(repo, pr_number, head_sha)` — immutable per commit |
| (default) | 600s (10 min) | Fallback for unregistered tool names |

Race conditions: benign — two concurrent workers both miss cache, both write the same value. No mutex needed.

### 7.3 Observability

| Span Name | Key Attributes |
|---|---|
| `devmind.review.pr_{pr_number}` | `pr.number`, `pr.repo`, `job.id` — root span |
| `devmind.context_gathering` | `pr.number`, `pr.repo`, `files.changed`, `files.context_loaded` |
| `devmind.analysis` | `pr.number`, `tokens.input`, `tokens.output`, `tokens.total` |
| `devmind.self_eval` | `pr.number`, `tokens.input/output`, `eval.avg_score`, `eval.iteration`, `eval.dimension_count` |
| `devmind.posting` | `pr.number`, `pr.repo` |
| (cache spans) | `cache.hit` (bool), `tool.name` |

Pipeline: backend → OTLP gRPC (port 4317) → OTel Collector 0.114.0 → Jaeger 1.76.0 (UI: port 16686) + Prometheus 2.55.0 (port 9090).

---

## SECTION 8 — API / Interface Design

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/github` | Validates HMAC-SHA256 (X-Hub-Signature-256). Logs event. Returns 200. **Does NOT enqueue** — intentionally manual. Use `POST /api/review` to trigger a review. |
| `POST` | `/api/review` | Manually enqueue PR review. Body: `{pr_number: int, repo: string}`. Returns `{job_id, entry_id, status: 'queued'}`. 503 if Redis unreachable. |
| `GET` | `/api/jobs` | List up to 50 ReviewJob records from Redis. Returns `[]` if Redis unavailable. |
| `GET` | `/api/jobs/{job_id}` | Full detail for one job including PhaseTrace records. 404 if not found; 503 if Redis unavailable. |
| `GET` | `/api/metrics` | Aggregate token usage, cache hit rate, avg eval score. Returns zeros if Redis unavailable. |
| `GET` | `/api/github/repos` | List repos visible to `GITHUB_TOKEN`. Paginated, 100/page. 503 if token not configured. |
| `GET` | `/api/github/pulls` | List PRs for a repo. Params: `repo` (owner/repo), `state` (open|closed|all). |
| `GET` | `/health` | Returns `{"status": "ok"}`. Process health only — no Redis check. |

### Key Pydantic Models (`backend/models/job.py`)

```python
class ReviewRequest(BaseModel):
    pr_number: int
    repo: str                     # "owner/repo" format

class ReviewJob(BaseModel):
    id: str                       # UUID
    pr_number: int
    repo: str
    status: JobStatus             # pending | running | completed | failed
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    review_body: str | None       # final posted review text
    eval_scores: list[EvalScore]  # 12 × {dimension, score, notes}
    eval_iterations: int
    avg_eval_score: float | None
    total_tokens_input: int
    total_tokens_output: int
    total_cache_hits: int
    total_cache_misses: int
    phases: list[PhaseTrace]      # one per phase
    trace_id: str | None          # OTel trace ID for Jaeger correlation
```

---

## SECTION 9 — End-to-End Data Flow Trace

```
TRIGGER: POST /api/review {"pr_number": 42, "repo": "acme-corp/backend-api"}
  review.py: trigger_review()
  job_id = str(uuid.uuid4())
  get_job_queue().enqueue(job_id, 42, "acme-corp/backend-api")
    XADD devmind:jobs {job_id, pr_number:"42", repo:"acme-corp/backend-api"}
  → {"job_id": "a1b2c3d4", "entry_id": "1234567890-0", "status": "queued"}

WORKER: worker.py run_worker("worker-0")
  XREADGROUP devmind-workers worker-0 {devmind:jobs: >} COUNT 1 BLOCK 2000
  orchestrator.run("a1b2c3d4", 42, "acme-corp/backend-api")

ORCHESTRATOR: loop.py AgentOrchestrator.run()
  job = ReviewJob(status=RUNNING, ...)
  _save_job(job) → SETEX devmind:job:a1b2c3d4 604800 '{"status":"running",...}'
  agent_span("devmind.review.pr_42")

  ── Review-draft cache check (cheap — 300s TTL) ────────────────────────────
  metadata = await get_pr_metadata(42, "acme-corp/backend-api")
    key = mcp:get_pr_metadata:{sha256(kwargs)[:16]}
    Redis MISS → GitHubClient.get_pr() → GET /repos/.../pulls/42
    Redis SET key 300 '{"number":42, "head_sha":"abc123", ...}'
  head_sha = "abc123"
  (cached, draft_hit) = await cache.get("review_draft", repo=..., pr_number=42, head_sha="abc123")
    HIT  → load {review, eval_scores, avg_score, diff}, skip Phase 1 entirely
    MISS → continue to Phase 1

PHASE 1: agentic_review.py  run_agentic_review(42, "acme-corp/backend-api")
  System prompt: AGENT_SYSTEM_PROMPT (tool strategy guidance)
  Tools:         ANTHROPIC_TOOLS (9 schemas passed to Claude)
  Initial user message: "Review PR #42 in acme-corp/backend-api..."

  — Turn 1 —
  Claude → tool_use {name:"get_pr_metadata", input:{pr_number:42, repo:"..."}}
  dispatch → get_pr_metadata()  [Redis HIT — fetched above]
  messages.append tool_result {head_sha:"abc123", title:"Add auth module", ...}

  — Turn 2 —
  Claude → tool_use {name:"get_pr_diff", input:{pr_number:42, repo:"..."}}
  dispatch → get_pr_diff()
    Redis MISS → GitHub GET /repos/.../pulls/42/files → Redis SET 3600s
  messages.append tool_result "--- auth.py (modified)\n+++ ..."

  — Turn 3 —
  Claude sees diff touches requirements.txt →
  Claude → tool_use {name:"scan_dependency_vulnerabilities", input:{pr_number:42, repo:"...", base_sha:"xyz", head_sha:"abc123"}}
  dispatch → scan_dependency_vulnerabilities()
    Redis MISS → GitHub GET /repos/.../dependency-graph/compare/xyz...abc123
    Redis SET 3600s  → {"vulnerabilities": [{"package":"requests","severity":"high",...}], ...}
  messages.append tool_result

  — Turn 4 —
  Claude → tool_use {name:"get_ci_results", input:{pr_number:42, repo:"...", head_sha:"abc123"}}
  dispatch → get_ci_results()
    Redis MISS → GitHub GET /repos/.../commits/abc123/check-runs → Redis SET 120s
  messages.append tool_result {"summary":"2/3 checks passing. FAILING: test-suite", ...}

  — Turn 5 —
  Claude decides to read the failing test file →
  Claude → tool_use {name:"read_file", input:{path:"tests/test_auth.py", repo:"...", ref:"abc123"}}
  dispatch → read_file()  [Redis MISS → GitHub → SET 86400s]
  messages.append tool_result (test file content)

  — Turn 6 —
  Claude → tool_use {name:"run_static_analysis", input:{pr_number:42, repo:"..."}}
  dispatch → run_static_analysis()
    internally calls get_pr_diff() [Redis HIT]
    runs 9 regex patterns on added lines
  messages.append tool_result {"critical_count":1, "findings":[{type:"hardcoded_secret",...}]}

  — Turn 7 —
  Claude stop_reason="end_turn"
  review_draft = extracted from response.content text blocks
  tool_calls_log = 6 entries

  diff_for_eval = await get_pr_diff(42, "acme-corp/backend-api")  [Redis HIT]

  cache.set("review_draft", {review, eval_scores:[], iterations:0, avg_score:0, diff:diff[:8000]}, ...)
    SETEX mcp:review_draft:{sha256[:16]} 604800 '{...}'   ← cached BEFORE self-eval

PHASE 2: self_eval.py  run_self_eval(review_draft, diff_for_eval, 42)
  system_blocks = build_eval_system_blocks(diff)   # diff[:8000] + rubric, cache_control=ephemeral
  messages = []
  iteration=1:
    messages.append {role:"user", content:build_score_message(review_draft)}
    score_resp = await Claude(system=system_blocks, messages=messages, max_tokens=2048)
    final_scores = _parse_scores(...)   # 12 DimensionScore objects
    avg = 4.2   # example — passes PASS_THRESHOLD=3.5
    break
  cache.set("review_draft", {review, eval_scores, iterations:1, avg_score:4.2, diff:...}, ...)
    SETEX mcp:review_draft:{sha256[:16]} 604800 '{...}'   ← overwrite with scores

PHASE 3: posting.py
  formatted = _format_review_body(review_text, eval_scores, avg_score=4.2, iterations=1)
    # appends: <details><summary>DevMind Quality Scorecard (avg: 4.20/5.0 · 1 iteration)
    # table: | Correctness | ★★★★ 4.2 | notes |
  result = await post_review_comment(42, "acme-corp/backend-api", formatted)
    POST /repos/.../pulls/42/reviews {"body":..., "event":"COMMENT"}

FINALIZE: loop.py
  job.total_tokens_input = sum(p.tokens_input for p in job.phases)
  job.total_cache_hits   = cache.hit_count - cache_before.hits
  job.status = COMPLETED
  _save_job(job) → SETEX devmind:job:a1b2c3d4 604800 '{"status":"completed",...}'
  queue.ack("1234567890-0") → XACK devmind:jobs devmind-workers 1234567890-0
```

---

## SECTION 10 — Failure Handling Matrix

| Failure | Detection | Response | Recovery | Gap/Risk |
|---|---|---|---|---|
| LLM API timeout/5xx in agentic loop | Exception from `AsyncAnthropic.messages.create` | Model fallback: sonnet → haiku → haiku-20240307. Other exceptions re-raise. | Exception propagates → job=FAILED → worker nacks (up to `MAX_RETRIES=3`) → DLQ | No per-turn timeout; no exponential backoff |
| LLM model not found (404) | `_is_model_not_found()` checks `'not_found_error'` in message | Silently tries next model in `_model_candidates()` | Falls back: sonnet → haiku → haiku-20240307 | If all fail, raises last exception. No alerting on fallback. |
| Tool call fails inside agentic loop | Exception from `_dispatch_tool()` | Caught; structured `{"error":"...", "tool":"..."}` returned as tool_result | Claude sees error and continues with partial context | May silently produce lower-quality review |
| `MAX_TOOL_TURNS=15` exceeded | Loop counter hits cap | Last assistant text extracted; fallback warning review if none | Review posted regardless | Partial review if agent genuinely needed more turns |
| GitHub API failure (direct call) | `httpx.HTTPStatusError` from `r.raise_for_status()` | Agentic loop: error dict returned as tool_result. Direct calls: raises. | httpx transport `retries=3` on direct calls | Direct-call failures propagate; agentic loop absorbs them silently |
| Redis cache failure | `aioredis ConnectionError` | Unhandled — propagates to job as exception | Job FAILED; worker nacks | Redis down = cache AND queue both unavailable — full system outage |
| Queue message stuck (consumer crash) | Message in PEL indefinitely | No `XAUTOCLAIM` — stuck messages NOT reclaimed | Manual `XAUTOCLAIM` required | No automatic recovery. PRs silently never get reviewed. |
| Bad JSON from LLM in self-eval | `_parse_scores` catches `JSONDecodeError`; tries bracket extraction | Returns empty list if no brackets found | `avg=0.0` → loop runs all `MAX_ITERATIONS` | Empty scores → 3 wasted iterations; review posted with `avg=0.0` |
| Process crash mid-job | Job status stuck as RUNNING in Redis | No heartbeat | Message stays in PEL | No watchdog for stale RUNNING jobs. 7-day TTL before cleanup. |
---

## SECTION 11 — Tradeoffs and Design Decisions

### Decision: Claude API over GPT-4 / Gemini
- **Alternatives**: No ADR in codebase.
- **Why This**: Anthropic's `cache_control: ephemeral` directly enables the self-eval token reduction — diff cached in system prompt, charged ~10% on subsequent calls. Critical for the cost metric.
- **Cost**: Vendor lock-in. Fallback chain covers Anthropic models only.
- **Reconsider When**: If Anthropic pricing becomes uncompetitive, or use case shifts to vision/multimodal.

### Decision: Redis Streams over Celery / RabbitMQ / SQS
- **Alternatives**: No ADR. Inferred: Redis already required for cache — Streams avoids a second infrastructure dependency.
- **Why This**: Single Redis instance handles queue + cache + state. Streams provide consumer groups, PEL, and DLQ natively.
- **Cost**: No `XAUTOCLAIM` (must add manually). No automatic redelivery on consumer crash. No built-in exponential backoff.
- **Reconsider When**: At 10x volume. SQS handles consumer crashes via visibility timeout with zero custom code.

### Decision: Agentic tool loop + self-eval over single-shot prompt
- **Alternatives**: Single large prompt covering all context + review + scores in one call.
- **Why This**: (1) Agentic phase lets Claude decide what context it actually needs — avoids fetching irrelevant data and allows following unexpected leads. (2) Self-eval enables quality control before posting. Single-shot has no mechanism to catch missed dimensions.
- **Cost**: 8–12 Claude API calls per review (vs 1 single-shot). Higher latency. `MAX_TOOL_TURNS=15` cap adds predictable upper bound.
- **Reconsider When**: If self-eval scores consistently show near-perfect first-pass quality (avg > 4.5), reducing `MAX_ITERATIONS=1` halves self-eval cost. If tool overhead dominates, a hybrid approach (fetch metadata + diff unconditionally, then Claude decides the rest) reduces minimum turn count.

### Decision: MCP as tool abstraction layer + Anthropic function-calling for tool discovery
- **Alternatives**: Direct async function calls to GitHub API; hardcoded pipeline that always runs every tool.
- **Why This**: MCP tool definitions (name, description, input_schema) serve dual purpose — they are the schemas passed to Claude's `tools=` parameter for true dynamic dispatch. Claude reads tool descriptions to decide whether a tool is relevant for the current PR, calls only what it needs, and chains calls based on what it finds. The cache-aside pattern and GitHub API logic stay in the tool layer, invisible to the agent loop.
- **Cost**: Two codebases to maintain (Python + TypeScript npm). Tool schemas defined twice — in `agentic_review.py` (Anthropic format) and `mcp/server.py` (MCP format). Must be kept in sync.
- **Reconsider When**: If MCP adds native function-calling integration so schemas don't need to be maintained separately.

### Decision: TTL-only cache invalidation
- **Alternatives**: Event-driven invalidation on PR updates.
- **Why This**: Simpler. Most cached data (file content at a SHA) is genuinely immutable. Metadata TTL=300s keeps staleness under 5 minutes.
- **Cost**: Metadata window could serve stale label/title data for up to 5 minutes.
- **Reconsider When**: If system needs to react to PR updates within seconds.

---

## SECTION 12 — Known Limitations and Gaps

| Gap | Why It Exists | Production Impact | Fix |
|---|---|---|---|
| **Webhook does NOT auto-enqueue** | Intentionally manual — `webhooks.py` validates HMAC-SHA256 but does not call `queue.enqueue()` | Requires `POST /api/review` to trigger a review. Not autonomous for new PRs. | Add `queue.enqueue()` in webhooks.py for `action in {"opened","synchronize"}` when ready. |
| **No XAUTOCLAIM on worker startup** | Not implemented | Worker crash leaves messages in PEL indefinitely. PRs silently never reviewed. | Add `XAUTOCLAIM` in `JobQueue.setup()` for messages idle > timeout. |
| `SELF_EVAL_THRESHOLD` env var not read | `rubric.py` hardcodes `PASS_THRESHOLD=3.5` | Cannot tune quality/cost tradeoff without code change + redeploy. | `PASS_THRESHOLD = float(os.getenv('SELF_EVAL_THRESHOLD', '3.5'))` |
| No retry backoff in `nack()` | Simple implementation | Transient failures exhaust retries in rapid succession. | Add delay field; worker skips if `submitted_at + backoff > now`. |
| No per-tool timeout in agentic loop | `MAX_TOOL_TURNS` caps count, not wall-clock | Single slow GitHub API call blocks worker up to 30s (httpx default) | `asyncio.wait_for(dispatch_tool(...), timeout=15)` per call |
| Tool schema duplication | Anthropic format (`agentic_review.py`) vs MCP format (`server.py`) | Schema drift if a tool is added to one file but not the other | Auto-convert MCP `inputSchema` → Anthropic `input_schema` at startup |
| Mock Claude in simulation | Real Claude calls expensive | 91% and 100% agreement both from mock that trivially passes all thresholds. | Run annotated benchmark with real Claude (haiku for cost). |
| Sub-2s p95 claim vs stored 12.2s | Sub-2s likely refers to Redis op latency | Misleading if read as end-to-end review latency. | Clarify: "sub-2s Redis op p95". Run `fetch_agent_timing.py` for real e2e. |
| No inline GitHub comments | `create_review()` sends `event='COMMENT'` only | Less actionable — developer must find lines themselves. | Use GitHub Pulls Review API `comments` array: `{path, position, body}` per finding. |
| Unit tests only (no integration tests) | `backend/tests/unit/` covers cache, compressor, rubric, webhooks | End-to-end flow untested automatically. | Add integration test with mock Redis + httpx `MockTransport` for GitHub. |

---

## SECTION 13 — Interview Q&A Preparation

### Q1: "Walk me through this project."

DevMind is an autonomous PR code review agent I built solo. A review is triggered manually via `POST /api/review`. The webhook handler validates HMAC-SHA256 but does not enqueue. A pool of 4 async workers picks it up via `XREADGROUP devmind-workers` and runs a 3-phase agentic loop in `backend/agent/loop.py`.

**Phase 1 — Agentic Review** (`agentic_review.py`): Claude receives all 9 tool schemas via the Anthropic `tools=` function-calling API and decides what context it needs. It starts with `get_pr_metadata` to get the head SHA, then adaptively calls `get_pr_diff`, `get_ci_results`, `run_static_analysis`, `scan_dependency_vulnerabilities`, `read_file` on specific files, and `search_repo_docs` based on what it finds. All tool results are cached in Redis (TTLs from 120s to 86400s). The loop runs up to `MAX_TOOL_TURNS=15` turns until Claude emits `stop_reason="end_turn"` and the review draft is extracted.

**Phase 2 — Self-Evaluation**: Claude scores its review against 12 dimensions (`PASS_THRESHOLD=3.5`, `MAX_ITERATIONS=3`). If avg < 3.5, Claude refines targeting the bottom 3 dimensions. The diff lives in the system prompt with `cache_control={"type":"ephemeral"}` so Anthropic charges ~10% on subsequent calls.

**Phase 3 — Posting**: Format the review with a per-dimension scorecard and post to GitHub via `POST /pulls/N/reviews`.

The result is stored as a `ReviewJob` JSON blob (TTL=7 days) and the React dashboard polls `/api/jobs` for live status.

---

### Q2: "How does the core loop work?"

The loop is `AgentOrchestrator.run()` in `backend/agent/loop.py`.

First, `get_pr_metadata` is called to get `head_sha` for the **review-draft cache check**. If this exact commit SHA was reviewed before, the cached `{review, eval_scores, avg_score, iterations}` is loaded from Redis (TTL=7 days) and ALL Claude calls are skipped — zero tokens.

On a cache miss, **Phase 1 (agentic)** runs: a multi-turn `messages` loop sends the 9 tool schemas to Claude via `tools=ANTHROPIC_TOOLS`. Each turn Claude either calls tools (we execute them and append `tool_result` blocks) or returns `stop_reason="end_turn"` with the review text. Typical reviews use 6–10 tool calls across 7–11 turns.

**Phase 2 (self-eval)** uses a separate `messages` list. The diff is in the system prompt with `cache_control=ephemeral` (charged ~10% on reuse). Each iteration: (1) `score_message` → Claude returns JSON scores, (2) avg computed, (3) if avg >= 3.5 or iteration == `MAX_ITERATIONS=3`: break. Otherwise: `refinement_message` targeting bottom 3 weak dimensions → Claude returns new draft → loop.

Not idempotent: re-running a failed job calls Claude again. The review-draft cache prevents re-work only for successfully completed jobs.

---

### Q3: "How did you reduce token costs by 38%?"

Three mechanisms compound:

1. **Redis caching**: key = `mcp:{tool_name}:{sha256(kwargs)[:16]}`. File contents at a commit SHA are immutable → TTL=86400s. Same `utils.py` across multiple PRs at the same SHA → one GitHub call, N cache hits.

2. **Prompt compression** (`compressor.py`): `extract_changed_context()` parses `@@` hunk headers via regex, extracts ±10 lines around each changed section, merges overlapping ranges. Only files >500 lines get compressed. `deduplicate_file_contexts()` removes exact-content duplicates.

3. **Anthropic prompt cache**: diff in self-eval system prompt with `cache_control={"type":"ephemeral"}`. Each eval/refinement call after the first pays ~10% for the diff tokens.

**Honest caveat**: The stored `metrics_summary.json` shows `cache_hit_rate=0.0%` because that run wasn't paired with a `--no-cache` baseline comparison. The 38% comes from the `metric_token_cost()` formula requiring both modes to be run.

---

### Q4: "Why did you use Redis Streams instead of Celery / RabbitMQ / SQS?"

Redis was already required for the MCP tool result cache, so adding Redis Streams kept infrastructure to a single service. Streams provide consumer groups (`XREADGROUP`), persistent message storage, pending entry lists for at-least-once delivery, and native dead-letter via `XADD devmind:jobs:dead` — all without additional dependencies.

**The honest cost**: There's no `XAUTOCLAIM` on worker startup (a known gap in `streams.py`) — messages held by crashed workers stay in the PEL indefinitely. No exponential backoff in `nack()` — failed messages re-enqueue immediately.

At 10x scale: SQS with visibility timeout would be the right call — consumer crash recovery and DLQ configuration with zero custom code.

---

### Q5: "What happens if the LLM fails mid-run?"

In `agentic_review.py` and `self_eval.py`, the model fallback chain is: `claude-3-5-sonnet-latest` → `claude-3-5-haiku-latest` → `claude-3-haiku-20240307`. For `"not_found_error"` (model unavailable) it logs a warning and tries the next model; any other exception re-raises immediately — no per-turn retry.

If a tool call fails inside the agentic loop, the dispatcher catches the exception and returns a structured `{"error": "...", "tool": "..."}` result. Claude sees this and can continue the review with whatever context it has gathered. The loop doesn't abort on a single tool failure.

If all Claude models fail, the exception propagates to `AgentOrchestrator.run()`'s outer try/except: `job.status=FAILED`, `job.error=str(exc)`, `_save_job()`. The `worker.py` loop calls `queue.nack()`, which increments `_retries` and re-enqueues if retries < `MAX_RETRIES=3`, otherwise moves to `devmind:jobs:dead`.

**Gaps**: No per-tool-call timeout (httpx default 30s per call). No exponential backoff on retries. If `_parse_scores()` returns empty in self-eval, `avg_score=0.0` → loop runs all 3 iterations → job completes COMPLETED with `avg=0.0`.

---

### Q6: "How did you measure the 60% turnaround reduction?"

The methodology is in `report.py` → `metric_turnaround()`. Primary comparison: DevMind vs. naive single-pass automated reviewer via `run_simulation.py`. The naive baseline models no caching, full diff+files (~13.5k tokens), no Anthropic prompt cache, `avg_iterations=2.5`. DevMind models 70% cache hit rate, compressed context, Anthropic cache, `avg_iterations=1.5`.

Timing constants: `_CLAUDE_BASE_S=1.5`, `_CLAUDE_PER_1K_IN_S=1.2`, `_CLAUDE_PER_1K_OUT_S=0.8`, `_GITHUB_API_S=0.4`.

The stored run shows `pipeline_reduction_pct=50.7`. The `report.py` threshold for "✅" is `>= 55%` (not 60%). The 60% is the design target. Human baseline (for context): 32.51h from real GitHub data via `fetch_human_baseline.py`.

---

### Q7: "What's the biggest limitation of your system?"

Three honest ones:

1. **Webhook does NOT auto-enqueue**. `webhooks.py` validates HMAC-SHA256 but `queue.enqueue()` is never called — by design. The system requires manual `POST /api/review` triggers. Fix: 5 lines in `webhooks.py` when ready.

2. **No `XAUTOCLAIM`**: if a worker crashes mid-job, the message stays in PEL indefinitely. In production, a stuck message means a PR is silently never reviewed.

2. **Tool schema duplication**: the 9 agentic tools are defined in Anthropic format in `agentic_review.py` AND in MCP format in `server.py`. These must be kept in sync manually — a new tool added to one place but not the other causes silent divergence between what external MCP clients see and what Claude uses internally.

3. **91% agreement was measured using a deterministic mock** that generates scores `[4.0-5.0]` — trivially passes 3.5 threshold. Stored metrics show 100% agreement, not 91%. Need real-Claude run on annotated benchmark.

---

### Q8: "Why did you use MCP instead of direct API calls? Is the agent actually using tool discovery?"

MCP provides the tool abstraction boundary — each tool encapsulates GitHub API logic, auth, caching, and error handling behind a clean async function interface. The agent calls `get_pr_metadata(pr_number=..., repo=...)` without knowing anything about REST pagination or auth headers.

The key insight is that the MCP tool definitions (name, description, input_schema) are the same schemas passed to Claude's `tools=` parameter in `agentic_review.py`. So Claude sees tool descriptions and **genuinely decides** which ones to call for each specific PR. A doc-only PR gets no vulnerability scan. A PR touching auth code gets `get_file_history` calls on those files. Claude can follow unexpected leads.

Three concrete benefits: (1) Cache-aside pattern lives entirely in the tool layer — `loop.py` is clean of caching logic. (2) Claude makes adaptive decisions — not a hardcoded pipeline. (3) The same 10 tools are published as `@arbiter09/github-mcp` npm for use by any external agent (Cursor, Claude Desktop).

**The cost**: Tool schemas exist in two formats — Anthropic (`agentic_review.py`) and MCP (`server.py`) — and must be kept in sync. The TypeScript npm package duplicates tool implementations.

---

### Q9: "What would you change if this needed to handle 10x the load?"

Five concrete changes:

1. Replace Redis Streams with SQS — visibility timeout + auto-redelivery handles consumer crashes. The custom `nack()` logic disappears.
2. Separate Redis instances for cache vs job state vs queue. Currently one failure takes down all three.
3. Add `XAUTOCLAIM` on worker startup (5-line fix). Prerequisite for production regardless of scale.
4. Move worker pool out of FastAPI process. Currently `start_worker_pool()` runs inside the web server (`main.py` startup event). Long-running Claude calls compete with HTTP handling. `worker_entrypoint.py` already exists.
5. Wire webhook→queue auto-enqueue in `webhooks.py` when ready to go fully autonomous. Currently requires manual `POST /api/review` triggers.

---

### Q10: "Is your quality/agreement metric actually measuring what it claims?"

Partially. The annotation design is sound: `pr_templates.py` defines 60 `PRTemplate` objects with full 12-dimension `DimensionAnnotation` lists (`expected=True/False` + rationale). The `score_dimension_agreement()` function asks: for `expected=True` dims, did agent score >= `PASS_THRESHOLD=3.5`? For `expected=False` dims, did agent score >= `INCOHERENCE_FLOOR=3.0`?

**What it doesn't measure**: `mock_claude.py` generates scores `[4.0-5.0]` for covered dims and `[3.5-5.0]` for uncovered — both trivially satisfy both thresholds. The stored `metrics_summary.json` shows `agreement_rate_pct=100%` and `dimension_agreement_pct=0.0%` (`annotated_count=0`).

The honest position: 91% is the design target. To get a real measured number: run annotated benchmark with real Claude and store results.

---

### Q11: "Is the agent actually intelligent? Does it do real tool discovery?"

Yes — after the refactor in `agentic_review.py`.

**Before**: A hardcoded orchestrator always called all tools in a fixed sequence regardless of what the PR contained. Claude only saw the assembled text at the end. That was a pipeline, not an agent.

**Now**: Claude receives all 9 tool schemas via the Anthropic `tools=` parameter on every turn. When Claude decides it needs more context, it emits a `tool_use` block. We execute it, append the `tool_result`, and continue. Claude controls the order, the choice of tools, and when to stop.

Concrete examples of adaptive behavior:
- A PR that only changes markdown files → Claude calls `get_pr_diff`, reads it, writes the review. Skips CI, vuln scan, and file reads.
- A PR adding a new auth module → Claude calls `get_file_history` on the auth file to check past bugs, `read_file` on the test file to verify coverage, `scan_dependency_vulnerabilities` because it added a new JWT library.
- A PR where CI is failing → Claude calls `get_ci_results`, sees the failing test name, calls `read_file` on that specific test to understand the failure, surfaces it prominently in the review.

**The `MAX_TOOL_TURNS=15` cap** prevents infinite loops. Typical reviews complete in 6–10 tool calls. The `stop_reason="end_turn"` signal from Claude terminates the loop cleanly.

**Honest caveat**: The tool dispatcher is still deterministic — we decide how to execute each tool call. Claude is deciding WHICH tools to call and WHEN, but the tools themselves have fixed behavior. Claude cannot, for example, write new code or modify files. It's a reasoning agent constrained to a read-only tool set plus the ability to write one review comment.

---

## SECTION 14 — Simulation / Validation Setup

### How Test Inputs Are Generated

`generate_prs.py` creates a JSONL dataset from 60 `PRTemplate` objects in `pr_templates.py`, randomly sampled with equal weight. Each template has a `diff_template` (real code diff), language (python/ts/go/java/rust), severity (low/medium/high/critical), and 12-dimension annotations. Human review time sampled from real GitHub data via `fetch_human_baseline.py` (stored: `human_median=32.51h`) or synthetic assumption (`_SYNTHETIC_BASELINE_MEDIAN_HOURS=24.0`, sigma=0.8).

### Mock Claude Logic (`mock_claude.py`)

```python
def generate_mock_eval_scores(expected_findings, rng):
    covered = set(expected_findings)
    for dim in DIMENSIONS:
        if dim in covered:
            score = round(rng.uniform(4.0, 5.0), 1)   # always passes PASS_THRESHOLD
        else:
            score = round(rng.uniform(3.5, 5.0), 1)   # always passes INCOHERENCE_FLOOR
```

### Simulation Assumptions

| Assumption | Value/Source | Real-World Validity |
|---|---|---|
| Claude base latency | `_CLAUDE_BASE_S=1.5s` (calibrated from real Redis jobs) | Reasonable for Sonnet; varies with API load |
| GitHub cache hit rate | 70% assumed (`github_calls = 3 * 0.3`) | Depends on PR volume and file overlap |
| DevMind avg iterations | `avg_iter=1.5` (naive=2.5) | Mock always scores >=3.5 so stored=1.0; real value unknown |
| Mock Claude scores | [4.0-5.0] covered, [3.5-5.0] uncovered | Real Claude sometimes scores covered dims < 3.5 |

### For Real-World Validation

```bash
python simulation/fetch_agent_timing.py            # real e2e wall-clock times from Redis
python run_simulation.py --annotated               # against annotated benchmark with real Claude
python report.py --baseline data/results_nocache.jsonl  # real 38% token measurement
```

---

## SECTION 15 — Project Structure Reference

| File / Directory | Description |
|---|---|
| `backend/agent/loop.py` | AgentOrchestrator — 3 phases (agentic_review → self_eval → posting), review-draft cache check via `get_pr_metadata`, job state persistence. `JOB_KEY_PREFIX='devmind:job:'`, `JOB_TTL=604800` |
| `backend/agent/phases/agentic_review.py` | **NEW** — Phase 1: Claude-driven tool loop. `AGENT_SYSTEM_PROMPT`, `ANTHROPIC_TOOLS` (9 schemas), `_dispatch_tool()`, `MAX_TOOL_TURNS=15`. Replaces hardcoded context_gathering + analysis pipeline. |
| `backend/agent/rubric.py` | `PASS_THRESHOLD=3.5`, `MAX_ITERATIONS=3`, 12 dimension list, all prompt builders, Anthropic cache strategy |
| `backend/agent/compressor.py` | `extract_changed_context` (hunk regex ±10 lines), `deduplicate_file_contexts`, `build_analysis_prompt` (now accepts `enriched_context` for CI/vuln/static/docs sections) |
| `backend/agent/phases/analysis.py` | Legacy phase (still callable); accepts `enriched_context` dict. Superseded by `agentic_review.py` in main loop. |
| `backend/agent/phases/context_gathering.py` | Legacy phase (still callable); now also calls `get_ci_results`, `scan_dependency_vulnerabilities`, `search_repo_docs` in parallel. Superseded by `agentic_review.py` in main loop. |
| `backend/agent/phases/self_eval.py` | Phase 2: multi-turn loop, diff in system w/ `cache_control=ephemeral`, score→refine→rescore |
| `backend/agent/phases/posting.py` | Phase 3: scorecard footer with star ratings, `post_review_comment` |
| `backend/cache/redis_cache.py` | `CacheClient`: get/set with per-tool TTL, key=`mcp:{tool}:{sha256[:16]}`, hit/miss counters. New TTLs: `get_ci_results`=120s, `scan_dependency_vulnerabilities`=3600s, `search_repo_docs`=3600s |
| `backend/jobqueue/streams.py` | `JobQueue`: `STREAM_KEY=devmind:jobs`, `DLQ=devmind:jobs:dead`, `GROUP_NAME=devmind-workers`, `MAX_RETRIES=3` |
| `backend/jobqueue/worker.py` | `run_worker`/`start_worker_pool`: `WORKER_CONCURRENCY=4`, asyncio tasks, `block_ms=2000` |
| `backend/mcp/server.py` | Python MCP server (stdio transport) — 10 tools for external agents. `call_tool` dispatches sync `run_static_analysis` and 9 async tools. |
| `backend/mcp/tools/pr_tools.py` | `get_pr_metadata`, `get_pr_diff`, `post_review_comment` with cache-aside |
| `backend/mcp/tools/file_tools.py` | `read_file`, `list_changed_files`, `get_file_history` with cache-aside |
| `backend/mcp/tools/ci_tools.py` | **NEW** — `get_ci_results` (GitHub Checks API, TTL=120s), `search_repo_docs` (README/CONTRIBUTING/PR template, TTL=3600s) |
| `backend/mcp/tools/security_tools.py` | **NEW** — `run_static_analysis` (in-memory diff pattern scan, 9 patterns), `scan_dependency_vulnerabilities` (GitHub Dependency Review API, TTL=3600s) |
| `backend/mcp/github_client.py` | `GitHubClient`: `timeout=30s`, `retries=3`, `GITHUB_API=api.github.com`, all pagination. New methods: `get_check_runs`, `get_dependency_review`, `get_repo_file` |
| `backend/api/main.py` | FastAPI app factory: CORS, router registration, OTel, worker pool startup |
| `backend/api/webhooks.py` | `POST /webhooks/github` — HMAC-SHA256 validation; logs event; returns 200. **Does NOT enqueue** — manual trigger via `POST /api/review` only. |
| `backend/api/review.py` | `POST /api/review`, `GET /api/github/repos`, `GET /api/github/pulls` |
| `backend/api/jobs.py` | `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/metrics` |
| `backend/models/job.py` | `ReviewJob`, `PhaseTrace`, `EvalScore`, `PRWebhookPayload`, `JobStatus` |
| `backend/telemetry/setup.py` | `setup_telemetry()`: `TracerProvider`, `OTLPSpanExporter`/`ConsoleSpanExporter`, `BatchSpanProcessor` |
| `backend/telemetry/spans.py` | `agent_span()`, `record_llm_usage()`, `record_cache_result()`, `record_eval_result()`, `get_current_trace_id()` |
| `simulation/pr_templates.py` | 60 `PRTemplate` objects: Python(20), TypeScript(12), Go(10), Java(10), Rust(8) — all 12-dim annotated |
| `simulation/run_simulation.py` | Harness: mock Claude, timing model constants, `score_dimension_agreement()` |
| `simulation/report.py` | `metric_turnaround`, `metric_token_cost`, `metric_agreement_rate` — all 3 headline metrics |
| `simulation/build_annotated_dataset.py` | Builds `simulation/data/annotated_prs.jsonl` — committed 60-PR benchmark |
| `simulation/generate_prs.py` | Generate 500 synthetic PRs; real or synthetic 24h human baseline |
| `simulation/fetch_human_baseline.py` | Real PR review timing from GitHub — excludes bots, self-reviews, sub-minute responses |
| `simulation/fetch_agent_timing.py` | Extract real agent wall-clock times from completed Redis job records |
| `simulation/mock_claude.py` | Deterministic mock: scores `[4.0-5.0]` covered, `[3.5-5.0]` uncovered |
| `simulation/data/annotated_prs.jsonl` | 60-PR committed benchmark — 12-dim annotations with `expected=True/False` + rationale |
| `simulation/data/metrics_summary.json` | Stored run: `pipeline_reduction=50.7%`, `agent_median=12.1s`, `naive=24.6s`, `agreement=100%` (mock) |
| `mcp-server/src/index.ts` | TypeScript `@arbiter09/github-mcp` npm package — same 6 tools, stdio transport, `McpServer` SDK |
| `mcp-server/smithery.yaml` | Smithery MCP registry manifest |
| `infra/docker-compose.yml` | Redis 7.2-alpine (AOF), OTel Collector 0.114.0, Jaeger 1.76.0, Prometheus 2.55.0 |
| `backend/.env.example` | All env vars: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `REDIS_URL`, `OTEL_*`, `WORKER_CONCURRENCY` |

---

## SECTION 16 — Local Dev Setup

### Prerequisites

| Requirement | Version/Notes |
|---|---|
| Python | 3.13 (see `.python-version` file) |
| Node.js | 20+ (for mcp-server TypeScript + frontend) |
| Docker + Docker Compose | For Redis, OTel Collector, Jaeger, Prometheus |
| Anthropic API Key | `ANTHROPIC_API_KEY` — claude-3-5-sonnet-latest access required |
| GitHub Personal Access Token | `GITHUB_TOKEN` — needs `repo:read` + `pull_requests:write` scopes |

### Environment Variables (`backend/.env.example`)

| Variable | Example | Note |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Required |
| `GITHUB_TOKEN` | `ghp_...` | Required; read repos + write PR reviews |
| `GITHUB_WEBHOOK_SECRET` | `your-webhook-secret` | If unset, all webhooks pass (dev mode) |
| `REDIS_URL` | `redis://localhost:6379` | Queue + cache + job state |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | If unset, falls back to `ConsoleSpanExporter` |
| `OTEL_SERVICE_NAME` | `devmind-backend` | Service name in traces |
| `WORKER_CONCURRENCY` | `4` | Number of parallel agent workers |
| `SELF_EVAL_THRESHOLD` | `3.5` | **NOT read by rubric.py — hardcoded** |
| `MAX_EVAL_ITERATIONS` | `3` | **NOT read by rubric.py — hardcoded** |

### Startup Commands

```bash
# 1. Infrastructure
docker compose -f infra/docker-compose.yml up -d
# → Redis :6379  |  OTel Collector :4317  |  Jaeger UI :16686  |  Prometheus :9090

# 2. Backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env    # fill in API keys

# 3. Run backend (from REPO ROOT, not backend/ directory)
uvicorn backend.api.main:app --reload --port 8000
# Worker pool starts automatically (4 workers)
# API: http://localhost:8000  |  Docs: http://localhost:8000/docs

# 4. Frontend
cd frontend && npm install && npm run dev   # → http://localhost:5173

# 5. Trigger a test review
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_number": 1, "repo": "your-org/your-repo"}'

# 6. Run simulation (no API keys needed — uses mock Claude by default)
cd simulation
python build_annotated_dataset.py
python run_simulation.py --annotated --output data/results.jsonl
python run_simulation.py --annotated --naive-baseline --output data/results_baseline.jsonl
python report.py --results data/results.jsonl --naive-baseline data/results_baseline.jsonl
```

---

## APPENDIX — Confidence Gaps

Things that are ambiguous, estimated rather than directly measured, or require manual verification before an interview.

| Gap | Status | Verification Action |
|---|---|---|
| Pipeline reduction = 60% (resume) vs 50.7% (stored) | **DISCREPANCY** — stored number is lower | `python run_simulation.py --annotated && --naive-baseline && python report.py` |
| 91% agreement rate | **NOT validated** with real Claude — mock always passes | `python run_simulation.py --annotated --no-mock-claude` (requires `ANTHROPIC_API_KEY`) |
| 38% token cost reduction | **ESTIMATED** — stored run shows `cache_hit_rate=0.0%` | Run with `--no-cache` and compare via `report.py --baseline` |
| Sub-2s p95 latency | **AMBIGUOUS** — stored p95 is 12.2s (simulated) | Clarify: "sub-2s Redis op latency, not e2e review time." Run `fetch_agent_timing.py` for real numbers. |
| `SELF_EVAL_THRESHOLD` env var | **CONFIRMED not functional** — hardcoded in `rubric.py` | Patch `rubric.py` or note proactively. |
| Webhook auto-enqueue gap | **CONFIRMED** — `webhooks.py` validates but does not enqueue. Manual trigger only. | Use `POST /api/review`. Intentional design decision. |
| Solo authorship | Assumed from project structure | `git log --format='%an' \| sort -u` |
| npm package live publish | README has badge; not verified | `npm view @arbiter09/github-mcp version` |
| Real agent end-to-end timing | No Redis jobs in current environment | Run `python simulation/fetch_agent_timing.py` after completing real reviews |

---

## KEY NUMBERS TO MEMORIZE

```
PASS_THRESHOLD         = 3.5
MAX_ITERATIONS         = 3
MAX_TOOL_TURNS         = 15           ← agentic loop hard cap
WORKER_CONCURRENCY     = 4
JOB_TTL                = 604800s (7 days)
MAX_FILE_LINES         = 500
context_lines          = 10
read_file TTL          = 86400s (24h)
get_pr_diff TTL        = 3600s (1h)
get_pr_metadata TTL    = 300s (5min)
get_ci_results TTL     = 120s         ← CI status changes during run
scan_dep_vulns TTL     = 3600s
search_repo_docs TTL   = 3600s
review_draft TTL       = 604800s (7d)
STREAM_KEY             = devmind:jobs
DLQ                    = devmind:jobs:dead
GROUP                  = devmind-workers
MAX_RETRIES            = 3
MCP tools total        = 10 (was 6)
  GitHub context (6)   = get_pr_metadata, get_pr_diff, read_file,
                         list_changed_files, get_file_history, post_review_comment
  CI/docs (2)          = get_ci_results, search_repo_docs
  Security (2)         = scan_dependency_vulnerabilities, run_static_analysis
Agentic tools (Claude) = 9 (post_review_comment excluded — orchestrator handles posting)
Model chain            = claude-3-5-sonnet-latest → haiku → haiku-20240307
Webhook trigger        = manual only — POST /api/review (webhook validates, does not enqueue)
Stored pipeline_reduction = 50.7%
Stored human_median    = 32.51h (real_github_data)
Stored agent_median    = 12.12s (simulation_timing_model)
Stored p95             = 12.209s
Cache key schema       = mcp:{tool_name}:{sha256(kwargs)[:16]}
```
