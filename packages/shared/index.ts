export type Locale = 'en' | 'zh';
export type Text = Record<Locale,string>;
export interface Source {id:string; name:string; url:string; publishedAt:string; eventAt:string|null; timezone:string; synthetic:boolean; excerpt:Text;}
export interface Story {id:string; category:string; maturity:string; company:string; kind:'feature'|'quick_bite'; title:Text; summary:Text; why:Text; limitation:Text; sourceIds:string[]; evidenceStatus:'verified'|'synthetic'; score:number;}
export interface Issue {id:string; slug:string; date:string; state:'draft'|'validated'|'published'; validated:boolean; synthetic:boolean; title:Text; introduction:Text; sources:Source[]; stories:Story[];}

// Public projections cannot carry retained publisher excerpts or arbitrary evidence fields.
export type PublicSource = Omit<Source, 'excerpt'>;
export type PublicIssue = Omit<Issue, 'sources'> & {sources: PublicSource[]};
export interface PublicSourceClearance {
  sourceId: string; url: string; publisher: string; approved: boolean;
  basis: 'permission' | 'legal-review'; evidenceUrl: string; reviewedBy: string; reviewedAt: string;
}
export interface PublicEditionClearance {
  issueId: string; contentSha256: string; editorialApproved: boolean;
  reviewedBy: string; reviewedAt: string; reviewEvidence: string;
  sourceLinks: PublicSourceClearance[];
}
export interface PublicDisplayPolicy {
  version: 1; intendedUse: 'public-web'; editions: PublicEditionClearance[];
}

export type {TrackerData, TrackerEvidenceStatus, TrackerMilestoneView, TrackerProjectView, TrackerStage, TrackerTopic} from './tracker/types';
