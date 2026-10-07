import type { ProblemDetails } from "./types";

const API_BASE = "/api/v1";
const CSRF_COOKIE = "fsp_csrf";

export class ApiError extends Error {
  status: number;
  problem: ProblemDetails;

  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail || problem.title || "Ошибка запроса");
    this.status = status;
    this.problem = problem;
  }

  fieldError(field: string): string | null {
    return this.problem.errors?.find((e) => e.field === field)?.message ?? null;
  }
}

function readCookie(name: string): string {
  const row = document.cookie
    .split("; ")
    .find((r) => r.startsWith(`${name}=`));
  return row ? decodeURIComponent(row.split("=")[1]) : "";
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

/**
 * Обёртка над fetch: credentials для cookie-сессии, CSRF-заголовок для
 * изменяющих методов (double-submit, NFR-02), разбор Problem Details (RFC 9457).
 */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers ?? {}),
  };
  if (method !== "GET") {
    headers["X-CSRF-Token"] = readCookie(CSRF_COOKIE);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  let data: ProblemDetails | T | null = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    throw new ApiError(
      res.status,
      (data as ProblemDetails) ?? {
        title: "Ошибка запроса",
        code: "UNKNOWN",
        status: res.status,
      },
    );
  }
  return data as T;
}

export const authApi = {
  register: (body: {
    email: string;
    password: string;
    role: string;
    consent_version: string;
    consent_granted: boolean;
  }) =>
    api<{ id: string; email: string; status: string; detail: string }>("/auth/register", {
      method: "POST",
      body,
    }),
  confirmEmail: (token: string) =>
    api<import("./types").SessionInfo>("/auth/confirm-email", { method: "POST", body: { token } }),
  resendConfirmation: (email: string) =>
    api<{ detail: string }>("/auth/resend-confirmation", { method: "POST", body: { email } }),
  login: (email: string, password: string) =>
    api<import("./types").SessionInfo>("/auth/login", { method: "POST", body: { email, password } }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
  session: () => api<import("./types").SessionInfo>("/auth/session"),
  csrf: () => api<{ detail: string }>("/auth/csrf"),
};

export const meApi = {
  me: () => api<import("./types").Me>("/me"),
};

export const referenceApi = {
  industries: () => api<import("./types").ReferenceItem[]>("/references/industries"),
  specializations: () => api<import("./types").ReferenceItem[]>("/references/specializations"),
  grades: () => api<import("./types").ReferenceItem[]>("/references/grades"),
  skills: () => api<import("./types").ReferenceItem[]>("/references/skills"),
  roles: () => api<import("./types").ReferenceItem[]>("/references/roles"),
  consents: () => api<import("./types").ConsentDoc[]>("/references/consents"),
};

export const candidateApi = {
  getProfile: () => api<import("./types").CandidateProfile | null>("/candidate/profile"),
  saveProfile: (body: import("./types").CandidateProfileIn) =>
    api<import("./types").CandidateProfile>("/candidate/profile", { method: "PUT", body }),
  // Оценка и категория (FR-08..FR-13)
  getAssessment: () => api<import("./types").AssessmentSummary>("/candidate/assessment"),
  getTestQuestions: (specializationId: string) =>
    api<import("./types").TestQuestion[]>(`/candidate/assessment/tests/${specializationId}/questions`),
  submitTest: (specializationId: string, answers: import("./types").TestAnswer[]) =>
    api<import("./types").AttemptResult>(`/candidate/assessment/tests/${specializationId}/submit`, {
      method: "POST",
      body: { answers },
    }),
  // Приглашения (FR-23..FR-27)
  listInvitations: () => api<import("./types").CandidateInvitation[]>("/candidate/invitations"),
  respondInvitation: (id: string, decision: "accept" | "decline") =>
    api<import("./types").CandidateInvitation>(`/candidate/invitations/${id}/respond`, {
      method: "POST",
      body: { decision },
    }),
  revokeContacts: (id: string) =>
    api<import("./types").CandidateInvitation>(`/candidate/invitations/${id}/contacts/revoke`, {
      method: "POST",
    }),
};

export const employerApi = {
  getCompany: () => api<import("./types").Company | null>("/employer/company"),
  saveCompany: (body: import("./types").CompanyIn) =>
    api<import("./types").Company>("/employer/company", { method: "PUT", body }),
  listNeeds: () => api<import("./types").EmployerNeed[]>("/employer/needs"),
  createNeed: (body: import("./types").EmployerNeedIn) =>
    api<import("./types").EmployerNeed>("/employer/needs", { method: "POST", body }),
  // Подбор (FR-18..FR-22)
  listMatches: (needId: string) =>
    api<import("./types").MatchCandidate[]>(`/employer/needs/${needId}/matches`),
  // Приглашения (FR-23..FR-27)
  listInvitations: () => api<import("./types").EmployerInvitation[]>("/employer/invitations"),
  createInvitation: (needId: string, body: {
    candidate_id: string;
    salary_from: number;
    salary_to: number;
    message: string;
  }) =>
    api<import("./types").EmployerInvitation>(`/employer/needs/${needId}/invitations`, {
      method: "POST",
      body,
    }),
  withdrawInvitation: (id: string) =>
    api<import("./types").EmployerInvitation>(`/employer/invitations/${id}/withdraw`, { method: "POST" }),
  getInvitationContacts: (id: string) =>
    api<import("./types").CandidateContacts>(`/employer/invitations/${id}/contacts`),
};