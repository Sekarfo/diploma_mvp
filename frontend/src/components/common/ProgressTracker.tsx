import clsx from "clsx";
import type { PipelineStep } from "../../types";

interface Props {
  steps: PipelineStep[];
}

export function ProgressTracker({ steps }: Props): JSX.Element {
  return (
    <section className="panel progress-panel">
      <h3>Pipeline Progress</h3>
      <div className="progress-list">
        {steps.map((step) => (
          <div key={step.key} className="progress-item">
            <div className="progress-label-row">
              <span>{step.label}</span>
              <span className={clsx("step-state", `step-${step.status}`)}>{step.progress.toFixed(0)}%</span>
            </div>
            <div className="progress-track">
              <div className={clsx("progress-fill", `fill-${step.status}`)} style={{ width: `${step.progress}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

