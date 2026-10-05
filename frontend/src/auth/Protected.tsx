import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./AuthContext";
import type { Role } from "../api/types";

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="center-page">Загрузка…</div>;
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={user.role === "candidate" ? "/candidate" : "/employer"} replace />;
  }
  return <>{children}</>;
}

/** Редирект авторизованных на их кабинет. */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="center-page">Загрузка…</div>;
  }
  if (user) {
    return <Navigate to={user.role === "candidate" ? "/candidate" : "/employer"} replace />;
  }
  return <>{children}</>;
}