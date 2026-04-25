import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { api, type ReviewJob } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";

export function LiveFeed() {
  const [jobs, setJobs] = useState<ReviewJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerRepo, setTriggerRepo] = useState("");
  const [triggerPR, setTriggerPR] = useState("");

  const refresh = useCallback(async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(refresh, 3000);

  const handleTrigger = async () => {
    if (!triggerRepo || !triggerPR) return;
    await api.triggerReview(parseInt(triggerPR), triggerRepo);
    setTriggerRepo("");
    setTriggerPR("");
    refresh();
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">Live Feed</h2>
          <p className="text-sm text-gray-500 mt-0.5">Real-time stream of agent review jobs</p>
        </div>
        {/* Manual trigger */}
        <div className="flex items-center gap-2">
          <input
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 w-40 focus:outline-none focus:ring-1 focus:ring-brand-500"
            placeholder="owner/repo"
            value={triggerRepo}
            onChange={(e) => setTriggerRepo(e.target.value)}
          />
          <input
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 w-20 focus:outline-none focus:ring-1 focus:ring-brand-500"
            placeholder="PR #"
            value={triggerPR}
            onChange={(e) => setTriggerPR(e.target.value)}
          />
          <button
            onClick={handleTrigger}
            className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-colors"
          >
            Review
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-500 text-sm">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-20 text-gray-600">
          <p className="text-4xl mb-3">🤖</p>
          <p className="font-medium text-gray-400">No jobs yet</p>
          <p className="text-sm mt-1">Trigger a review or set up the GitHub webhook</p>
        </div>
      ) : (
        <div className="space-y-2">
          {jobs.map((job) => (
            <Link
              key={job.id}
              to={`/inspect/${job.id}`}
              className="flex items-center justify-between p-4 bg-gray-900 border border-gray-800 rounded-xl hover:border-gray-600 transition-colors group"
            >
              <div className="flex items-center gap-4">
                <StatusBadge status={job.status} />
                <div>
                  <p className="text-sm font-medium text-white">
                    {job.repo} <span className="text-gray-500">#{job.pr_number}</span>
                  </p>
                  <p className="text-xs text-gray-600 mt-0.5">
                    {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-6 text-right">
                {job.avg_eval_score !== null && (
                  <div>
                    <p className="text-xs text-gray-500">Eval score</p>
                    <p className="text-sm font-mono font-semibold text-white">
                      {job.avg_eval_score.toFixed(2)}
                    </p>
                  </div>
                )}
                {job.total_tokens_input > 0 && (
                  <div>
                    <p className="text-xs text-gray-500">Tokens</p>
                    <p className="text-sm font-mono font-semibold text-white">
                      {(job.total_tokens_input + job.total_tokens_output).toLocaleString()}
                    </p>
                  </div>
                )}
                <span className="text-gray-600 group-hover:text-gray-400 transition-colors">→</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
