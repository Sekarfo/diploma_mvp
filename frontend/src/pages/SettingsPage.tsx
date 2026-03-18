import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useUiStore } from "../store/useUiStore";

export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const setMinScoreThreshold = useUiStore((state) => state.setMinScoreThreshold);
  const setModelVersion = useUiStore((state) => state.setModelVersion);

  const query = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings.get
  });

  const [modelVersion, updateModelVersion] = useState("ranker-v1.4");
  const [minScoreThreshold, updateMinScoreThreshold] = useState(65);
  const [piiMaskingEnabled, setPiiMaskingEnabled] = useState(true);
  const [auditLoggingEnabled, setAuditLoggingEnabled] = useState(true);

  useEffect(() => {
    if (!query.data) {
      return;
    }
    updateModelVersion(query.data.modelVersion);
    updateMinScoreThreshold(query.data.minScoreThreshold);
    setPiiMaskingEnabled(query.data.piiMaskingEnabled);
    setAuditLoggingEnabled(query.data.auditLoggingEnabled);
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: () =>
      api.settings.update({
        modelVersion,
        minScoreThreshold,
        piiMaskingEnabled,
        auditLoggingEnabled
      }),
    onSuccess: (settings) => {
      setMinScoreThreshold(settings.minScoreThreshold);
      setModelVersion(settings.modelVersion);
      queryClient.invalidateQueries({ queryKey: ["shortlists"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    }
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Settings</h1>
      </div>

      <section className="panel">
        <h3>User roles</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Scope</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Recruiter</td>
              <td>Review shortlist, approve/reject, submit feedback.</td>
            </tr>
            <tr>
              <td>ML Engineer</td>
              <td>Inspect explanations, monitor metrics, trigger retraining pipeline.</td>
            </tr>
            <tr>
              <td>Admin</td>
              <td>Manage integrations, threshold settings, and model versions.</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="split-grid">
        <section className="panel">
          <h3>Data privacy settings</h3>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={piiMaskingEnabled}
              onChange={(event) => setPiiMaskingEnabled(event.target.checked)}
            />
            <span>Enable PII masking on resume previews</span>
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={auditLoggingEnabled}
              onChange={(event) => setAuditLoggingEnabled(event.target.checked)}
            />
            <span>Enable audit logging for reviewer actions</span>
          </label>
        </section>

        <section className="panel">
          <h3>Model + thresholds</h3>
          <label className="field">
            <span>Model version selection</span>
            <select value={modelVersion} onChange={(event) => updateModelVersion(event.target.value)}>
              <option value="ranker-v1.4">ranker-v1.4</option>
              <option value="ranker-v1.3">ranker-v1.3</option>
              <option value="baseline-v1.0">baseline-v1.0</option>
            </select>
          </label>

          <label className="field">
            <span>Threshold (min score): {minScoreThreshold}%</span>
            <input
              type="range"
              min={40}
              max={95}
              value={minScoreThreshold}
              onChange={(event) => updateMinScoreThreshold(Number(event.target.value))}
            />
          </label>
        </section>
      </section>

      <section className="panel">
        <button type="button" className="primary-button" onClick={() => mutation.mutate()}>
          {mutation.isPending ? "Saving..." : "Save settings"}
        </button>
      </section>
    </section>
  );
}

