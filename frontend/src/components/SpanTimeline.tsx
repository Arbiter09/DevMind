import { formatDistanceStrict } from "date-fns";
import type { PhaseTrace } from "../api/client";
import clsx from "clsx";

const PHASE_COLORS: Record<string, string> = {
  context_gathering: "bg-purple-500",
  analysis: "bg-blue-500",
  self_eval: "bg-orange-500",
  posting: "bg-green-500",
};

function durationMs(phase: PhaseTrace): number {
  if (!phase.ended_at) return 0;
  return new Date(phase.ended_at).getTime() - new Date(phase.started_at).getTime();
}

export function SpanTimeline({ phases }: { phases: PhaseTrace[] }) {
  if (!phases.length) return null;

  const totalMs = phases.reduce((acc, p) => acc + durationMs(p), 0);

  return (
    <div className="space-y-3">
      {/* Bar chart */}
      <div className="flex h-4 rounded-full overflow-hidden gap-0.5">
        {phases.map((p) => {
          const pct = totalMs > 0 ? (durationMs(p) / totalMs) * 100 : 25;
          return (
            <div
              key={p.phase}
              className={clsx("h-full", PHASE_COLORS[p.phase] ?? "bg-gray-500")}
              style={{ width: `${pct}%` }}
              title={`${p.phase}: ${durationMs(p)}ms`}
            />
          );
        })}
      </div>

      {/* Phase rows */}
      {phases.map((p) => (
        <div key={p.phase} className="flex items-start justify-between text-sm">
          <div className="flex items-center gap-2">
            <span
              className={clsx("w-2 h-2 rounded-full mt-1 shrink-0", PHASE_COLORS[p.phase] ?? "bg-gray-500")}
            />
            <div>
              <p className="font-medium capitalize text-gray-200">
                {p.phase.replace(/_/g, " ")}
              </p>
              <p className="text-xs text-gray-500">{durationMs(p)}ms</p>
            </div>
          </div>
          <div className="text-right text-xs text-gray-500 space-y-0.5">
            {(p.tokens_input > 0 || p.tokens_output > 0) && (
              <p>
                {p.tokens_input.toLocaleString()} in / {p.tokens_output.toLocaleString()} out tokens
              </p>
            )}
            {(p.cache_hits > 0 || p.cache_misses > 0) && (
              <p>
                {p.cache_hits} cache hits / {p.cache_misses} misses
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
