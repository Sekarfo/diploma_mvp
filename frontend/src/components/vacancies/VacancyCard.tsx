import { Link } from "react-router-dom";
import type { Vacancy } from "../../types";
import { StatusIndicator } from "../common/StatusIndicator";
import { formatDateShort } from "../../lib/format";

interface Props {
  vacancy: Vacancy;
}

export function VacancyCard({ vacancy }: Props): JSX.Element {
  return (
    <article className="panel vacancy-card">
      <div className="vacancy-card-head">
        <h4>{vacancy.title}</h4>
        <StatusIndicator status={vacancy.status} />
      </div>
      <p className="muted">{vacancy.extractedSkills.slice(0, 4).join(" · ")}</p>
      <div className="vacancy-card-foot">
        <span>{vacancy.candidatesFound} candidates</span>
        <span>Created {formatDateShort(vacancy.createdAt)}</span>
      </div>
      <Link className="text-link" to={`/vacancies/${vacancy.id}`}>
        Open vacancy
      </Link>
    </article>
  );
}

