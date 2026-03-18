import { NavLink } from "react-router-dom";
import clsx from "clsx";

const navItems = [
  { label: "Dashboard", to: "/", end: true },
  { label: "Vacancies", to: "/vacancies" },
  { label: "Candidates", to: "/candidates" },
  { label: "Shortlists", to: "/shortlists" },
  { label: "Analytics", to: "/analytics" },
  { label: "Feedback & Training", to: "/feedback-training" },
  { label: "Integrations", to: "/integrations" },
  { label: "Settings", to: "/settings" }
];

export function Sidebar(): JSX.Element {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">TR</div>
        <div>
          <p className="brand-title">TalentRank</p>
          <p className="brand-subtitle">Screening Console</p>
        </div>
      </div>
      <nav className="nav-list">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => clsx("nav-item", isActive && "nav-item-active")}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <p className="sidebar-kpi-label">Flow Scope</p>
        <p className="sidebar-kpi-value">Vacancy → Processing → Shortlist → Feedback</p>
      </div>
    </aside>
  );
}
