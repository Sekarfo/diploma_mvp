import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ProgressTracker } from "../components/common/ProgressTracker";
import { useUiStore } from "../store/useUiStore";

export function ProcessingPage(): JSX.Element {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const setActiveProcessingJobId = useUiStore((state) => state.setActiveProcessingJobId);
  const setSelectedVacancyId = useUiStore((state) => state.setSelectedVacancyId);

  const query = useQuery({
    queryKey: ["processing", jobId],
    queryFn: () => api.processing.get(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (value) => {
      const job = value.state.data;
      return job && !job.completed ? 1200 : false;
    }
  });

  const job = query.data;

  if (!job) {
    return <section className="panel loading-state">Processing job not found.</section>;
  }

  const progress = Math.round(job.steps.reduce((acc, step) => acc + step.progress, 0) / job.steps.length);

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Processing</h1>
        <span className="muted">Queue depth: {job.queueDepth}</span>
      </div>

      <ProgressTracker steps={job.steps} />

      <section className="panel processing-summary">
        <h3>{job.completed ? "Shortlist Ready" : "Background pipeline in progress"}</h3>
        <p className="muted">
          {job.completed
            ? "Parsing, search, scoring, and ranking are complete. Candidate shortlist is ready for review."
            : `Current completion: ${progress}%. This screen polls the job state to reflect async queue updates.`}
        </p>
        {job.completed ? (
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              setActiveProcessingJobId(null);
              setSelectedVacancyId(job.vacancyId);
              navigate(`/shortlists?vacancy=${job.vacancyId}`);
            }}
          >
            Open Shortlist
          </button>
        ) : null}
      </section>
    </section>
  );
}

