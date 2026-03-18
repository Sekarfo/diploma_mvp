import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { StatusIndicator } from "../components/common/StatusIndicator";

export function VacanciesPage(): JSX.Element {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["vacancies"],
    queryFn: api.vacancies.list,
    refetchInterval: 2500
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Vacancies</h1>
        <button type="button" className="primary-button" onClick={() => navigate("/vacancies/new")}>
          + Create Vacancy
        </button>
      </div>

      <section className="panel">
        <table className="data-table clickable-rows">
          <thead>
            <tr>
              <th>Vacancy title</th>
              <th>Status</th>
              <th>Candidates found</th>
              <th>Created date</th>
            </tr>
          </thead>
          <tbody>
            {(query.data ?? []).map((vacancy) => (
              <tr key={vacancy.id} onClick={() => navigate(`/vacancies/${vacancy.id}`)}>
                <td>{vacancy.title}</td>
                <td>
                  <StatusIndicator status={vacancy.status} />
                </td>
                <td>{vacancy.candidatesFound}</td>
                <td>{formatDate(vacancy.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}

