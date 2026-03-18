import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatHours, formatPercent } from "../lib/format";

function AnalyticsMetric(props: { label: string; value: string }): JSX.Element {
  return (
    <article className="panel metric-card">
      <p className="metric-label">{props.label}</p>
      <h2>{props.value}</h2>
    </article>
  );
}

export function AnalyticsPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["analytics"],
    queryFn: api.analytics.summary
  });

  if (!query.data) {
    return <section className="panel loading-state">Loading analytics...</section>;
  }

  const analytics = query.data;

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Analytics</h1>
      </div>

      <div className="metrics-row">
        <AnalyticsMetric label="Precision@10" value={formatPercent(analytics.precisionAt10)} />
        <AnalyticsMetric label="Recall" value={formatPercent(analytics.recall)} />
        <AnalyticsMetric label="Avg shortlist time" value={formatHours(analytics.avgShortlistHours)} />
        <AnalyticsMetric label="Fairness metrics" value={formatPercent(analytics.fairnessScore)} />
      </div>

      <div className="split-grid">
        <section className="panel">
          <h3>Model performance over time</h3>
          <div className="chart-rows">
            {analytics.performanceSeries.map((point) => (
              <div key={point.label} className="chart-row">
                <span>{point.label}</span>
                <div className="chart-track">
                  <div className="chart-bar-primary" style={{ width: `${point.precision}%` }} />
                  <div className="chart-bar-secondary" style={{ width: `${point.recall}%` }} />
                </div>
                <span>
                  P {point.precision}% · R {point.recall}%
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h3>Hiring distribution</h3>
          <div className="bar-chart">
            {analytics.hiringDistribution.map((bucket) => (
              <div key={bucket.bucket} className="bar-item">
                <span>{bucket.bucket}</span>
                <div className="bar-track">
                  <div style={{ width: `${Math.max(6, bucket.value * 30)}%` }} />
                </div>
                <span>{bucket.value}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

