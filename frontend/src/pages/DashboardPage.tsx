import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatHours, formatPercent } from "../lib/format";
import { StatusIndicator } from "../components/common/StatusIndicator";
import { ScoreBadge } from "../components/common/ScoreBadge";
import { VacancyCard } from "../components/vacancies/VacancyCard";
import type { DashboardSummary } from "../types";

function MetricCard(props: { label: string; value: string; hint: string }): JSX.Element {
  return (
    <article className="panel metric-card">
      <p className="metric-label">{props.label}</p>
      <h2>{props.value}</h2>
      <p className="metric-hint">{props.hint}</p>
    </article>
  );
}

export function DashboardPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: api.dashboard.summary,
    refetchInterval: (data) => {
      const current = data.state.data as DashboardSummary | undefined;
      return current?.pipeline.some((item) => item.status === "PROCESSING") ? 2200 : false;
    }
  });

  if (query.isLoading) {
    return <section className="panel loading-state">Loading dashboard...</section>;
  }

  if (!query.data) {
    return <section className="panel loading-state">Unable to load dashboard.</section>;
  }

  const summary = query.data;

  return (
    <section className="page-stack">
      <div className="metrics-row">
        <MetricCard
          label="Total Vacancies"
          value={summary.totalVacancies.toString()}
          hint="Active pipeline inputs"
        />
        <MetricCard
          label="Resumes Processed"
          value={summary.resumesProcessed.toString()}
          hint="Parsed and scored in queue"
        />
        <MetricCard
          label="Avg Matching Score"
          value={formatPercent(summary.avgMatchingScore)}
          hint="Top-ranked candidate fit"
        />
        <MetricCard
          label="Time-to-Shortlist"
          value={formatHours(summary.avgShortlistHours)}
          hint="Average queue completion"
        />
      </div>

      <div className="dashboard-main-grid">
        <section className="panel pipeline-panel">
          <div className="panel-head">
            <h3>Pipeline Status</h3>
            <Link className="text-link" to="/vacancies/new">
              + Create Vacancy
            </Link>
          </div>
          <div className="pipeline-list">
            {summary.pipeline.map((item) => (
              <div key={item.vacancyId} className="pipeline-item">
                <div className="pipeline-item-head">
                  <p>{item.vacancyTitle}</p>
                  <StatusIndicator status={item.status} />
                </div>
                <div className="progress-track">
                  <div className="progress-fill fill-running" style={{ width: `${item.progress}%` }} />
                </div>
                <p className="muted">{item.progress}% complete</p>
              </div>
            ))}
          </div>
        </section>

        <section className="panel insights-panel">
          <h3>AI Insights</h3>
          <div className="insight-row">
            <span>Model accuracy</span>
            <strong>{formatPercent(summary.insights.modelAccuracy)}</strong>
          </div>
          <div className="insight-row">
            <span>Fairness alerts</span>
            <strong>{summary.insights.fairnessAlerts}</strong>
          </div>
          <div className="insight-row">
            <span>System load</span>
            <strong>{summary.insights.systemLoad}%</strong>
          </div>
          <p className="muted">
            Live monitoring focuses on ranking confidence, fairness checks, and queue pressure.
          </p>
        </section>
      </div>

      <div className="dashboard-bottom-grid">
        <section>
          <div className="panel-head">
            <h3>Recent Vacancies</h3>
            <Link className="text-link" to="/vacancies">
              View all
            </Link>
          </div>
          <div className="card-grid">
            {summary.recentVacancies.map((vacancy) => (
              <VacancyCard key={vacancy.id} vacancy={vacancy} />
            ))}
          </div>
        </section>

        <section className="panel recent-shortlists-panel">
          <div className="panel-head">
            <h3>Recent Shortlists</h3>
            <Link className="text-link" to="/shortlists">
              Open shortlist page
            </Link>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Vacancy</th>
                <th>Match</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {summary.recentShortlists.map((entry) => (
                <tr key={`${entry.vacancyId}-${entry.candidateId}`}>
                  <td>{entry.candidate.fullName}</td>
                  <td>{entry.vacancy.title}</td>
                  <td>
                    <ScoreBadge score={entry.matchScore} />
                  </td>
                  <td>
                    <Link className="text-link" to={`/candidates/${entry.candidateId}`}>
                      View profile
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </section>
  );
}

