export type ApplicationState =
  | "received"
  | "extracted"
  | "queued"
  | "evaluated"
  | "error";

export type IntegrityVerdict = "clean" | "suspicious" | "tampered";
export type DecisionKind = "shortlist" | "reject";

export interface Decision {
  kind: DecisionKind;
  reason: string;
  decided_by: string;
  created_at: string;
}

export interface ApplicationSummary {
  id: string;
  candidate_name: string;
  candidate_email: string;
  state: ApplicationState;
  applied_at: string;
  /** Absent until the batch returns; the row still appears. */
  overall_score: string | null;
  summary: string;
  mandatory_requirements_met: boolean | null;
  integrity: IntegrityVerdict | null;
  hidden_text_chars: number;
  needs_human_review: boolean;
  decision: Decision | null;
}

export interface Evidence {
  quote: string;
  found: boolean;
  /** Offsets into `resume_text`, for highlighting the exact span. */
  start: number | null;
  end: number | null;
}

export interface CriterionScore {
  criterion_id: string;
  criterion_name: string;
  weight: number;
  mandatory: boolean;
  score: number;
  justification: string;
  evidence: Evidence[];
}

export interface HiddenSpan {
  text: string;
  reason: string;
  page: number;
  detail: string;
}

export interface Integrity {
  verdict: IntegrityVerdict;
  hidden_spans: HiddenSpan[];
  matched_patterns: string[];
}

export interface ApplicationDetail {
  id: string;
  opening_id: string;
  opening_title: string;
  candidate_name: string;
  candidate_email: string;
  candidate_phone: string | null;
  candidate_linkedin: string | null;
  state: ApplicationState;
  applied_at: string;
  consented_at: string;
  resume_text: string;
  page_count: number;
  overall_score: string | null;
  relevant_years_experience: string | null;
  mandatory_requirements_met: boolean | null;
  missing_requirements: string[];
  detected_skills: string[];
  summary: string;
  /** What the model saw as risk in the candidate. */
  risks: string[];
  /** What our own verification objected to. A different thing entirely. */
  review_flags: string[];
  needs_human_review: boolean;
  model_id: string | null;
  prompt_version: string | null;
  rubric_version: number | null;
  criteria: CriterionScore[];
  integrity: Integrity | null;
  decision: Decision | null;
}

export interface RankedPage {
  opening_id: string;
  opening_title: string;
  total: number;
  evaluated: number;
  items: ApplicationSummary[];
}

export interface Opening {
  id: string;
  slug: string;
  title: string;
  status: "open" | "closed";
}

export interface SearchHit {
  application_id: string;
  candidate_name: string;
  overall_score: string | null;
  excerpt: string;
}
