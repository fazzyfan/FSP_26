import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const session = await login(email, password);
      navigate(session.role === "candidate" ? "/candidate" : "/employer", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выполнить вход");
      if (err instanceof ApiError && err.problem.code === "EMAIL_UNCONFIRMED") {
        navigate("/confirm-email/pending", { state: { email }, replace: true });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h2>Вход</h2>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {error && <div className="alert alert-error">{error}</div>}
        <button className="btn btn-primary" disabled={pending}>
          {pending ? "Входим…" : "Войти"}
        </button>
        <p className="muted">
          Нет аккаунта? <Link to="/register">Зарегистрируйтесь</Link>
          {from && from !== "/login" && (
            <>
              {" "}· <Link to={from}>вернуться</Link>
            </>
          )}
        </p>
      </form>
    </div>
  );
}