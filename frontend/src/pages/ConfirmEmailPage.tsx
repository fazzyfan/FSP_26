import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, authApi } from "../api/client";

/**
 * Страница обработки ссылки из письма (FR-02): /confirm-email?token=...
 */
export function ConfirmEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [message, setMessage] = useState("Подтверждаем адрес…");

  useEffect(() => {
    if (!token) {
      setState("error");
      setMessage("Ссылка подтверждения не содержит токена.");
      return;
    }
    authApi
      .confirmEmail(token)
      .then(() => {
        setState("ok");
        setMessage("Адрес подтверждён. Теперь можно войти.");
      })
      .catch((err: unknown) => {
        setState("error");
        setMessage(err instanceof ApiError ? err.message : "Не удалось подтвердить адрес");
      });
  }, [token]);

  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h2>Подтверждение email</h2>
        <p>{message}</p>
        {state === "ok" && (
          <Link to="/login" className="btn btn-primary">
            Войти
          </Link>
        )}
        {state === "error" && (
          <Link to="/login" className="btn btn-outline">
            На страницу входа
          </Link>
        )}
      </div>
    </div>
  );
}

/** Промежуточная страница «проверьте почту» при попытке входа до подтверждения. */
export function PendingEmailPage() {
  const [search] = useSearchParams();
  const email = (search.get("email") ?? "").split(" ")[0];
  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h2>Email ещё не подтверждён</h2>
        <p>Найдите письмо от платформы ФСП и перейдите по ссылке из него.</p>
        {email && (
          <p>
            Письмо выслано на <b>{email}</b>.{" "}
            <button
              className="link-like"
              onClick={async () => {
                try {
                  await authApi.resendConfirmation(email);
                } catch {
                  /* повтор доступен через 60 секунд */
                }
              }}
            >
              Отправить ещё раз
            </button>
          </p>
        )}
        <Link to="/login" className="btn btn-outline">
          Назад
        </Link>
      </div>
    </div>
  );
}