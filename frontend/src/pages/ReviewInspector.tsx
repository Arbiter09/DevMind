import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, type ReviewJob } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { DimensionScoreBar } from "../components/DimensionScoreBar";
import { SpanTimeline } from "../components/SpanTimeline";
import { usePolling } from "../hooks/usePolling";

export function ReviewInspector() {
  const { jobId } = useParams<{ jobId?: string }>();
  const navigate = useNavigate();
  const [searchId, setSearchId] = useState(jobId ?? "");
  const [job, setJob] = useState<ReviewJob | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!searchId) return;
    try {
      const data = await api.getJob(searchId);
      setJob(data);
      setError("");
    } catch {
      setError("Job not found");
    }
  }, [searchId]);

  usePolling(load, 3000, !!searchId && job?.status !== "completed" && job?.status !== "failed");

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white">Review Inspector</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Drill into a single PR review — phases, Claude I/O, and self-eval scores
        </p>
      </div>

      <div className="flex gap-2">
        <input
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 flex-1 max-w-md focus:outline-none focus:ring-1 focus:ring-brand-500"
          placeholder="Job ID"
          value={searchId}
          onChange={(e) => setSearchId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <button
          onClick={load}
          className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          Inspect
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {job && (
        <div className="grid grid-cols-3 gap-4">
          {/* Left: overview + timeline */}
          <div className="col-span-2 space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="font-semibold text-white">
                    {job.repo} <span className="text-gray-500">#{job.pr_number}</span>
                  </p>
                  <p className="text-xs text-gray-600 mt-0.5 font-mono">{job.id}</p>
                </div>
                <StatusBadge status={job.status} />
              </div>

              <div className="grid grid-cols-4 gap-3 mb-5">
                {[
                  { label: "Tokens in", value: job.total_tokens_input.toLocaleString() },
                  { label: "Tokens out", value: job.total_tokens_output.toLocaleString() },
                  { label: "Cache hits", value: job.total_cache_hits.toString() },
                  { label: "Iterations", value: job.eval_iterations.toString() },
                ].map((stat) => (
                  <div key={stat.label} className="bg-gray-800 rounded-lg p-3">
                    <p className="text-xs text-gray-500">{stat.label}</p>
                    <p className="text-lg font-mono font-semibold text-white">{stat.value}</p>
                  </div>
                ))}
              </div>

              <SpanTimeline phases={job.phases} />
            </div>

            {/* Review body */}
            {job.review_body && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Generated Review</h3>
                <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed overflow-auto max-h-96">
                  {job.review_body}
                </pre>
              </div>
            )}

            {job.error && (
              <div className="bg-red-900/20 border border-red-800 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-red-400 mb-2">Error</h3>
                <pre className="text-xs text-red-300 font-mono">{job.error}</pre>
              </div>
            )}
          </div>

          {/* Right: eval scores */}
          <div className="space-y-4">
            {job.eval_scores.length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-300">Self-Eval Scores</h3>
                  {job.avg_eval_score !== null && (
                    <span className="text-lg font-mono font-bold text-white">
                      {job.avg_eval_score.toFixed(2)}
                      <span className="text-xs text-gray-500">/5</span>
                    </span>
                  )}
                </div>
                <DimensionScoreBar scores={job.eval_scores} />
              </div>
            )}

            {job.trace_id && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-1">Trace ID</p>
                <a
                  href={`http://localhost:16686/trace/${job.trace_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs font-mono text-brand-400 hover:text-brand-300 break-all"
                >
                  {job.trace_id}
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
