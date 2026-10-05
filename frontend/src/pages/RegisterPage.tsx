import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, authApi, referenceApi } from "../api/client";
import type { ConsentDoc, Role } from "../api/types";

export function RegisterPage() {
  const [params] = useSearchParams();
  const initialRole: Role = params.get("role") === "employer" ? "employer" : "candidate";

  const [role, setRole] = useState<Role>(initialRole);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consents, setConsents] = useState<ConsentDoc[]>([]);
  const [consentVersion, setConsentVersion] = useState("");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    referenceApi
      .consents()
      .then((list) => {
        const latest = list.filter((c) => c.code === "data_processing")[0];
        setConsents(list);
        if (latest) setConsentVersion(latest.version);
      })
      .catch(() => undefined);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      await authApi.register({
        email,
        password,
        role,
        consent_version: consentVersion,
        consent_granted: agree,
      });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        const fe: Record<string, string> = {};
        for (const f of err.problem.errors ?? []) fe[f.field] = f.message;
        setFieldErrors(fe);
      } else {
        setError("Не удалось зарегистрироваться");
      }
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <div className="auth-wrap">
        <div className="card auth-card">
          <h2>Проверьте почту</h2>
          <p>
            На <b>{email}</b> отправлена ссылка подтверждения (действует 24 часа). Без
            подтверждения адреса войти нельзя.
          </p>
          <p className="muted">
            Не пришло письмо?{" "}
            <button
              className="link-like"
              onClick={async () => {
                try {
                  await authApi.resendConfirmation(email);
                  setError("Новое письмо отправлено.");
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : "Повторите позже");
                }
              }}
            >
              Отправить ещё раз
            </button>
          </p>
          {error && <div className="alert alert-info">{error}</div>}
          <Link to="/login" className="btn btn-outline">
            На страницу входа
          </Link>
        </div>
      </div>
    );
  }

  const consent = consents.find((c) => c.code === "data_processing");

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h2>Регистрация</h2>

        <label>Роль</label>
        <div className="segmented">
          <button
            type="button"
            className={role === "candidate" ? "seg active" : "seg"}
            onClick={() => setRole("candidate")}
          >
            Кандидат
          </button>
          <button
            type="button"
            className={role === "employer" ? "seg active" : "seg"}
            onClick={() => setRole("employer")}
          >
            Работодатель
          </button>
        </div>

        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          {fieldErrors.email && <span className="field-error">{fieldErrors.email}</span>}
        </label>

        <label>
          Пароль <span className="muted">(12–128 символов)</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={12}
            maxLength={128}
            required
            autoComplete="new-password"
          />
          {fieldErrors.password && <span className="field-error">{fieldErrors.password}</span>}
        </label>

        {consent && (
          <label className="checkbox-row">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} required />
            <span>
              Я согласен на обработку персональных данных (версия {consent.version})
            </span>
          </label>
        )}
        {consent && <details className="consent-text"><summary>Текст согласия</summary><p>{consent.text}</p></details>}

        {error && !consent && <div className="alert alert-error">{error}</div>}
        {error && consent && <div className="alert alert-error">{error}</div>}

        <button className="btn btn-primary" disabled={pending || !consentVersion}>
          {pending ? "Создаём аккаунт…" : "Зарегистрироваться"}
        </button>
        <p className="muted">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </form>
    </div>
  );
}