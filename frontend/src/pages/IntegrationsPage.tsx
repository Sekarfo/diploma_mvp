import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { StatusIndicator } from "../components/common/StatusIndicator";
import { formatDate } from "../lib/format";

export function IntegrationsPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["integrations"],
    queryFn: api.integrations.list
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Integrations</h1>
      </div>

      <div className="card-grid">
        {(query.data ?? []).map((integration) => (
          <article key={integration.key} className="panel integration-card">
            <div className="panel-head">
              <h3>{integration.title}</h3>
              <StatusIndicator status={integration.status} />
            </div>
            <p className="muted">{integration.description}</p>
            <p className="muted">Last sync: {formatDate(integration.lastSync)}</p>
            <button type="button" className="secondary-button">
              Check connection
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

