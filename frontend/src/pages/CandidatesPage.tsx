import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export function CandidatesPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["candidates"],
    queryFn: api.candidates.list
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Candidates</h1>
      </div>
      <div className="card-grid">
        {(query.data ?? []).map((candidate) => (
          <article className="panel candidate-directory-card" key={candidate.id}>
            <h4>{candidate.fullName}</h4>
            <p className="muted">
              {candidate.headline} · {candidate.experienceYears}y · {candidate.location}
            </p>
            <p>{candidate.skills.slice(0, 5).join(" · ")}</p>
            <Link className="text-link" to={`/candidates/${candidate.id}`}>
              View profile
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}

