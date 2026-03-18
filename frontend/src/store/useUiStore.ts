import { create } from "zustand";

interface UiState {
  selectedVacancyId: string | null;
  activeProcessingJobId: string | null;
  minScoreThreshold: number;
  modelVersion: string;
  setSelectedVacancyId: (vacancyId: string | null) => void;
  setActiveProcessingJobId: (jobId: string | null) => void;
  setMinScoreThreshold: (value: number) => void;
  setModelVersion: (value: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedVacancyId: null,
  activeProcessingJobId: null,
  minScoreThreshold: 65,
  modelVersion: "ranker-v1.4",
  setSelectedVacancyId: (vacancyId) => set({ selectedVacancyId: vacancyId }),
  setActiveProcessingJobId: (jobId) => set({ activeProcessingJobId: jobId }),
  setMinScoreThreshold: (value) => set({ minScoreThreshold: value }),
  setModelVersion: (value) => set({ modelVersion: value })
}));

