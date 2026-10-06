import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, employerApi } from "../../api/client";
import type { EmployerNeed, MatchCandidate } from "../../api/types";

export function MatchesPage() {
  const [needs, setNeeds] = useState<EmployerNeed[]>([]);
  const [needId, setNeedId] = useState("");
  const [matches, setMatches] = useState<MatchCandidate[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // инлайн-форма приглашения: candidate_id -> открыта
  const [inviteFor, setInviteFor] = useState<string | null>(null);
  const [salaryFrom, setSalaryFrom] = useState("");
  const [salaryTo, setSalaryTo] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  const loadNeeds = useCallback(() => {
    employerApi
      .listNeeds()
      .then((list) => {
        setNeeds(list);
        if (list.length > 0 && !needId) setNeedId(list[0].id);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [needId]);

  useEffect(() => {
    void loadNeeds();
  }, [loadNeeds]);

  const loadMatches = useCallback(() => {
    if (!needId) return;
    setMatches(null);
    setError(null);
    employerApi
      .listMatches(needId)
      .then(setMatches)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить подбор"));
  }, [needId]);

  useEffect(() => {
    if (needId) void loadMatches();
  }, [needId, loadMatches]);

  async function sendInvitation(e: FormEvent) {
    e.preventDefault();
    if (!inviteFor) return;
    setSending(true);
    setError(null);
    try {
      await employerApi.createInvitation(needId, {
        candidate_id: inviteFor,
        salary_from: salaryFrom ? Number(salaryFrom) : null,
        salary_to: salaryTo ? Number(salaryTo) : null,
        message: message || null,
      });
      setInviteFor(null);
      setSalaryFrom("");
      setSalaryTo("");
      setMessage("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить приглашение");
    } finally {
      setSending(false);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;
  if (needs.length === 0) {
    return (
      <div className="card">
        <h2>Подбор кандидатов</h2>
        <div className="alert alert-info">
          Сначала создайте рабочую потребность — подбор строится по её специализации, грейдам и навыкам.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="card">
        <h2>Подбор кандидатов</h2>
        <label>
          Потребность
          <select value={needId} onChange={(e) => setNeedId(e.target.value)}>
            {needs.map((n) => (
              <option key={n.id} value={n.id}>{n.title}</option>
            ))}
          </select>
        </label>
        <p className="muted">
          Показаны опубликованные профили с подтверждённой категорией. Контакты откроются только после принятия
          приглашения.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      {matches === null && <div className="card">Загрузка подбора…</div>}
      {matches !== null && matches.length === 0 && (
        <div className="card">
          <p className="muted">
            Нет подходящих кандидатов. Кандидат появится после прохождения теста (подтверждённая категория).
          </p>
        </div>
      )}

      {matches?.map((m) => (
        <div className="card" key={m.candidate_id}>
          <div className="row space-between">
            <div>
              <h3>{m.full_name}</h3>
              <p className="muted">
                {m.specialization_name} · {m.grade_name} · стаж {m.experience_months} мес.
              </p>
            </div>
            <div className="score" title="Балл подбора">Балл: {m.score}</div>
          </div>
          <ul className="plain-list">
            {m.reasons.map((r) => (
              <li key={r}>· {r}</li>
            ))}
          </ul>
          {m.matched_skills.length > 0 && (
            <p className="muted">Совпавшие навыки: {m.matched_skills.join(", ")}</p>
          )}

          {inviteFor !== m.candidate_id ? (
            <button className="btn btn-primary" onClick={() => setInviteFor(m.candidate_id)}>
              Пригласить
            </button>
          ) : (
            <form className="form inner-form" onSubmit={sendInvitation}>
              <div className="grid-2">
                <label>
                  Зарплата от, ₽
                  <input
                    type="number"
                    min={0}
                    value={salaryFrom}
                    onChange={(e) => setSalaryFrom(e.target.value)}
                  />
                </label>
                <label>
                  Зарплата до, ₽
                  <input
                    type="number"
                    min={0}
                    value={salaryTo}
                    onChange={(e) => setSalaryTo(e.target.value)}
                  />
                </label>
              </div>
              <label>
                Сообщение кандидату
                <textarea
                  rows={2}
                  maxLength={2000}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Опишите задачи и условия"
                />
              </label>
              <div className="row">
                <button className="btn btn-primary" disabled={sending}>
                  {sending ? "Отправляем…" : "Отправить приглашение"}
                </button>
                <button type="button" className="btn btn-outline" onClick={() => setInviteFor(null)}>
                  Отмена
                </button>
              </div>
            </form>
          )}
        </div>
      ))}
    </div>
  );
}