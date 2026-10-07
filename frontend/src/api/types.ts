export type Role = "candidate" | "employer";

export interface SessionInfo {
  id: string;
  email: string;
  role: Role;
  status: string;
}

export interface Me {
  id: string;
  email: string;
  role: Role;
  status: string;
  has_profile: boolean;
  has_company: boolean;
  needs_count: number;
}

export interface ReferenceItem {
  id: string;
  code: string;
  name: string;
}

export interface ConsentDoc {
  code: string;
  version: string;
  title: string;
  text: string;
}

export interface CandidateProfile {
  full_name: string;
  phone: string | null;
  contact_email: string;
  experience_months: number;
  claimed_level: string | null;
  claimed_level_code: string | null;
  roles: string[];
  skills: string[];
  soft_skills: string[];
  about: string | null;
  is_published: boolean;
  show_fsp: boolean;
  fsp_member_id: string | null;
  version: number;
  updated_at: string | null;
}

export interface CandidateProfileIn {
  full_name: string;
  phone: string | null;
  experience_months: number;
  role_ids: string[];
  skill_ids: string[];
  claimed_level_id: string | null;
  soft_skills: string[];
  about: string | null;
  is_published: boolean;
  show_fsp: boolean;
  fsp_member_id: string | null;
  version: number;
}

export interface Company {
  id: string;
  name: string;
  industry_id: string | null;
  industry_name: string | null;
  description: string | null;
  contact_email: string;
  website: string | null;
  phone: string | null;
  version: number;
}

export interface CompanyIn {
  name: string;
  industry_id: string | null;
  description: string | null;
  contact_email: string;
  website: string | null;
  phone: string | null;
  version: number;
}

export interface EmployerNeed {
  id: string;
  company_id: string;
  title: string;
  tasks_text: string;
  industry_id: string | null;
  specialization_id: string | null;
  grade_ids: string[];
  skill_ids: string[];
  created_at: string | null;
}

export interface EmployerNeedIn {
  title: string;
  tasks_text: string;
  industry_id: string | null;
  specialization_id: string | null;
  grade_ids: string[];
  skill_ids: string[];
}

// --- Оценка и категория (FR-08..FR-13) ---

export interface TestGradeInfo {
  grade_code: string;
  grade_name: string;
  questions_count: number;
}

export interface TestInfo {
  specialization_id: string;
  specialization_name: string;
  grades: TestGradeInfo[];
  questions_count: number;
}

export interface ConfirmedCategory {
  id: string;
  specialization_id: string;
  specialization_name: string;
  grade_code: string;
  grade_name: string;
  confirmed_at: string;
}

export interface BlockResult {
  block: number;
  correct: number;
  total: number;
}

export interface AttemptResult {
  attempt_id: string;
  specialization_id: string;
  specialization_name: string;
  grade_code: string | null;
  grade_name: string | null;
  status: string;
  correct_count: number;
  total_count: number;
  score_percent: number;
  block_results: BlockResult[];
  passed: boolean;
  next_attempt_at: string | null;
  message: string;
}

export interface ActiveAttempt {
  attempt_id: string;
  specialization_id: string;
  specialization_name: string;
  grade_code: string;
  grade_name: string;
  expires_at: string;
  remaining_seconds: number;
}

export interface AssessmentSummary {
  category: ConfirmedCategory | null;
  active_attempt: ActiveAttempt | null;
  last_attempt: AttemptResult | null;
  next_attempt_at: string | null;
  tests: TestInfo[];
}

export interface QuestionOption {
  id: string;
  text: string;
}

export interface TestQuestion {
  id: string;
  text: string;
  block: number;
  options: QuestionOption[];
}

export interface TestAnswer {
  question_id: string;
  option_id: string;
}

export interface AttemptState {
  attempt_id: string;
  specialization_id: string;
  specialization_name: string;
  grade_code: string;
  grade_name: string;
  status: string;
  started_at: string;
  expires_at: string;
  remaining_seconds: number;
  questions: TestQuestion[];
  answers: TestAnswer[];
}

// --- Подбор (FR-18..FR-22) ---

export interface ScoreBreakdown {
  competencies: number;
  test: number;
  fsp: number;
}

export interface MatchCandidate {
  candidate_id: string;
  full_name: string;
  specialization_name: string;
  grade_code: string;
  grade_name: string;
  experience_months: number;
  score: number;
  score_breakdown: ScoreBreakdown;
  matched_skills: string[];
  reasons: string[];
}

export interface MatchPage {
  items: MatchCandidate[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// --- Приглашения (FR-23..FR-27) ---

export interface EmployerInvitation {
  id: string;
  need_id: string;
  need_title: string;
  candidate_id: string;
  candidate_name: string;
  salary_from: number;
  salary_to: number;
  message: string;
  status: string;
  created_at: string;
  responded_at: string | null;
  contacts_consented_at: string | null;
  contacts_revoked_at: string | null;
}

export interface CandidateInvitation {
  id: string;
  company_id: string;
  company_name: string;
  need_title: string;
  salary_from: number;
  salary_to: number;
  message: string;
  status: string;
  created_at: string;
  responded_at: string | null;
  company_contact_email: string | null;
  company_phone: string | null;
  contacts_consented_at: string | null;
  contacts_revoked_at: string | null;
}

export interface CandidateContacts {
  full_name: string;
  phone: string | null;
  email: string;
  about: string | null;
}

export interface FieldError {
  field: string;
  code: string;
  error_class: string;
  message: string;
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  error_class?: string | null;
  detail?: string | null;
  errors?: FieldError[];
  request_id?: string;
  recovery?: string;
  retry_after_seconds?: number;
  next_allowed_at?: string;
  extra?: Record<string, unknown>;
}