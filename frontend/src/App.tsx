import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RedirectIfAuthed, RequireAuth } from "./auth/Protected";
import { PublicLayout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ConfirmEmailPage, PendingEmailPage } from "./pages/ConfirmEmailPage";
import { CandidateCabinet, InvitesPlaceholder, TestPlaceholder } from "./pages/candidate/CandidateCabinet";
import { ProfileForm } from "./pages/candidate/ProfileForm";
import {
  EmployerCabinet,
  EmployerInvitesPlaceholder,
  SearchPlaceholder,
} from "./pages/employer/EmployerCabinet";
import { CompanyForm } from "./pages/employer/CompanyForm";
import { NeedsPage } from "./pages/employer/NeedsPage";

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
          </Route>

          {/* Кабинет кандидата */}
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
            <Route path="test" element={<TestPlaceholder />} />
            <Route path="invites" element={<InvitesPlaceholder />} />
          </Route>

          {/* Кабинет работодателя */}
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
            <Route path="needs" element={<NeedsPage />} />
            <Route path="search" element={<SearchPlaceholder />} />
            <Route path="invites" element={<EmployerInvitesPlaceholder />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}