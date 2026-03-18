import { Link } from "react-router-dom";
import type { ShortlistCandidate } from "../../types";
import { ScoreBadge } from "../common/ScoreBadge";

interface Props {
  entry: ShortlistCandidate;
}

export function CandidateCard({ entry }: Props): JSX.Element {
  const topSkills = entry.topMatchingSkills.length > 0 ? entry.topMatchingSkills : entry.candidate.skills.slice(0, 4);
  return (
    <article className="panel candidate-card">
      <div className="candidate-card-top">
        <div>
          <h4>{entry.candidate.fullName}</h4>
          <p className="muted">
            {entry.candidate.headline} · {entry.candidate.experienceYears}y exp
          </p>
        </div>
        <ScoreBadge score={entry.matchScore} />
      </div>
      <p className="candidate-skills">{topSkills.join(" · ")}</p>
      <p className="muted">{entry.explanation}</p>
      <div className="candidate-card-actions">
        <Link className="text-link" to={`/candidates/${entry.candidateId}`}>
          View profile
        </Link>
      </div>
    </article>
  );
}
