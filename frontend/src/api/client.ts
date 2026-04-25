const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export interface EvalScore {
  dimension: string;
  score: number;
  notes: string;
}

export interface PhaseTrace {
  phase: string;
  started_at: string;
  ended_at: string | null;
  tokens_input: number;
  tokens_output: number;
  cache_hits: number;
  cache_misses: number;
  details: Record<string, unknown>;
}

export interface ReviewJob {
  id: string;
  pr_number: number;
  repo: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  review_body: string | null;
  eval_scores: EvalScore[];
  eval_iterations: number;
  avg_eval_score: number | null;
  total_tokens_input: number;
  total_tokens_output: number;
  total_cache_hits: number;
  total_cache_misses: number;
  phases: PhaseTrace[];
  trace_id: string | null;
}

export interface Metrics {
  total_jobs: number;
  completed: number;
  failed: number;
  pending: number;
  tokens: { total_input: number; total_output: number; total: number };
  cache: { hits: number; misses: number; hit_rate: number };
  quality: { avg_eval_score: number | null; avg_iterations: number | null };
}

export const api = {
  getJobs: (limit = 50) =>
    request<ReviewJob[]>(`/jobs?limit=${limit}`),

  getJob: (id: string) =>
    request<ReviewJob>(`/jobs/${id}`),

  getMetrics: () =>
    request<Metrics>("/metrics"),

  triggerReview: (pr_number: number, repo: string) =>
    request<{ job_id: string; status: string }>("/review", {
      method: "POST",
      body: JSON.stringify({ pr_number, repo }),
    }),
};
