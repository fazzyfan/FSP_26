import type { ReactNode } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function PublicLayout() {
  return (
    <div className="layout">
      <header className="topbar">
        <Link to="/" className="brand">
          ФСП · обратный найм
        </Link>
        <nav className="topnav">
          <Link to="/login">Вход</Link>
          <Link to="/register" className="btn btn-primary btn-sm">
            Регистрация
          </Link>
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
      <footer className="footer">MVP платформы ФСП · демонстрационные данные</footer>
    </div>
  );
}

export function CabinetLayout({ title, nav }: { title: string; nav: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="layout">
      <header className="topbar">
        <Link to="/" className="brand">
          ФСП · {title}
        </Link>
        <nav className="topnav">
          <span className="muted">{user?.email}</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Выйти
          </button>
        </nav>
      </header>
      <div className="cabinet">
        <aside className="sidebar">{nav}</aside>
        <main className="panel">
          <Outlet />
        </main>
      </div>
    </div>
  );
}