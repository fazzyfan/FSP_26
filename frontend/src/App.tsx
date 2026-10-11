import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RedirectIfAuthed, RequireAuth } from "./auth/Protected";
import { PublicLayout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ConfirmEmailPage, PendingEmailPage } from "./pages/ConfirmEmailPage";
import { CandidateCabinet } from "./pages/candidate/CandidateCabinet";
import { ProfileForm } from "./pages/candidate/ProfileForm";
import { AssessmentPage } from "./pages/candidate/AssessmentPage";
import { InvitationsPage as CandidateInvitationsPage } from "./pages/candidate/InvitationsPage";
import { EmployerCabinet } from "./pages/employer/EmployerCabinet";
import { CompanyForm } from "./pages/employer/CompanyForm";
import { NeedsPage } from "./pages/employer/NeedsPage";
import { MatchesPage } from "./pages/employer/MatchesPage";
import { InvitationsPage as EmployerInvitationsPage } from "./pages/employer/InvitationsPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route
              path="/login"
              element={
                <RedirectIfAuthed>
                  <LoginPage />
                </RedirectIfAuthed>
              }
            />
            <Route
              path="/register"
              element={
                <RedirectIfAuthed>
                  <RegisterPage />
                </RedirectIfAuthed>
              }
            />
            <Route path="/confirm-email" element={<ConfirmEmailPage />} />
            <Route path="/confirm-email/pending" element={<PendingEmailPage />} />

            {/* Отдельные вкладки для авторизованных (без сайдбара кабинета) */}
            <Route
              path="/candidate/test"
              element={
                <RequireAuth roles={["candidate"]}>
                  <AssessmentPage />
                </RequireAuth>
              }
            />
            <Route
              path="/candidate/invites"
              element={
                <RequireAuth roles={["candidate"]}>
                  <CandidateInvitationsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/employer/needs"
              element={
                <RequireAuth roles={["employer"]}>
                  <NeedsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/employer/search"
              element={
                <RequireAuth roles={["employer"]}>
                  <MatchesPage />
                </RequireAuth>
              }
            />
            <Route
              path="/employer/invites"
              element={
                <RequireAuth roles={["employer"]}>
                  <EmployerInvitationsPage />
                </RequireAuth>
              }
            />
          </Route>

          {/* Кабинет кандидата — только профиль и резюме */}
          <Route
            path="/candidate"
            element={
              <RequireAuth roles={["candidate"]}>
                <CandidateCabinet />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/candidate/profile" replace />} />
            <Route path="profile" element={<ProfileForm />} />
          </Route>

          {/* Кабинет работодателя — только профиль компании */}
          <Route
            path="/employer"
            element={
              <RequireAuth roles={["employer"]}>
                <EmployerCabinet />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/employer/company" replace />} />
            <Route path="company" element={<CompanyForm />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}