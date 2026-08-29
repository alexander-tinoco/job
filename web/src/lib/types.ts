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
  /** Questions the applicant answered differently from what the opening asked. */
  unmet_requirements: string[];
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
  /** The applicant's own declarations. Nothing consumes them but the screen. */
  screening_answers: ScreeningAnswer[];
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

export interface ComparedSide {
  application_id: string;
  score: number;
  /** What this criterion added to that candidate's overall score. */
  contribution: string;
  justification: string;
  quotes: string[];
}

export interface ComparedCriterion {
  criterion_id: string;
  criterion_name: string;
  weight: number;
  mandatory: boolean;
  sides: ComparedSide[];
  /** Empty when everyone scored the same: a tie crowns nobody. */
  leaders: string[];
  spread: string;
}

export interface ComparedCandidate {
  id: string;
  name: string;
  overall_score: string;
  summary: string;
  relevant_years_experience: string;
  mandatory_requirements_met: boolean;
  tampered: boolean;
  decision: string | null;
}

export interface Comparison {
  opening_title: string;
  candidates: ComparedCandidate[];
  criteria: ComparedCriterion[];
  /** The one or two criteria carrying the difference. */
  decisive: string[];
}

export interface ScreeningQuestion {
  id: string;
  text: string;
  /** No `expected_answer`: the API never tells an applicant which answer is wanted. */
}

export interface ScreeningAnswer {
  question_id: string;
  text: string;
  answer: boolean;
  expected_answer: boolean;
  matches: boolean;
}

export interface DuplicateMatch {
  application_id: string;
  candidate_name: string;
  opening_title: string;
  /** Estimated overlap of the two documents, 0.0 to 1.0. */
  similarity: number;
  identical: boolean;
  /** False is the finding: one document, two identities. */
  same_person: boolean;
}
