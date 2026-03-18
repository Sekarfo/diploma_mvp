import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppLayout(): JSX.Element {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace-shell">
        <TopBar />
        <main className="workspace-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

