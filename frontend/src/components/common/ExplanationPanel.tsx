import type { ExplanationFactor } from "../../types";

interface Props {
  title?: string;
  summary: string;
  factors: ExplanationFactor[];
}

export function ExplanationPanel({ title = "Explanation", summary, factors }: Props): JSX.Element {
  return (
    <section className="panel explanation-panel">
      <h4>{title}</h4>
      <p className="muted">{summary}</p>
      <div className="factor-list">
        {factors.map((factor) => (
          <div key={factor.factor} className="factor-row">
            <div className="factor-header">
              <span>{factor.factor}</span>
              <span>{Math.round(factor.impact * 100)}%</span>
            </div>
            <div className="factor-bar">
              <div style={{ width: `${Math.min(100, Math.round(factor.impact * 100))}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

