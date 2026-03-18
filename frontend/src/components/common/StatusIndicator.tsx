import clsx from "clsx";
import type { VacancyStatus } from "../../types";

interface Props {
  status: VacancyStatus | "healthy" | "degraded";
}

const statusLabel: Record<Props["status"], string> = {
  NEW: "NEW",
  PROCESSING: "PROCESSING",
  READY: "READY",
  healthy: "Healthy",
  degraded: "Degraded"
};

export function StatusIndicator({ status }: Props): JSX.Element {
  return (
    <span className={clsx("status-indicator", `status-${status.toLowerCase()}`)}>
      {statusLabel[status]}
    </span>
  );
}

