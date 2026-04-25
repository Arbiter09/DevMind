import clsx from "clsx";
import type { EvalScore } from "../api/client";

function scoreColor(score: number): string {
  if (score >= 4.5) return "bg-green-500";
  if (score >= 3.5) return "bg-blue-500";
  if (score >= 2.5) return "bg-yellow-500";
  return "bg-red-500";
}

export function DimensionScoreBar({ scores }: { scores: EvalScore[] }) {
  return (
    <div className="space-y-2">
      {scores.map((s) => (
        <div key={s.dimension} className="group">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-400 capitalize">
              {s.dimension.replace(/_/g, " ")}
            </span>
            <span
              className={clsx(
                "text-xs font-mono font-semibold",
                s.score >= 4 ? "text-green-400" : s.score >= 3 ? "text-yellow-400" : "text-red-400"
              )}
            >
              {s.score.toFixed(1)}
            </span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={clsx("h-full rounded-full transition-all", scoreColor(s.score))}
              style={{ width: `${(s.score / 5) * 100}%` }}
            />
          </div>
          {s.notes && (
            <p className="text-xs text-gray-500 mt-0.5 hidden group-hover:block">{s.notes}</p>
          )}
        </div>
      ))}
    </div>
  );
}
