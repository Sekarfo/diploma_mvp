import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { ScoreBadge } from "../components/common/ScoreBadge";
import { ExplanationPanel } from "../components/common/ExplanationPanel";
import { CandidateCard } from "../components/candidates/CandidateCard";
import { useUiStore } from "../store/useUiStore";

export function ShortlistsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const vacancyIdFromUrl = searchParams.get("vacancy");
  const selectedVacancyId = useUiStore((state) => state.selectedVacancyId);
  const setSelectedVacancyId = useUiStore((state) => state.setSelectedVacancyId);
  const minScoreThreshold = useUiStore((state) => state.minScoreThreshold);
  const setMinScoreThreshold = useUiStore((state) => state.setMinScoreThreshold);

  const vacancyQuery = useQuery({
    queryKey: ["vacancies"],
    queryFn: api.vacancies.list,
    refetchInterval: 2200
  });

  const shortlistQuery = useQuery({
    queryKey: ["shortlists", selectedVacancyId, minScoreThreshold],
    queryFn: () => api.shortlists.list(selectedVacancyId, minScoreThreshold),
    enabled: Boolean(selectedVacancyId)
  });

  useEffect(() => {
    if (vacancyIdFromUrl) {
      setSelectedVacancyId(vacancyIdFromUrl);
      return;
    }

    if (!selectedVacancyId) {
      const readyVacancy = vacancyQuery.data?.find((vacancy) => vacancy.status === "READY");
      if (readyVacancy) {
        setSelectedVacancyId(readyVacancy.id);
        setSearchParams({ vacancy: readyVacancy.id }, { replace: true });
      }
    }
  }, [vacancyIdFromUrl, selectedVacancyId, setSearchParams, setSelectedVacancyId, vacancyQuery.data]);

  const decisionMutation = useMutation({
    mutationFn: (payload: { candidateId: string; decision: "approved" | "rejected" }) =>
      api.shortlists.setDecision(selectedVacancyId ?? "", payload.candidateId, payload.decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shortlists"] });
      queryClient.invalidateQueries({ queryKey: ["feedback"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    }
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Shortlists</h1>
        <div className="controls-inline">
          <label>
            Vacancy
            <select
              value={selectedVacancyId ?? ""}
              onChange={(event) => {
                const value = event.target.value || null;
                setSelectedVacancyId(value);
                if (value) {
                  setSearchParams({ vacancy: value }, { replace: true });
                }
              }}
            >
              {(vacancyQuery.data ?? []).map((vacancy) => (
                <option key={vacancy.id} value={vacancy.id}>
                  {vacancy.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Min score
            <input
              type="range"
              min={40}
              max={95}
              value={minScoreThreshold}
              onChange={(event) => setMinScoreThreshold(Number(event.target.value))}
            />
            <span>{minScoreThreshold}%</span>
          </label>
        </div>
      </div>

      <section className="panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>Match Score</th>
              <th>Skills Match</th>
              <th>Experience</th>
              <th>Explanation</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {(shortlistQuery.data ?? []).map((entry) => (
              <tr key={`${entry.vacancyId}-${entry.candidateId}`}>
                <td>{entry.candidate.fullName}</td>
                <td>
                  <ScoreBadge score={entry.matchScore} />
                </td>
                <td>{entry.skillsMatch.toFixed(1)}%</td>
                <td>{entry.candidate.experienceYears}y</td>
                <td>{entry.explanation}</td>
                <td>
                  <div className="table-actions">
                    <button
                      type="button"
                      className="table-action"
                      onClick={() =>
                        decisionMutation.mutate({
                          candidateId: entry.candidateId,
                          decision: "approved"
                        })
                      }
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="table-action danger"
                      onClick={() =>
                        decisionMutation.mutate({
                          candidateId: entry.candidateId,
                          decision: "rejected"
                        })
                      }
                    >
                      Reject
                    </button>
                    <Link className="text-link" to={`/candidates/${entry.candidateId}`}>
                      View profile
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="candidate-cards-grid">
        {(shortlistQuery.data ?? []).slice(0, 4).map((entry) => (
          <div key={`${entry.vacancyId}-${entry.candidateId}`} className="stack-sm">
            <CandidateCard entry={entry} />
            <ExplanationPanel
              title="SHAP-based factors"
              summary={entry.explanation}
              factors={entry.explanationFactors}
            />
          </div>
        ))}
      </section>
    </section>
  );
}
