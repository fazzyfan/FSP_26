import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, employerApi } from "../../api/client";
import type { EmployerNeed, MatchCandidate, MatchPage } from "../../api/types";

export function MatchesPage() {
  const [needs, setNeeds] = useState<EmployerNeed[]>([]);
  const [needId, setNeedId] = useState("");
  const [pageData, setPageData] = useState<MatchPage | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // фильтры и пагинация
  const [gradeFilter, setGradeFilter] = useState("");
  const [minScore, setMinScore] = useState("");
  const [page, setPage] = useState(1);

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
    setPageData(null);
    setError(null);
    employerApi
      .listMatches(needId, {
        page,
        page_size: 10,
        grade: gradeFilter || null,
        min_score: minScore ? Number(minScore) : undefined,
      })
      .then(setPageData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить подбор"));
  }, [needId, page, gradeFilter, minScore]);

  useEffect(() => {
    if (needId) void loadMatches();
  }, [needId, loadMatches]);

  async function sendInvitation(e: FormEvent) {
    e.preventDefault();
    if (!inviteFor) return;
    const from = Number(salaryFrom);
    const to = Number(salaryTo);
    if (!salaryFrom || !salaryTo || from <= 0 || to <= 0) {
      setError("Укажите положительную зарплатную вилку (от и до).");
      return;
    }
    if (from > to) {
      setError("Нижняя граница вилки не может превышать верхнюю.");
      return;
    }
    if (message.trim().length < 10) {
      setError("Опишите условия приглашения (не менее 10 символов).");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await employerApi.createInvitation(needId, {
        candidate_id: inviteFor,
        salary_from: from,
        salary_to: to,
        message: message.trim(),
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

  function resetFilters() {
    setGradeFilter("");
    setMinScore("");
    setPage(1);
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

  const matches: MatchCandidate[] = pageData?.items ?? [];

  return (
    <div className="stack">
      <div className="card">
        <h2>Подбор кандидатов</h2>
        <label>
          Потребность
          <select
            value={needId}
            onChange={(e) => {
              setNeedId(e.target.value);
              setPage(1);
            }}
          >
            {needs.map((n) => (
              <option key={n.id} value={n.id}>{n.title}</option>
            ))}
          </select>
        </label>
        <div className="grid-2">
          <label>
            Грейд
            <select value={gradeFilter} onChange={(e) => { setGradeFilter(e.target.value); setPage(1); }}>
              <option value="">Все допустимые</option>
              <option value="junior">Junior</option>
              <option value="middle">Middle</option>
            </select>
          </label>
          <label>
            Минимальный балл
            <input
              type="number"
              min={0}
              max={100}
              placeholder="0"
              value={minScore}
              onChange={(e) => { setMinScore(e.target.value); setPage(1); }}
            />
          </label>
        </div>
        <p className="muted">
          Балл подбора: 60% — компетенции, 30% — результат теста, 10% — достижения ФСП.
          Неподходящие специализации и грейды исключены. Контакты откроются только после принятия приглашения.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      {pageData === null && <div className="card">Загрузка подбора…</div>}
      {pageData !== null && pageData.total === 0 && (
        <div className="card">
          <p className="muted">
            Нет подходящих кандидатов. {gradeFilter || minScore ? "Попробуйте смягчить фильтры." : "Кандидат появится после прохождения теста (подтверждённая категория)."}
          </p>
          {(gradeFilter || minScore) && (
            <button className="btn btn-outline" onClick={resetFilters}>Сбросить фильтры</button>
          )}
        </div>
      )}

      {matches.map((m) => (
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
          <p className="muted">
            Разбивка: компетенции {m.score_breakdown.competencies} · тест {m.score_breakdown.test} ·
            ФСП {m.score_breakdown.fsp}
          </p>
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
                  Зарплата от, ₽ *
                  <input
                    type="number"
                    min={1}
                    required
                    placeholder="120000"
                    value={salaryFrom}
                    onChange={(e) => setSalaryFrom(e.target.value)}
                  />
                </label>
                <label>
                  Зарплата до, ₽ *
                  <input
                    type="number"
                    min={1}
                    required
                    placeholder="180000"
                    value={salaryTo}
                    onChange={(e) => setSalaryTo(e.target.value)}
                  />
                </label>
              </div>
              <label>
                Условия приглашения (обязательно, ≥ 10 символов)
                <textarea
                  rows={2}
                  maxLength={2000}
                  required
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Задачи, формат работы, бонусы — что предлагает компания"
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

      {pageData && pageData.pages > 1 && (
        <div className="row">
          <button className="btn btn-outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ← Назад
          </button>
          <span className="muted">
            Страница {page} из {pageData.pages} · всего {pageData.total}
          </span>
          <button
            className="btn btn-outline"
            disabled={page >= pageData.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Вперёд →
          </button>
        </div>
      )}
    </div>
  );
}