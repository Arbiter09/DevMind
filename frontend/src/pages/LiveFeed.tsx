import { useState, useCallback, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import {
  api,
  type GitHubPull,
  type GitHubRepo,
  type ReviewJob,
} from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { usePolling } from "../hooks/usePolling";

export function LiveFeed() {
  const RECENT_REPOS_KEY = "devmind.recentRepos";
  const [jobs, setJobs] = useState<ReviewJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerRepo, setTriggerRepo] = useState("");
  const [triggerPR, setTriggerPR] = useState("");
  const [showFailed, setShowFailed] = useState(false);
  const [latestAttemptOnly, setLatestAttemptOnly] = useState(true);
  const [githubRepos, setGitHubRepos] = useState<GitHubRepo[]>([]);
  const [repoPulls, setRepoPulls] = useState<GitHubPull[]>([]);
  const [githubError, setGitHubError] = useState("");
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingPulls, setLoadingPulls] = useState(false);
  const [recentRepos, setRecentRepos] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(RECENT_REPOS_KEY);
      const parsed = raw ? (JSON.parse(raw) as string[]) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });

  const rememberRepo = (repo: string) => {
    const trimmed = repo.trim();
    if (!trimmed) return;

    setRecentRepos((prev) => {
      const next = [trimmed, ...prev.filter((r) => r !== trimmed)].slice(0, 10);
      localStorage.setItem(RECENT_REPOS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const repoOptions = useMemo(() => {
    const fromJobs = jobs.map((job) => job.repo).filter(Boolean);
    const fromGitHub = githubRepos.map((repo) => repo.full_name).filter(Boolean);
    return Array.from(new Set([...fromGitHub, ...recentRepos, ...fromJobs])).slice(0, 50);
  }, [githubRepos, jobs, recentRepos]);

  const visibleJobs = useMemo(() => {
    const sorted = [...jobs].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    const filtered = showFailed ? sorted : sorted.filter((j) => j.status !== "failed");

    if (!latestAttemptOnly) return filtered;

    const byPr = new Map<string, ReviewJob>();
    for (const job of filtered) {
      const key = `${job.repo}#${job.pr_number}`;
      if (!byPr.has(key)) {
        byPr.set(key, job);
      }
    }
    return Array.from(byPr.values());
  }, [jobs, latestAttemptOnly, showFailed]);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(refresh, 3000);

  const loadRepos = useCallback(async () => {
    setLoadingRepos(true);
    setGitHubError("");
    try {
      const repos = await api.getGitHubRepos();
      setGitHubRepos(repos);
    } catch (err) {
      setGitHubError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setLoadingRepos(false);
    }
  }, []);

  const loadPulls = useCallback(async (repo: string) => {
    if (!repo.trim()) {
      setRepoPulls([]);
      return;
    }
    setLoadingPulls(true);
    setGitHubError("");
    try {
      const pulls = await api.getGitHubPulls(repo.trim(), "open");
      setRepoPulls(pulls);
    } catch (err) {
      setGitHubError(err instanceof Error ? err.message : "Failed to load PRs");
      setRepoPulls([]);
    } finally {
      setLoadingPulls(false);
    }
  }, []);

  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  useEffect(() => {
    setTriggerPR("");
    void loadPulls(triggerRepo);
  }, [triggerRepo, loadPulls]);

  const handleTrigger = async () => {
    if (!triggerRepo || !triggerPR) return;
    const repo = triggerRepo.trim();
    await api.triggerReview(parseInt(triggerPR), repo);
    rememberRepo(repo);
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
          <select
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 w-56 focus:outline-none focus:ring-1 focus:ring-brand-500"
            value={triggerRepo}
            onChange={(e) => setTriggerRepo(e.target.value)}
          >
            <option value="">
              {loadingRepos ? "Loading repos..." : "Select repository"}
            </option>
            {repoOptions.map((repo) => (
              <option key={repo} value={repo}>
                {repo}
              </option>
            ))}
          </select>
          <select
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 w-64 focus:outline-none focus:ring-1 focus:ring-brand-500"
            value={triggerPR}
            onChange={(e) => setTriggerPR(e.target.value)}
            disabled={!triggerRepo || loadingPulls}
          >
            <option value="">
              {!triggerRepo
                ? "Select repo first"
                : loadingPulls
                  ? "Loading open PRs..."
                  : repoPulls.length
                    ? "Select open PR"
                    : "No open PRs found"}
            </option>
            {repoPulls.map((pr) => (
              <option key={pr.number} value={String(pr.number)}>
                #{pr.number} - {pr.title}
              </option>
            ))}
          </select>
          <button
            onClick={handleTrigger}
            disabled={!triggerRepo || !triggerPR}
            className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-colors"
          >
            Review
          </button>
          <button
            onClick={loadRepos}
            className="bg-gray-800 hover:bg-gray-700 text-gray-200 px-3 py-1.5 rounded-lg text-sm border border-gray-700 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setLatestAttemptOnly((v) => !v)}
          className={`px-3 py-1 text-xs rounded-md border transition-colors ${
            latestAttemptOnly
              ? "bg-gray-700 text-white border-gray-600"
              : "bg-gray-900 text-gray-300 border-gray-700 hover:bg-gray-800"
          }`}
        >
          Latest attempt only
        </button>
        <button
          onClick={() => setShowFailed((v) => !v)}
          className={`px-3 py-1 text-xs rounded-md border transition-colors ${
            showFailed
              ? "bg-gray-700 text-white border-gray-600"
              : "bg-gray-900 text-gray-300 border-gray-700 hover:bg-gray-800"
          }`}
        >
          Show failed jobs
        </button>
        <p className="text-xs text-gray-500">
          Showing {visibleJobs.length} of {jobs.length} jobs
        </p>
      </div>
      {githubError && (
        <p className="text-xs text-red-400">{githubError}</p>
      )}

      {loading ? (
        <div className="text-gray-500 text-sm">Loading...</div>
      ) : visibleJobs.length === 0 ? (
        <div className="text-center py-20 text-gray-600">
          <p className="text-4xl mb-3">🤖</p>
          <p className="font-medium text-gray-400">No jobs for current filters</p>
          <p className="text-sm mt-1">Toggle filters above or trigger a new review</p>
        </div>
      ) : (
        <div className="space-y-2">
          {visibleJobs.map((job) => (
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
