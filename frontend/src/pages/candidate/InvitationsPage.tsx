import { useCallback, useEffect, useState } from "react";
import { ApiError, candidateApi } from "../../api/client";
import type { CandidateInvitation } from "../../api/types";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

function salaryText(from: number, to: number): string {
  if (from === to) return `${from.toLocaleString("ru-RU")} ₽`;
  return `${from.toLocaleString("ru-RU")} – ${to.toLocaleString("ru-RU")} ₽`;
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

  async function revokeContacts(id: string) {
    if (!window.confirm("Отозвать доступ к вашим контактам? Компания больше не увидит их.")) return;
    setBusyId(id);
    setError(null);
    try {
      await candidateApi.revokeContacts(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отозвать доступ");
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
          Принятие приглашения означает согласие открыть контакты именно этой компании.
          Доступ можно отозвать в любой момент. Повторное принятие после отзыва не восстанавливает доступ.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        {pending.length === 0 && <p className="muted">Новых приглашений нет.</p>}
        {pending.map((inv) => (
          <div className="card inner" key={inv.id}>
            <h3>{inv.company_name}</h3>
            <p className="muted">{inv.need_title}</p>
            <ul className="plain-list">
              <li>Зарплатная вилка: {salaryText(inv.salary_from, inv.salary_to)}</li>
              <li>Условия: {inv.message}</li>
              {inv.company_contact_email && <li>Контакт работодателя: {inv.company_contact_email}{inv.company_phone ? `, ${inv.company_phone}` : ""}</li>}
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
                  {inv.status === "accepted"
                    ? inv.contacts_revoked_at
                      ? `принято, доступ к контактам отозван (${fmtDate(inv.contacts_revoked_at)})`
                      : `принято, контакты открыты (${fmtDate(inv.contacts_consented_at ?? inv.responded_at ?? inv.created_at)})`
                    : inv.status === "declined"
                      ? "отклонено"
                      : "отозвано"} · {fmtDate(inv.responded_at ?? inv.created_at)}
                </span>
                {inv.status === "accepted" && !inv.contacts_revoked_at && (
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={busyId === inv.id}
                    onClick={() => void revokeContacts(inv.id)}
                  >
                    Отозвать доступ
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}