import { useState, useCallback } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";
import { api, type ReviewJob } from "../api/client";
import { usePolling } from "../hooks/usePolling";

export function QualityMetrics() {
  const [jobs, setJobs] = useState<ReviewJob[]>([]);

  const refresh = useCallback(async () => {
    const data = await api.getJobs(200);
    setJobs(data.filter((j) => j.status === "completed"));
  }, []);

  usePolling(refresh, 10000);

  // Score distribution bucketed into 0.5 increments
  const buckets: Record<string, number> = {};
  for (let i = 1; i <= 5; i += 0.5) {
    buckets[i.toFixed(1)] = 0;
  }
  jobs.forEach((j) => {
    if (j.avg_eval_score !== null) {
      const bucket = (Math.floor(j.avg_eval_score * 2) / 2).toFixed(1);
      if (buckets[bucket] !== undefined) buckets[bucket]++;
    }
  });
  const distData = Object.entries(buckets).map(([score, count]) => ({ score, count }));

  // Per-dimension average scores
  const dimTotals: Record<string, { sum: number; count: number }> = {};
  jobs.forEach((j) => {
    j.eval_scores.forEach((s) => {
      if (!dimTotals[s.dimension]) dimTotals[s.dimension] = { sum: 0, count: 0 };
      dimTotals[s.dimension].sum += s.score;
      dimTotals[s.dimension].count += 1;
    });
  });
  const dimData = Object.entries(dimTotals)
    .map(([dim, { sum, count }]) => ({
      dim: dim.replace(/_/g, " "),
      avg: parseFloat((sum / count).toFixed(2)),
    }))
    .sort((a, b) => a.avg - b.avg);

  // Iteration frequency
  const iterCounts: Record<number, number> = { 1: 0, 2: 0, 3: 0 };
  jobs.forEach((j) => {
    const i = Math.min(j.eval_iterations, 3);
    if (i > 0) iterCounts[i] = (iterCounts[i] ?? 0) + 1;
  });
  const iterData = Object.entries(iterCounts).map(([iter, count]) => ({
    iter: `${iter} iteration${Number(iter) > 1 ? "s" : ""}`,
    count,
  }));

  const passRate =
    jobs.length > 0
      ? ((jobs.filter((j) => (j.avg_eval_score ?? 0) >= 3.5).length / jobs.length) * 100).toFixed(1)
      : null;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white">Quality Metrics</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Self-eval score distribution, dimension averages, and iteration frequency
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Reviews Analysed", value: jobs.length.toString() },
          { label: "Pass Rate (≥3.5)", value: passRate ? `${passRate}%` : "—" },
          {
            label: "1-Shot Pass Rate",
            value:
              jobs.length > 0
                ? `${(
                    (jobs.filter((j) => j.eval_iterations === 1).length / jobs.length) *
                    100
                  ).toFixed(1)}%`
                : "—",
          },
        ].map((s) => (
          <div key={s.label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-xs text-gray-500">{s.label}</p>
            <p className="text-2xl font-mono font-bold text-white mt-1">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Score distribution */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Score Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={distData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="score" tick={{ fill: "#6b7280", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                labelStyle={{ color: "#e5e7eb" }}
              />
              <Bar dataKey="count" fill="#4c6ef5" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Iteration frequency */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Refinement Iterations</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={iterData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="iter" tick={{ fill: "#6b7280", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                labelStyle={{ color: "#e5e7eb" }}
              />
              <Bar dataKey="count" fill="#f59e0b" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Per-dimension averages */}
      {dimData.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">
            Average Score by Dimension (lowest first)
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={dimData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                type="number"
                domain={[0, 5]}
                tick={{ fill: "#6b7280", fontSize: 11 }}
              />
              <YAxis
                type="category"
                dataKey="dim"
                width={150}
                tick={{ fill: "#9ca3af", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                labelStyle={{ color: "#e5e7eb" }}
              />
              <Bar dataKey="avg" fill="#4ade80" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
