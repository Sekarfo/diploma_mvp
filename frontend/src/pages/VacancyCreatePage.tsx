import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useUiStore } from "../store/useUiStore";

const skillHints = ["python", "sql", "fastapi", "xgboost", "react", "typescript", "docker", "machine learning"];

function inferSkills(input: string): string[] {
  const lower = input.toLowerCase();
  return skillHints.filter((skill) => lower.includes(skill));
}

export function VacancyCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setSelectedVacancyId = useUiStore((state) => state.setSelectedVacancyId);
  const setActiveProcessingJobId = useUiStore((state) => state.setActiveProcessingJobId);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const extractedPreview = useMemo(() => inferSkills(`${title} ${description}`), [title, description]);

  const mutation = useMutation({
    mutationFn: api.vacancies.create,
    onSuccess: (response) => {
      setSelectedVacancyId(response.vacancy.id);
      setActiveProcessingJobId(response.processingJob.id);
      queryClient.invalidateQueries({ queryKey: ["vacancies"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/processing/${response.processingJob.id}`);
    }
  });

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!title.trim() || !description.trim()) {
      return;
    }
    mutation.mutate({ title, description });
  }

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Create Vacancy</h1>
      </div>
      <form className="panel form-grid" onSubmit={onSubmit}>
        <label className="field">
          <span>Job title</span>
          <input
            type="text"
            placeholder="Senior ML Engineer"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Job description</span>
          <textarea
            rows={8}
            placeholder="Describe role, required skills, and expected experience."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <div className="inline-list">
          <span className="muted">Extracted skills preview:</span>
          {extractedPreview.length > 0 ? (
            extractedPreview.map((skill) => (
              <span key={skill} className="tag">
                {skill}
              </span>
            ))
          ) : (
            <span className="muted">No explicit skills detected yet.</span>
          )}
        </div>
        <button type="submit" className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "Submitting..." : "Submit Vacancy"}
        </button>
      </form>
    </section>
  );
}

