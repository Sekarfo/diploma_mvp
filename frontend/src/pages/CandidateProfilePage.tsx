import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { ExplanationPanel } from "../components/common/ExplanationPanel";
import { ScoreBadge } from "../components/common/ScoreBadge";
import { api } from "../api/client";

export function CandidateProfilePage(): JSX.Element {
  const { candidateId = "" } = useParams();
  const query = useQuery({
    queryKey: ["candidate", candidateId],
    queryFn: () => api.candidates.getProfile(candidateId),
    enabled: Boolean(candidateId)
  });

  if (!query.data?.candidate) {
    return <section className="panel loading-state">Candidate not found.</section>;
  }

  const { candidate, evaluations } = query.data;
  const topEvaluation = evaluations[0];

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>{candidate.fullName}</h1>
        {topEvaluation ? <ScoreBadge score={topEvaluation.matchScore} /> : null}
      </div>

      <div className="split-grid">
        <section className="panel">
          <h3>Resume preview</h3>
          <p className="muted">{candidate.resumePreview}</p>
          <h4>Extracted structured data</h4>
          <ul className="plain-list">
            <li>Headline: {candidate.headline}</li>
            <li>Experience: {candidate.experienceYears} years</li>
            <li>Location: {candidate.location}</li>
            <li>Skills: {candidate.skills.join(", ")}</li>
          </ul>
        </section>

        <section className="panel">
          <h3>Score breakdown</h3>
          {evaluations.length === 0 ? (
            <p className="muted">No shortlist scores yet for this candidate.</p>
          ) : (
            <div className="score-breakdown">
              {evaluations.map((evaluation) => (
                <div key={`${evaluation.vacancyId}-${evaluation.candidateId}`} className="score-row">
                  <div>
                    <p>{evaluation.vacancy.title}</p>
                    <p className="muted">
                      Skills {evaluation.skillsMatch.toFixed(0)}% · Experience {evaluation.experienceScore.toFixed(0)}%
                    </p>
                  </div>
                  <ScoreBadge score={evaluation.matchScore} />
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {topEvaluation ? (
        <ExplanationPanel
          title="Explanation Panel"
          summary={topEvaluation.explanation}
          factors={topEvaluation.explanationFactors}
        />
      ) : null}
    </section>
  );
}

