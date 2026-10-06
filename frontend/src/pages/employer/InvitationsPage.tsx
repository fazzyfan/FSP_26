import { useCallback, useEffect, useState } from "react";
import { ApiError, employerApi } from "../../api/client";
import type { CandidateContacts, EmployerInvitation } from "../../api/types";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU");
}

function salaryText(from: number | null, to: number | null): string {
  if (from === null && to === null) return "по договорённости";
  if (from !== null && to !== null && from !== to) return `${from.toLocaleString("ru-RU")} – ${to.toLocaleString("ru-RU")} ₽`;
  return `${(from ?? to ?? 0).toLocaleString("ru-RU")} ₽`;
}

const STATUS: Record<string, string> = {
  pending: "ожидает ответа",
  accepted: "принято",
  declined: "отклонено",
  withdrawn: "отозвано",
};

export function InvitationsPage() {
  const [invites, setInvites] = useState<EmployerInvitation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contactsFor, setContactsFor] = useState<string | null>(null);
  const [contacts, setContacts] = useState<CandidateContacts | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    employerApi
      .listInvitations()
      .then(setInvites)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить приглашения"))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function showContacts(inv: EmployerInvitation) {
    setContactsFor(inv.id);
    setContacts(null);
    setError(null);
    try {
      setContacts(await employerApi.getInvitationContacts(inv.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Контакты недоступны");
    }
  }

  async function withdraw(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await employerApi.withdrawInvitation(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отозвать приглашение");
    } finally {
      setBusyId(null);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;

  return (
    <div className="stack">
      <div className="card">
        <h2>Отправленные приглашения</h2>
        <p className="muted">Контакты кандидата открываются только после принятия приглашения (FR-27).</p>
        {error && <div className="alert alert-error">{error}</div>}
        {invites.length === 0 && <p className="muted">Приглашений пока нет.</p>}
        {invites.map((inv) => (
          <div className="card inner" key={inv.id}>
            <h3>{inv.candidate_name}</h3>
            <p className="muted">{inv.need_title} · {salaryText(inv.salary_from, inv.salary_to)}</p>
            <ul className="plain-list">
              <li>
                Статус: <b>{STATUS[inv.status] ?? inv.status}</b> {inv.responded_at && `(${fmtDate(inv.responded_at)})`}
              </li>
              {inv.message && <li>Сообщение: {inv.message}</li>}
            </ul>

            {inv.status === "accepted" && (
              <div className="row">
                <button className="btn btn-primary" onClick={() => void showContacts(inv)}>
                  Показать контакты
                </button>
              </div>
            )}
            {inv.status === "pending" && (
              <button className="btn btn-outline" disabled={busyId === inv.id} onClick={() => void withdraw(inv.id)}>
                Отозвать
              </button>
            )}

            {contactsFor === inv.id && contacts && (
              <div className="alert alert-info">
                <b>{contacts.full_name}</b>
                <p>Email: {contacts.email}</p>
                {contacts.phone && <p>Телефон: {contacts.phone}</p>}
                {contacts.about && <p className="muted">{contacts.about}</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}