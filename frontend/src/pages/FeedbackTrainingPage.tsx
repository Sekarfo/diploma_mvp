import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { formatDate } from "../lib/format";

type EditState = Record<string, { decision: "Approve" | "Reject"; reason: string }>;

export function FeedbackTrainingPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<EditState>({});

  const query = useQuery({
    queryKey: ["feedback"],
    queryFn: api.feedback.list
  });

  const editableRows = useMemo(() => query.data ?? [], [query.data]);

  const saveMutation = useMutation({
    mutationFn: (payload: { recordId: string; decision: "Approve" | "Reject"; reason: string }) =>
      api.feedback.update(payload.recordId, {
        decision: payload.decision,
        reason: payload.reason
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feedback"] });
      queryClient.invalidateQueries({ queryKey: ["shortlists"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    }
  });

  const retrainMutation = useMutation({
    mutationFn: (recordId: string) => api.feedback.sendToRetraining(recordId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feedback"] });
    }
  });

  return (
    <section className="page-stack">
      <div className="panel-head">
        <h1>Feedback & Training</h1>
      </div>
      <section className="panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>Decision</th>
              <th>Reason</th>
              <th>Vacancy</th>
              <th>Model Version</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {editableRows.map((record) => {
              const draft = drafts[record.id] ?? {
                decision: record.decision,
                reason: record.reason
              };

              return (
                <tr key={record.id}>
                  <td>
                    <div>{record.candidate.fullName}</div>
                    <small className="muted">{formatDate(record.updatedAt)}</small>
                  </td>
                  <td>
                    <select
                      value={draft.decision}
                      onChange={(event) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [record.id]: {
                            ...draft,
                            decision: event.target.value as "Approve" | "Reject"
                          }
                        }))
                      }
                    >
                      <option value="Approve">Approve</option>
                      <option value="Reject">Reject</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="text"
                      value={draft.reason}
                      onChange={(event) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [record.id]: {
                            ...draft,
                            reason: event.target.value
                          }
                        }))
                      }
                    />
                  </td>
                  <td>{record.vacancy.title}</td>
                  <td>{record.modelVersion}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        type="button"
                        className="table-action"
                        onClick={() =>
                          saveMutation.mutate({
                            recordId: record.id,
                            decision: draft.decision,
                            reason: draft.reason
                          })
                        }
                      >
                        Edit labels
                      </button>
                      <button
                        type="button"
                        className="table-action"
                        disabled={record.sentToRetraining}
                        onClick={() => retrainMutation.mutate(record.id)}
                      >
                        {record.sentToRetraining ? "Queued" : "Send to retraining pipeline"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </section>
  );
}

