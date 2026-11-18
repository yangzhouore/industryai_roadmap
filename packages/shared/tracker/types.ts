import type {PublicSource, Text} from '../index';

export const trackerStages = ['research', 'prototype', 'pilot', 'deployed', 'scaling', 'commercial'] as const;
export type TrackerStage = (typeof trackerStages)[number];
export type TrackerEvidenceStatus = 'vendor_claim' | 'independently_verified' | 'reported' | 'synthetic';

export interface TrackerTopic {
  id: string;
  name: Text;
}

export interface TrackerProjectView {
  id: string;
  name: Text;
  companyIds: string[];
  technologyIds: string[];
}

export interface TrackerMilestoneView {
  id: string;
  projectId: string;
  title: Text;
  summary: Text;
  stage: TrackerStage;
  status: TrackerEvidenceStatus;
  eventAt: string | null;
  publishedAt: string;
  companyIds: string[];
  technologyIds: string[];
  sources: PublicSource[];
  issueSlug: string;
}

export interface TrackerData {
  synthetic: boolean;
  companies: TrackerTopic[];
  technologies: TrackerTopic[];
  projects: TrackerProjectView[];
  milestones: TrackerMilestoneView[];
}
