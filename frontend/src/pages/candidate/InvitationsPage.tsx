import { useCallback, useEffect, useState } from "react";
import { ApiError, candidateApi } from "../../api/client";
import type { CandidateInvitation } from "../../api/types";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

function salaryText(from: number | null, to: number | null): string {
  if (from === null && to === null) return "по договорённости";
  if (from !== null && to !== null && from !== to) return `${from.toLocaleString("ru-RU")} – ${to.toLocaleString("ru-RU")} ₽`;
  return `${(from ?? to ?? 0).toLocaleString("ru-RU")} ₽`;
}

export function InvitationsPage() {
  const [invites, setInvites] = useState<CandidateInvitation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    candidateApi
      .listInvitations()
      .then(setInvites)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить приглашения"))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function respond(id: string, decision: "accept" | "decline") {
    setBusyId(id);
    setError(null);
    try {
      await candidateApi.respondInvitation(id, decision);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обработать приглашение");
    } finally {
      setBusyId(null);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;

  const pending = invites.filter((i) => i.status === "pending");
  const history = invites.filter((i) => i.status !== "pending");

  return (
    <div className="stack">
      <div className="card">
        <h2>Входящие приглашения</h2>
        <p className="muted">
          После принятия работодатель получит ваши контакты. Отказ скрывает профиль от этой компании.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        {pending.length === 0 && <p className="muted">Новых приглашений нет.</p>}
        {pending.map((inv) => (
          <div className="card inner" key={inv.id}>
            <h3>{inv.company_name}</h3>
            <p className="muted">{inv.need_title}</p>
            <ul className="plain-list">
              <li>Зарплатная вилка: {salaryText(inv.salary_from, inv.salary_to)}</li>
              {inv.message && <li>Сообщение: {inv.message}</li>}
            </ul>
            <div className="row">
              <button
                className="btn btn-primary"
                disabled={busyId === inv.id}
                onClick={() => void respond(inv.id, "accept")}
              >
                Принять
              </button>
              <button
                className="btn btn-outline"
                disabled={busyId === inv.id}
                onClick={() => void respond(inv.id, "decline")}
              >
                Отклонить
              </button>
            </div>
          </div>
        ))}
      </div>

      {history.length > 0 && (
        <div className="card">
          <h3>История</h3>
          <ul className="plain-list">
            {history.map((inv) => (
              <li key={inv.id}>
                <b>{inv.company_name}</b> — {inv.need_title} ·{" "}
                <span className="muted">
                  {inv.status === "accepted" ? "принято" : inv.status === "declined" ? "отклонено" : "отозвано"} ·{" "}
                  {fmtDate(inv.responded_at ?? inv.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}