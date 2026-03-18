import clsx from "clsx";

interface Props {
  score: number;
}

export function ScoreBadge({ score }: Props): JSX.Element {
  const tone = score >= 85 ? "high" : score >= 70 ? "mid" : "low";
  return <span className={clsx("score-badge", `score-${tone}`)}>{score.toFixed(1)}%</span>;
}

