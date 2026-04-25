import clsx from "clsx";

type Status = "pending" | "running" | "completed" | "failed";

const styles: Record<Status, string> = {
  pending: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  running: "bg-blue-500/20 text-blue-300 border-blue-500/30 animate-pulse",
  completed: "bg-green-500/20 text-green-300 border-green-500/30",
  failed: "bg-red-500/20 text-red-300 border-red-500/30",
};

const icons: Record<Status, string> = {
  pending: "⏳",
  running: "⚡",
  completed: "✅",
  failed: "❌",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
        styles[status]
      )}
    >
      {icons[status]} {status}
    </span>
  );
}
