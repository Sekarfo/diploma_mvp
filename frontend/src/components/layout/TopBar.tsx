import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export function TopBar(): JSX.Element {
  const { data } = useQuery({
    queryKey: ["dashboard", "summary", "topbar"],
    queryFn: api.dashboard.summary,
    refetchInterval: 3000
  });

  const processingCount =
    data?.pipeline.filter((item) => item.status === "PROCESSING").length ?? 0;
  const queueState = processingCount > 0 ? "Processing jobs running" : "Queue healthy";

  return (
    <header className="topbar">
      <div className="topbar-status">
        <span className={`status-dot ${processingCount > 0 ? "status-dot-busy" : "status-dot-ok"}`} />
        <span>{queueState}</span>
      </div>
      <div className="topbar-user">
        <button type="button" className="ghost-button">
          Alerts
          <span className="topbar-count">{processingCount}</span>
        </button>
        <div className="user-pill">A</div>
      </div>
    </header>
  );
}

