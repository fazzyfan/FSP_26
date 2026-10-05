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
}