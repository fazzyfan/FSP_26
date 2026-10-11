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
  // Ошибки полей формы приглашения: видимая подсветка вместо браузерной валидации
  const [fieldErrors, setFieldErrors] = useState<{ from?: string; to?: string; message?: string }>({});
  // Кандидаты с открытым приглашением компании (status=pending): повторная отправка
  // возможна только после отзыва приглашения во вкладке «Приглашения».
  const [invitedCandidates, setInvitedCandidates] = useState<Set<string>>(new Set());

  const loadInvites = useCallback(() => {
    employerApi
      .listInvitations()
      .then((list) => {
        setInvitedCandidates(
          new Set(list.filter((i) => i.status === "pending").map((i) => i.candidate_id))
        );
      })
      .catch(() => {
        /* подбор остаётся доступным; статусы приглашений не критичны */
      });
  }, []);

  useEffect(() => {
    void loadInvites();
  }, [loadInvites]);

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
    const candidateId = inviteFor;
    const from = Number(salaryFrom);
    const to = Number(salaryTo);
    const fe: { from?: string; to?: string; message?: string } = {};
    if (!salaryFrom || from <= 0) fe.from = "Укажите положительную сумму";
    if (!salaryTo || to <= 0) fe.to = "Укажите положительную сумму";
    if (from > to) fe.to = "Не может быть меньше «от»";
    if (message.trim().length < 10) fe.message = "Не менее 10 символов";
    setFieldErrors(fe);
    if (Object.keys(fe).length > 0) {
      setError("Проверьте выделенные поля формы приглашения.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await employerApi.createInvitation(needId, {
        candidate_id: candidateId,
        salary_from: from,
        salary_to: to,
        message: message.trim(),
      });
      // Кандидат помечается как «приглашение было отправлено» (до отзыва).
      setInvitedCandidates((prev) => new Set(prev).add(candidateId));
      setInviteFor(null);
      setSalaryFrom("");
      setSalaryTo("");
      setMessage("");
      setFieldErrors({});
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
          Показываются все опубликованные кандидаты; прохождение теста указано отдельно.
          Контакты откроются только после принятия приглашения.
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
              <h3>
                {m.full_name}{" "}
                <span className={`badge ${m.test_passed ? "badge-ok" : "badge-muted"}`}>
                  {m.test_passed ? "Прошёл тест" : "Тест не пройден"}
                </span>
              </h3>
              <p className="muted">
                {m.specialization_name || "Категория не подтверждена"}
                {m.grade_name ? ` · ${m.grade_name}` : ""} · стаж {m.experience_months} мес.
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

          {(m.about || m.skills.length > 0) && (
            <div className="resume-summary">
              {m.about && <p>{m.about}</p>}
              {m.skills.length > 0 && <p className="muted">Навыки: {m.skills.join(", ")}</p>}
            </div>
          )}

          {inviteFor === m.candidate_id ? (
            <form className="form inner-form" onSubmit={sendInvitation} noValidate>
              <div className="grid-2">
                <label className={fieldErrors.from ? "invalid" : ""}>
                  Зарплата от, ₽ *
                  <input
                    type="number"
                    min={1}
                    placeholder="120000"
                    value={salaryFrom}
                    onChange={(e) => setSalaryFrom(e.target.value)}
                  />
                  {fieldErrors.from && <span className="field-error">{fieldErrors.from}</span>}
                </label>
                <label className={fieldErrors.to ? "invalid" : ""}>
                  Зарплата до, ₽ *
                  <input
                    type="number"
                    min={1}
                    placeholder="180000"
                    value={salaryTo}
                    onChange={(e) => setSalaryTo(e.target.value)}
                  />
                  {fieldErrors.to && <span className="field-error">{fieldErrors.to}</span>}
                </label>
              </div>
              <label className={fieldErrors.message ? "invalid" : ""}>
                Условия приглашения (обязательно, ≥ 10 символов)
                <textarea
                  rows={2}
                  maxLength={2000}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Задачи, формат работы, бонусы — что предлагает компания"
                />
                {fieldErrors.message && <span className="field-error">{fieldErrors.message}</span>}
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
          ) : invitedCandidates.has(m.candidate_id) ? (
            <button
              className="btn btn-success"
              disabled
              title="Отзовите приглашение во вкладке «Приглашения», чтобы отправить снова"
            >
              ✓ Приглашение было отправлено
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => {
                setFieldErrors({});
                setInviteFor(m.candidate_id);
              }}
            >
              Пригласить
            </button>
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