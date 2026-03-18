export type VacancyStatus = "NEW" | "PROCESSING" | "READY";
export type DecisionStatus = "pending" | "approved" | "rejected";

export type PipelineStepKey = "parsing" | "searching" | "scoring" | "ranking";
export type PipelineStepStatus = "pending" | "running" | "done";

export interface PipelineStep {
  key: PipelineStepKey;
  label: string;
  status: PipelineStepStatus;
  progress: number;
}

export interface Vacancy {
  id: string;
  title: string;
  description: string;
  extractedSkills: string[];
  weights: {
    skills: number;
    experience: number;
  };
  status: VacancyStatus;
  candidatesFound: number;
  createdAt: string;
  shortlistReadyAt?: string;
  processingJobId?: string;
}

export interface Candidate {
  id: string;
  fullName: string;
  headline: string;
  location: string;
  experienceYears: number;
  skills: string[];
  resumePreview: string;
}

export interface ExplanationFactor {
  factor: string;
  impact: number;
}

export interface ShortlistEntry {
  vacancyId: string;
  candidateId: string;
  matchScore: number;
  skillsMatch: number;
  experienceScore: number;
  topMatchingSkills: string[];
  explanation: string;
  explanationFactors: ExplanationFactor[];
  decision: DecisionStatus;
}

export interface ShortlistCandidate extends ShortlistEntry {
  candidate: Candidate;
  vacancy: Vacancy;
}

export interface ProcessingJob {
  id: string;
  vacancyId: string;
  queueDepth: number;
  startedAt: number;
  completed: boolean;
  steps: PipelineStep[];
}

export interface DashboardSummary {
  totalVacancies: number;
  resumesProcessed: number;
  avgMatchingScore: number;
  avgShortlistHours: number;
  pipeline: Array<{
    vacancyId: string;
    vacancyTitle: string;
    status: VacancyStatus;
    progress: number;
  }>;
  insights: {
    modelAccuracy: number;
    fairnessAlerts: number;
    systemLoad: number;
  };
  recentVacancies: Vacancy[];
  recentShortlists: ShortlistCandidate[];
}

export interface AnalyticsSummary {
  precisionAt10: number;
  recall: number;
  avgShortlistHours: number;
  fairnessScore: number;
  performanceSeries: Array<{
    label: string;
    precision: number;
    recall: number;
  }>;
  hiringDistribution: Array<{
    bucket: string;
    value: number;
  }>;
}

export interface FeedbackRecord {
  id: string;
  candidateId: string;
  vacancyId: string;
  decision: "Approve" | "Reject";
  reason: string;
  modelVersion: string;
  updatedAt: string;
  sentToRetraining: boolean;
}

export interface FeedbackRecordDetailed extends FeedbackRecord {
  candidate: Candidate;
  vacancy: Vacancy;
}

export interface IntegrationStatus {
  key: string;
  title: string;
  description: string;
  status: "healthy" | "degraded";
  lastSync: string;
}

export interface AppSettings {
  modelVersion: string;
  minScoreThreshold: number;
  dataRetentionDays: number;
  piiMaskingEnabled: boolean;
  auditLoggingEnabled: boolean;
}
