# DevMind Simulation Harness

Replays 500+ synthetic pull requests through the agent to measure the three headline metrics:

| Metric | Target | How Measured |
|---|---|---|
| PR review turnaround | ↓ 60% | wall-clock time per review vs. human baseline (24h median) |
| Claude API token costs | ↓ 38% | tokens used with caching vs. without (cold-cache run) |
| Reviewer agreement rate | 91% | avg self-eval score ≥ 3.5/5 (proxy for expert agreement) |

## Quick Start

```bash
cd simulation
pip install -r requirements.txt

# Generate 500 synthetic PRs
python generate_prs.py --count 500 --output data/prs.jsonl

# Run the agent against all PRs (uses mock GitHub, no real API calls)
python run_simulation.py --input data/prs.jsonl --output data/results.jsonl

# Compute and print the three headline metrics
python report.py --results data/results.jsonl
```

## Flags

| Flag | Description |
|---|---|
| `--count N` | Number of PRs to simulate (default: 500) |
| `--concurrency N` | Parallel workers (default: 8) |
| `--no-cache` | Disable Redis caching (measures baseline token cost) |
| `--mock-claude` | Use deterministic mock responses (fast, no API cost) |
| `--seed N` | Random seed for reproducible PR generation |
