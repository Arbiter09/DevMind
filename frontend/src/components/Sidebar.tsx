import { NavLink } from "react-router-dom";
import clsx from "clsx";

const links = [
  { to: "/", label: "Live Feed", icon: "⚡" },
  { to: "/inspect", label: "Review Inspector", icon: "🔍" },
  { to: "/cost", label: "Cost Analytics", icon: "💰" },
  { to: "/quality", label: "Quality Metrics", icon: "📊" },
];

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 flex flex-col py-6 px-3 gap-1">
      <div className="px-3 mb-6">
        <h1 className="text-lg font-bold text-white tracking-tight">DevMind</h1>
        <p className="text-xs text-gray-500 mt-0.5">PR Review Agent</p>
      </div>
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.to === "/"}
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
              isActive
                ? "bg-brand-500/20 text-brand-300 font-medium"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
            )
          }
        >
          <span>{link.icon}</span>
          {link.label}
        </NavLink>
      ))}
    </aside>
  );
}
