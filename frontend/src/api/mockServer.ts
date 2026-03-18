import type {
  AnalyticsSummary,
  AppSettings,
  Candidate,
  DashboardSummary,
  FeedbackRecord,
  FeedbackRecordDetailed,
  IntegrationStatus,
  ProcessingJob,
  ShortlistCandidate,
  ShortlistEntry,
  Vacancy
} from "../types";

const NETWORK_DELAY_MS = 260;
const STEP_DURATION_MS = 2500;

const KNOWN_SKILLS = [
  "python",
  "sql",
  "fastapi",
  "xgboost",
  "machine learning",
  "data science",
  "react",
  "typescript",
  "docker",
  "nlp",
  "aws",
  "statistics"
];

let idCounter = 100;

const now = Date.now();

const candidates: Candidate[] = [
  {
    id: "cand-01",
    fullName: "Amina Kenzhebek",
    headline: "Senior ML Engineer",
    location: "Almaty, KZ",
    experienceYears: 7,
    skills: ["python", "xgboost", "machine learning", "aws", "nlp"],
    resumePreview:
      "Built ranking services for hiring pipelines, deployed ML scoring APIs, and improved candidate selection precision by 17%."
  },
  {
    id: "cand-02",
    fullName: "Daniyar Issatay",
    headline: "Data Scientist",
    location: "Astana, KZ",
    experienceYears: 5,
    skills: ["python", "sql", "statistics", "machine learning"],
    resumePreview:
      "Designed candidate matching features with BM25 and overlap metrics, delivered model monitoring dashboards and bias checks."
  },
  {
    id: "cand-03",
    fullName: "Laura Kim",
    headline: "ML Platform Engineer",
    location: "Seattle, US",
    experienceYears: 6,
    skills: ["python", "fastapi", "docker", "aws", "typescript"],
    resumePreview:
      "Owned queue-based inference pipelines, implemented polling/websocket status updates, and optimized throughput under peak load."
  },
  {
    id: "cand-04",
    fullName: "Timur Nurpeissov",
    headline: "NLP Engineer",
    location: "Berlin, DE",
    experienceYears: 4,
    skills: ["python", "nlp", "machine learning", "sql"],
    resumePreview:
      "Built explanation layers for candidate ranking models, including feature-attribution outputs and recruiter-readable summaries."
  },
  {
    id: "cand-05",
    fullName: "Maya Patel",
    headline: "Frontend Engineer (React)",
    location: "Boston, US",
    experienceYears: 5,
    skills: ["react", "typescript", "python", "analytics"],
    resumePreview:
      "Developed recruiter dashboards to visualize processing queues, shortlist quality, and reviewer feedback loops."
  },
  {
    id: "cand-06",
    fullName: "Eldar Sarsembay",
    headline: "Data Engineer",
    location: "Almaty, KZ",
    experienceYears: 8,
    skills: ["python", "sql", "docker", "aws", "fastapi"],
    resumePreview:
      "Implemented high-volume ETL and feature stores for ranking models, with strict data privacy controls and audit logs."
  },
  {
    id: "cand-07",
    fullName: "Sofia Alvarez",
    headline: "Applied Scientist",
    location: "Madrid, ES",
    experienceYears: 3,
    skills: ["python", "machine learning", "statistics", "nlp"],
    resumePreview:
      "Delivered candidate scoring experiments, precision@10 tracking, and fairness metric monitoring for hiring teams."
  },
  {
    id: "cand-08",
    fullName: "Ivan Chen",
    headline: "Backend Engineer",
    location: "Toronto, CA",
    experienceYears: 6,
    skills: ["fastapi", "python", "docker", "sql"],
    resumePreview:
      "Built robust API services for ranking workflows, asynchronous job orchestration, and ATS export integrations."
  }
];

const vacancies: Vacancy[] = [
  {
    id: "vac-01",
    title: "Machine Learning Engineer",
    description:
      "Own end-to-end ranking pipelines, build FastAPI services, and improve explainable candidate scoring.",
    extractedSkills: ["python", "machine learning", "fastapi", "xgboost"],
    weights: { skills: 0.65, experience: 0.35 },
    status: "READY",
    candidatesFound: 8,
    createdAt: new Date(now - 1000 * 60 * 60 * 40).toISOString(),
    shortlistReadyAt: new Date(now - 1000 * 60 * 60 * 32).toISOString()
  },
  {
    id: "vac-02",
    title: "Data Scientist",
    description:
      "Create matching features, evaluate precision and recall, and work with recruiter feedback for retraining.",
    extractedSkills: ["python", "sql", "statistics", "machine learning"],
    weights: { skills: 0.7, experience: 0.3 },
    status: "READY",
    candidatesFound: 8,
    createdAt: new Date(now - 1000 * 60 * 60 * 18).toISOString(),
    shortlistReadyAt: new Date(now - 1000 * 60 * 60 * 11).toISOString()
  },
  {
    id: "vac-03",
    title: "ML Platform Engineer",
    description:
      "Improve queue throughput, monitoring, and deployment automation for ranking and shortlist generation.",
    extractedSkills: ["python", "docker", "aws", "fastapi"],
    weights: { skills: 0.6, experience: 0.4 },
    status: "PROCESSING",
    candidatesFound: 0,
    createdAt: new Date(now - 1000 * 60 * 60 * 2).toISOString(),
    processingJobId: "job-01"
  },
  {
    id: "vac-04",
    title: "NLP Engineer",
    description:
      "Design candidate explanation quality checks and improve natural-language feature extraction.",
    extractedSkills: ["python", "nlp", "machine learning"],
    weights: { skills: 0.62, experience: 0.38 },
    status: "NEW",
    candidatesFound: 0,
    createdAt: new Date(now - 1000 * 60 * 42).toISOString()
  }
];

const shortlistEntries: ShortlistEntry[] = [];

const feedbackRecords: FeedbackRecord[] = [
  {
    id: "fb-01",
    candidateId: "cand-01",
    vacancyId: "vac-01",
    decision: "Approve",
    reason: "Excellent feature ownership and ranking experience.",
    modelVersion: "ranker-v1.4",
    updatedAt: new Date(now - 1000 * 60 * 40).toISOString(),
    sentToRetraining: true
  },
  {
    id: "fb-02",
    candidateId: "cand-04",
    vacancyId: "vac-02",
    decision: "Reject",
    reason: "Skill overlap was high but production system depth was limited.",
    modelVersion: "ranker-v1.4",
    updatedAt: new Date(now - 1000 * 60 * 18).toISOString(),
    sentToRetraining: false
  }
];

const processingJobs = new Map<string, ProcessingJob>([
  [
    "job-01",
    {
      id: "job-01",
      vacancyId: "vac-03",
      queueDepth: 4,
      startedAt: now - STEP_DURATION_MS * 1.2,
      completed: false,
      steps: [
        { key: "parsing", label: "Parsing job description", status: "running", progress: 74 },
        { key: "searching", label: "Searching candidates", status: "pending", progress: 0 },
        { key: "scoring", label: "Scoring (ML)", status: "pending", progress: 0 },
        { key: "ranking", label: "Ranking", status: "pending", progress: 0 }
      ]
    }
  ]
]);

const integrations: IntegrationStatus[] = [
  {
    key: "ats-export",
    title: "ATS Export API",
    description: "Exports approved shortlist candidates to connected ATS.",
    status: "healthy",
    lastSync: new Date(now - 1000 * 60 * 7).toISOString()
  },
  {
    key: "webhooks",
    title: "Webhooks",
    description: "Delivers vacancy and shortlist events to external listeners.",
    status: "healthy",
    lastSync: new Date(now - 1000 * 60 * 2).toISOString()
  },
  {
    key: "external-hris",
    title: "External HR Systems",
    description: "Syncs final hiring decisions and status updates.",
    status: "degraded",
    lastSync: new Date(now - 1000 * 60 * 19).toISOString()
  }
];

let appSettings: AppSettings = {
  modelVersion: "ranker-v1.4",
  minScoreThreshold: 65,
  dataRetentionDays: 180,
  piiMaskingEnabled: true,
  auditLoggingEnabled: true
};

function wait(ms = NETWORK_DELAY_MS): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function createId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((item) => item.toLowerCase())));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round(value: number, digits = 1): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function extractSkills(source: string): string[] {
  const lower = source.toLowerCase();
  const skills = KNOWN_SKILLS.filter((skill) => lower.includes(skill));
  return unique(skills.length > 0 ? skills : ["python", "sql", "machine learning"]);
}

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function buildShortlist(vacancy: Vacancy): ShortlistEntry[] {
  const scored: ShortlistEntry[] = candidates.map((candidate) => {
    const overlap = vacancy.extractedSkills.filter((skill) =>
      candidate.skills.map((item) => item.toLowerCase()).includes(skill.toLowerCase())
    );
    const skillsMatch = round((overlap.length / Math.max(1, vacancy.extractedSkills.length)) * 100);
    const experienceScore = round(clamp(100 - Math.abs(candidate.experienceYears - 5) * 12, 45, 100));
    const noise = (hashString(`${candidate.id}:${vacancy.id}`) % 8) - 3;
    const weighted = vacancy.weights.skills * skillsMatch + vacancy.weights.experience * experienceScore + noise;
    const matchScore = round(clamp(weighted, 40, 99));

    return {
      vacancyId: vacancy.id,
      candidateId: candidate.id,
      matchScore,
      skillsMatch,
      experienceScore,
      topMatchingSkills: overlap.slice(0, 3),
      explanation: `Primary fit driven by ${overlap.slice(0, 2).join(", ") || "core skill overlap"} and experience alignment.`,
      explanationFactors: [
        { factor: "Skill overlap", impact: round(skillsMatch / 100) },
        { factor: "Experience alignment", impact: round(experienceScore / 100) },
        { factor: "Title relevance", impact: round(clamp(matchScore / 120, 0.2, 1), 2) }
      ],
      decision: "pending"
    };
  });

  return scored.sort((a, b) => b.matchScore - a.matchScore).slice(0, 10);
}

function ensureShortlist(vacancyId: string): void {
  const vacancy = vacancies.find((item) => item.id === vacancyId);
  if (!vacancy) {
    return;
  }

  const existing = shortlistEntries.some((item) => item.vacancyId === vacancyId);
  if (!existing) {
    shortlistEntries.push(...buildShortlist(vacancy));
  }
}

function startProcessingForVacancy(vacancy: Vacancy): ProcessingJob {
  const runningJob = vacancy.processingJobId ? processingJobs.get(vacancy.processingJobId) : undefined;
  if (runningJob && !runningJob.completed) {
    return runningJob;
  }

  const jobId = createId("job");
  const job: ProcessingJob = {
    id: jobId,
    vacancyId: vacancy.id,
    queueDepth: 4,
    startedAt: Date.now(),
    completed: false,
    steps: [
      { key: "parsing", label: "Parsing job description", status: "running", progress: 10 },
      { key: "searching", label: "Searching candidates", status: "pending", progress: 0 },
      { key: "scoring", label: "Scoring (ML)", status: "pending", progress: 0 },
      { key: "ranking", label: "Ranking", status: "pending", progress: 0 }
    ]
  };
  vacancy.status = "PROCESSING";
  vacancy.processingJobId = jobId;
  vacancy.shortlistReadyAt = undefined;
  processingJobs.set(jobId, job);
  return job;
}

function advanceProcessing(job: ProcessingJob): ProcessingJob {
  if (job.completed) {
    return job;
  }

  const elapsed = Date.now() - job.startedAt;
  const totalDuration = STEP_DURATION_MS * job.steps.length;

  job.steps = job.steps.map((step, index) => {
    const startMs = STEP_DURATION_MS * index;
    const endMs = STEP_DURATION_MS * (index + 1);

    if (elapsed >= endMs) {
      return { ...step, status: "done", progress: 100 };
    }
    if (elapsed < startMs) {
      return { ...step, status: "pending", progress: 0 };
    }
    const progress = clamp(((elapsed - startMs) / STEP_DURATION_MS) * 100, 5, 99);
    return { ...step, status: "running", progress: round(progress) };
  });

  job.queueDepth = clamp(4 - Math.floor(elapsed / STEP_DURATION_MS), 0, 4);
  job.completed = elapsed >= totalDuration;

  if (job.completed) {
    job.steps = job.steps.map((step) => ({ ...step, status: "done", progress: 100 }));
    job.queueDepth = 0;
    const vacancy = vacancies.find((item) => item.id === job.vacancyId);
    if (vacancy) {
      vacancy.status = "READY";
      vacancy.candidatesFound = candidates.length;
      vacancy.shortlistReadyAt = new Date().toISOString();
      ensureShortlist(vacancy.id);
    }
  }

  return job;
}

function processAllJobs(): void {
  Array.from(processingJobs.values()).forEach((job) => {
    advanceProcessing(job);
  });
}

function processingProgress(vacancy: Vacancy): number {
  if (vacancy.status === "READY") {
    return 100;
  }
  if (vacancy.status === "NEW") {
    return 0;
  }
  const job = vacancy.processingJobId ? processingJobs.get(vacancy.processingJobId) : undefined;
  if (!job) {
    return 8;
  }
  const completed = job.steps.reduce((acc, step) => acc + step.progress, 0);
  return round(completed / job.steps.length);
}

function toShortlistCandidate(entry: ShortlistEntry): ShortlistCandidate | null {
  const candidate = candidates.find((item) => item.id === entry.candidateId);
  const vacancy = vacancies.find((item) => item.id === entry.vacancyId);
  if (!candidate || !vacancy) {
    return null;
  }
  return {
    ...clone(entry),
    candidate: clone(candidate),
    vacancy: clone(vacancy)
  };
}

function decisionToFeedbackValue(decision: ShortlistEntry["decision"]): FeedbackRecord["decision"] {
  if (decision === "approved") {
    return "Approve";
  }
  return "Reject";
}

ensureShortlist("vac-01");
ensureShortlist("vac-02");

export async function listVacancies(): Promise<Vacancy[]> {
  processAllJobs();
  await wait();
  return clone(vacancies).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

export async function getVacancy(vacancyId: string): Promise<Vacancy | null> {
  processAllJobs();
  await wait();
  const found = vacancies.find((item) => item.id === vacancyId);
  return found ? clone(found) : null;
}

export async function createVacancy(payload: {
  title: string;
  description: string;
}): Promise<{ vacancy: Vacancy; processingJob: ProcessingJob }> {
  await wait();

  const vacancy: Vacancy = {
    id: createId("vac"),
    title: payload.title.trim(),
    description: payload.description.trim(),
    extractedSkills: extractSkills(`${payload.title} ${payload.description}`),
    weights: { skills: 0.65, experience: 0.35 },
    status: "NEW",
    candidatesFound: 0,
    createdAt: new Date().toISOString()
  };

  vacancies.unshift(vacancy);
  const processingJob = startProcessingForVacancy(vacancy);
  return { vacancy: clone(vacancy), processingJob: clone(processingJob) };
}

export async function updateVacancy(
  vacancyId: string,
  updates: {
    extractedSkills?: string[];
    weights?: Vacancy["weights"];
  }
): Promise<Vacancy | null> {
  await wait();
  const vacancy = vacancies.find((item) => item.id === vacancyId);
  if (!vacancy) {
    return null;
  }

  if (updates.extractedSkills) {
    vacancy.extractedSkills = unique(updates.extractedSkills.filter(Boolean));
  }
  if (updates.weights) {
    vacancy.weights = {
      skills: clamp(round(updates.weights.skills, 2), 0.1, 0.9),
      experience: clamp(round(updates.weights.experience, 2), 0.1, 0.9)
    };
  }

  if (vacancy.status === "READY") {
    for (let i = shortlistEntries.length - 1; i >= 0; i -= 1) {
      if (shortlistEntries[i]?.vacancyId === vacancyId) {
        shortlistEntries.splice(i, 1);
      }
    }
    ensureShortlist(vacancyId);
  }

  return clone(vacancy);
}

export async function generateShortlist(
  vacancyId: string
): Promise<{ ready: boolean; processingJobId?: string }> {
  await wait(180);
  const vacancy = vacancies.find((item) => item.id === vacancyId);
  if (!vacancy) {
    return { ready: false };
  }

  if (vacancy.status === "READY") {
    ensureShortlist(vacancyId);
    return { ready: true };
  }

  const job = startProcessingForVacancy(vacancy);
  return { ready: false, processingJobId: job.id };
}

export async function getProcessingJob(jobId: string): Promise<ProcessingJob | null> {
  await wait(120);
  const job = processingJobs.get(jobId);
  if (!job) {
    return null;
  }
  return clone(advanceProcessing(job));
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  processAllJobs();
  await wait();
  const totalVacancies = vacancies.length;
  const resumesProcessed = vacancies.reduce((acc, vacancy) => acc + vacancy.candidatesFound, 0);
  const avgMatchingScore =
    shortlistEntries.length === 0
      ? 0
      : round(shortlistEntries.reduce((acc, item) => acc + item.matchScore, 0) / shortlistEntries.length);

  const completedVacancies = vacancies.filter((item) => item.shortlistReadyAt);
  const avgShortlistHours =
    completedVacancies.length === 0
      ? 0
      : round(
          completedVacancies.reduce((acc, vacancy) => {
            const created = new Date(vacancy.createdAt).getTime();
            const ready = new Date(vacancy.shortlistReadyAt ?? vacancy.createdAt).getTime();
            return acc + Math.max(0, (ready - created) / (1000 * 60 * 60));
          }, 0) / completedVacancies.length,
          2
        );

  const pipeline = vacancies.slice(0, 5).map((vacancy) => ({
    vacancyId: vacancy.id,
    vacancyTitle: vacancy.title,
    status: vacancy.status,
    progress: processingProgress(vacancy)
  }));

  const recentShortlists = shortlistEntries
    .slice()
    .sort((a, b) => b.matchScore - a.matchScore)
    .slice(0, 6)
    .map(toShortlistCandidate)
    .filter((item): item is ShortlistCandidate => Boolean(item));

  const fairnessAlerts = shortlistEntries.filter((item) => item.matchScore < 68).length > 2 ? 2 : 1;

  return {
    totalVacancies,
    resumesProcessed,
    avgMatchingScore,
    avgShortlistHours,
    pipeline,
    insights: {
      modelAccuracy: 92.4,
      fairnessAlerts,
      systemLoad: 63
    },
    recentVacancies: clone(vacancies.slice(0, 4)),
    recentShortlists
  };
}

export async function listShortlistCandidates(
  vacancyId: string | null,
  minScoreThreshold: number
): Promise<ShortlistCandidate[]> {
  processAllJobs();
  await wait();
  if (!vacancyId) {
    return [];
  }
  ensureShortlist(vacancyId);

  return shortlistEntries
    .filter((item) => item.vacancyId === vacancyId && item.matchScore >= minScoreThreshold)
    .map(toShortlistCandidate)
    .filter((item): item is ShortlistCandidate => Boolean(item));
}

export async function updateShortlistDecision(
  vacancyId: string,
  candidateId: string,
  decision: "approved" | "rejected"
): Promise<void> {
  await wait(140);
  const shortlist = shortlistEntries.find(
    (item) => item.vacancyId === vacancyId && item.candidateId === candidateId
  );
  if (!shortlist) {
    return;
  }
  shortlist.decision = decision;

  const existing = feedbackRecords.find(
    (record) => record.candidateId === candidateId && record.vacancyId === vacancyId
  );
  const mappedDecision = decisionToFeedbackValue(decision);

  if (existing) {
    existing.decision = mappedDecision;
    existing.updatedAt = new Date().toISOString();
    existing.sentToRetraining = false;
    if (!existing.reason) {
      existing.reason = decision === "approved" ? "Strong ranking confidence." : "Rejected during review.";
    }
    return;
  }

  feedbackRecords.unshift({
    id: createId("fb"),
    candidateId,
    vacancyId,
    decision: mappedDecision,
    reason: decision === "approved" ? "High confidence shortlist candidate." : "Rejected after manual review.",
    modelVersion: appSettings.modelVersion,
    updatedAt: new Date().toISOString(),
    sentToRetraining: false
  });
}

export async function listCandidates(): Promise<Candidate[]> {
  await wait();
  return clone(candidates);
}

export async function getCandidateProfile(candidateId: string): Promise<{
  candidate: Candidate | null;
  evaluations: ShortlistCandidate[];
}> {
  processAllJobs();
  await wait();
  const candidate = candidates.find((item) => item.id === candidateId) ?? null;
  const evaluations = shortlistEntries
    .filter((item) => item.candidateId === candidateId)
    .map(toShortlistCandidate)
    .filter((item): item is ShortlistCandidate => Boolean(item))
    .sort((a, b) => b.matchScore - a.matchScore);
  return { candidate: candidate ? clone(candidate) : null, evaluations };
}

export async function listFeedbackRecords(): Promise<FeedbackRecordDetailed[]> {
  processAllJobs();
  await wait();
  return feedbackRecords
    .slice()
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
    .map((record) => {
      const candidate = candidates.find((item) => item.id === record.candidateId);
      const vacancy = vacancies.find((item) => item.id === record.vacancyId);
      if (!candidate || !vacancy) {
        return null;
      }
      return {
        ...clone(record),
        candidate: clone(candidate),
        vacancy: clone(vacancy)
      };
    })
    .filter((item): item is FeedbackRecordDetailed => Boolean(item));
}

export async function updateFeedbackRecord(
  recordId: string,
  updates: Pick<FeedbackRecord, "decision" | "reason">
): Promise<void> {
  await wait(130);
  const record = feedbackRecords.find((item) => item.id === recordId);
  if (!record) {
    return;
  }
  record.decision = updates.decision;
  record.reason = updates.reason;
  record.updatedAt = new Date().toISOString();
  record.sentToRetraining = false;

  const shortlist = shortlistEntries.find(
    (item) => item.candidateId === record.candidateId && item.vacancyId === record.vacancyId
  );
  if (shortlist) {
    shortlist.decision = updates.decision === "Approve" ? "approved" : "rejected";
  }
}

export async function sendFeedbackToRetraining(recordId: string): Promise<void> {
  await wait(180);
  const record = feedbackRecords.find((item) => item.id === recordId);
  if (!record) {
    return;
  }
  record.sentToRetraining = true;
  record.updatedAt = new Date().toISOString();
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  processAllJobs();
  await wait();
  const decisions = shortlistEntries.filter((item) => item.decision !== "pending");
  const approved = decisions.filter((item) => item.decision === "approved").length;
  const reviewed = decisions.length || 1;
  const precisionAt10 = round((approved / reviewed) * 100, 1);
  const recall = round((approved / Math.max(1, shortlistEntries.length)) * 100, 1);

  const readyVacancies = vacancies.filter((vacancy) => vacancy.shortlistReadyAt);
  const avgShortlistHours =
    readyVacancies.length === 0
      ? 0
      : round(
          readyVacancies.reduce((acc, vacancy) => {
            const start = new Date(vacancy.createdAt).getTime();
            const end = new Date(vacancy.shortlistReadyAt ?? vacancy.createdAt).getTime();
            return acc + (end - start) / (1000 * 60 * 60);
          }, 0) / readyVacancies.length,
          2
        );

  const fairnessScore = 93.1;
  const performanceSeries = [
    { label: "Nov", precision: 80, recall: 54 },
    { label: "Dec", precision: 82, recall: 57 },
    { label: "Jan", precision: 84, recall: 58 },
    { label: "Feb", precision: 86, recall: 60 },
    { label: "Mar", precision: round(precisionAt10, 1), recall: round(recall, 1) }
  ];

  const approvedEntries = shortlistEntries.filter((item) => item.decision === "approved");
  const buckets = [
    { bucket: "0-3 yrs", value: 0 },
    { bucket: "4-6 yrs", value: 0 },
    { bucket: "7+ yrs", value: 0 }
  ];
  approvedEntries.forEach((item) => {
    const candidate = candidates.find((candidateValue) => candidateValue.id === item.candidateId);
    if (!candidate) {
      return;
    }
    if (candidate.experienceYears <= 3) {
      buckets[0]!.value += 1;
    } else if (candidate.experienceYears <= 6) {
      buckets[1]!.value += 1;
    } else {
      buckets[2]!.value += 1;
    }
  });

  return {
    precisionAt10,
    recall,
    avgShortlistHours,
    fairnessScore,
    performanceSeries,
    hiringDistribution: buckets
  };
}

export async function listIntegrations(): Promise<IntegrationStatus[]> {
  await wait();
  return clone(integrations);
}

export async function getSettings(): Promise<AppSettings> {
  await wait();
  return clone(appSettings);
}

export async function updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  await wait(140);
  appSettings = { ...appSettings, ...patch };
  return clone(appSettings);
}
