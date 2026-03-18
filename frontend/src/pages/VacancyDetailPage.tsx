import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { StatusIndicator } from "../components/common/StatusIndicator";
import { useUiStore } from "../store/useUiStore";

export function VacancyDetailPage(): JSX.Element {
  const { vacancyId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setSelectedVacancyId = useUiStore((state) => state.setSelectedVacancyId);
  const setActiveProcessingJobId = useUiStore((state) => state.setActiveProcessingJobId);

  const query = useQuery({
    queryKey: ["vacancy", vacancyId],
    queryFn: () => api.vacancies.get(vacancyId),
    enabled: Boolean(vacancyId),
    refetchInterval: 2200
  });

  const [skills, setSkills] = useState<string[]>([]);
  const [newSkill, setNewSkill] = useState("");
  const [skillsWeight, setSkillsWeight] = useState(65);
  const [experienceWeight, setExperienceWeight] = useState(35);

  useEffect(() => {
    if (!query.data) {
      return;
    }
    setSkills(query.data.extractedSkills);
    setSkillsWeight(Math.round(query.data.weights.skills * 100));
    setExperienceWeight(Math.round(query.data.weights.experience * 100));
    setSelectedVacancyId(query.data.id);
  }, [query.data, setSelectedVacancyId]);

  const updateMutation = useMutation({
    mutationFn: () =>
      api.vacancies.update(vacancyId, {
        extractedSkills: skills,
        weights: {
          skills: skillsWeight / 100,
          experience: experienceWeight / 100
        }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vacancy", vacancyId] });
      queryClient.invalidateQueries({ queryKey: ["vacancies"] });
      queryClient.invalidateQueries({ queryKey: ["shortlists"] });
    }
  });

  const generateMutation = useMutation({
    mutationFn: () => api.vacancies.generateShortlist(vacancyId),
    onSuccess: (payload) => {
      queryClient.invalidateQueries({ queryKey: ["vacancies"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      if (payload.ready) {
        navigate(`/shortlists?vacancy=${vacancyId}`);
        return;
      }
      if (payload.processingJobId) {
        setActiveProcessingJobId(payload.processingJobId);
        navigate(`/processing/${payload.processingJobId}`);
      }
    }
  });

  if (!query.data) {
    return <section className="panel loading-state">Vacancy not found.</section>;
  }

  function addSkill(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const value = newSkill.trim().toLowerCase();
    if (!value || skills.includes(value)) {
      return;
    }
    setSkills((prev) => [...prev, value]);
    setNewSkill("");
  }

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>{query.data.title}</h1>
        <StatusIndicator status={query.data.status} />
      </div>

      <div className="split-grid">
        <section className="panel">
          <h3>Job description</h3>
          <p className="muted">{query.data.description}</p>
          <h4>Extracted skills (editable)</h4>
          <div className="inline-list">
            {skills.map((skill) => (
              <button
                type="button"
                key={skill}
                className="tag removable-tag"
                onClick={() => setSkills((prev) => prev.filter((item) => item !== skill))}
              >
                {skill} ×
              </button>
            ))}
          </div>
          <form className="inline-form" onSubmit={addSkill}>
            <input
              type="text"
              value={newSkill}
              onChange={(event) => setNewSkill(event.target.value)}
              placeholder="Add skill"
            />
            <button type="submit" className="secondary-button">
              Add
            </button>
          </form>
        </section>

        <section className="panel">
          <h3>Weights</h3>
          <label className="field">
            <span>Skills weight: {skillsWeight}%</span>
            <input
              type="range"
              min={20}
              max={80}
              value={skillsWeight}
              onChange={(event) => setSkillsWeight(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Experience weight: {experienceWeight}%</span>
            <input
              type="range"
              min={20}
              max={80}
              value={experienceWeight}
              onChange={(event) => setExperienceWeight(Number(event.target.value))}
            />
          </label>
          <button type="button" className="secondary-button" onClick={() => updateMutation.mutate()}>
            {updateMutation.isPending ? "Saving..." : "Save Vacancy Configuration"}
          </button>
        </section>
      </div>

      <div className="panel">
        <button type="button" className="primary-button" onClick={() => generateMutation.mutate()}>
          {generateMutation.isPending ? "Running..." : "Generate Shortlist"}
        </button>
      </div>
    </section>
  );
}

