import { useState, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { api, type Metrics, type ReviewJob } from "../api/client";
import { usePolling } from "../hooks/usePolling";
import { format } from "date-fns";

export function CostAnalytics() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [jobs, setJobs] = useState<ReviewJob[]>([]);

  const refresh = useCallback(async () => {
    const [m, j] = await Promise.all([api.getMetrics(), api.getJobs(100)]);
    setMetrics(m);
    setJobs(j.filter((j) => j.status === "completed"));
  }, []);

  usePolling(refresh, 10000);

  const tokensByDay = jobs.reduce<Record<string, number>>((acc, job) => {
    const day = format(new Date(job.created_at), "MMM d");
    acc[day] = (acc[day] ?? 0) + job.total_tokens_input + job.total_tokens_output;
    return acc;
  }, {});

  const chartData = Object.entries(tokensByDay).map(([date, tokens]) => ({ date, tokens }));

  const cacheData = metrics
    ? [
        { name: "Cache Hits", value: metrics.cache.hits, color: "#4ade80" },
        { name: "Cache Misses", value: metrics.cache.misses, color: "#f87171" },
      ]
    : [];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white">Cost Analytics</h2>
        <p className="text-sm text-gray-500 mt-0.5">Token usage, cache efficiency, and cost savings</p>
      </div>

      {metrics && (
        <>
          {/* Stats row */}
          <div className="grid grid-cols-4 gap-4">
            {[
              {
                label: "Total Tokens",
                value: metrics.tokens.total.toLocaleString(),
                sub: `${metrics.tokens.total_input.toLocaleString()} in / ${metrics.tokens.total_output.toLocaleString()} out`,
              },
              {
                label: "Cache Hit Rate",
                value: `${(metrics.cache.hit_rate * 100).toFixed(1)}%`,
                sub: `${metrics.cache.hits} hits / ${metrics.cache.misses} misses`,
              },
              {
                label: "Completed Jobs",
                value: metrics.completed.toString(),
                sub: `${metrics.failed} failed`,
              },
              {
                label: "Avg Eval Score",
                value: metrics.quality.avg_eval_score?.toFixed(2) ?? "—",
                sub: `${metrics.quality.avg_iterations?.toFixed(1) ?? "—"} avg iterations`,
              },
            ].map((stat) => (
              <div key={stat.label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <p className="text-xs text-gray-500">{stat.label}</p>
                <p className="text-2xl font-mono font-bold text-white mt-1">{stat.value}</p>
                <p className="text-xs text-gray-600 mt-1">{stat.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-4">
            {/* Token usage over time */}
            <div className="col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Token Usage Over Time</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="tokenGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#4c6ef5" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#4c6ef5" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: "#111827", border: "1px solid #374151" }}
                      labelStyle={{ color: "#e5e7eb" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="tokens"
                      stroke="#4c6ef5"
                      fill="url(#tokenGrad)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
                  No data yet
                </div>
              )}
            </div>

            {/* Cache pie */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Cache Distribution</h3>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={cacheData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    dataKey="value"
                  >
                    {cacheData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Legend
                    iconType="circle"
                    wrapperStyle={{ fontSize: 11, color: "#9ca3af" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
