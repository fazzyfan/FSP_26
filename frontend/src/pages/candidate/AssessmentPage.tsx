import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, candidateApi } from "../../api/client";
import type { AssessmentSummary, AttemptResult, AttemptState } from "../../api/types";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU");
}

function fmtDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function AssessmentPage() {
  const [summary, setSummary] = useState<AssessmentSummary | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [specId, setSpecId] = useState("");
  const [grade, setGrade] = useState<"junior" | "middle">("junior");

  const [attempt, setAttempt] = useState<AttemptState | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [remaining, setRemaining] = useState(0);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const answersRef = useRef<Record<string, string>>({});
  answersRef.current = answers;
  // Версия ответов на сервере (NFR-06): устаревший запрос не затирает свежий выбор
  const versionRef = useRef<number>(0);

  const load = useCallback(() => {
    candidateApi
      .getAssessment()
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные"))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Восстановление активной попытки после перезагрузки (FR-09, MVP)
  useEffect(() => {
    if (summary?.active_attempt && !attempt && !result) {
      candidateApi
        .getAttempt(summary.active_attempt.attempt_id)
        .then((st) => {
          setAttempt(st);
          setRemaining(st.remaining_seconds);
          versionRef.current = st.answers_version;
          setAnswers(Object.fromEntries(st.answers.map((a) => [a.question_id, a.option_id])));
        })
        .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось восстановить попытку"));
    }
  }, [summary, attempt, result]);

  // Таймер попытки (серверный лимит 20 минут)
  useEffect(() => {
    if (!attempt) return;
    const tick = () => {
      const left = Math.max(0, Math.floor((new Date(attempt.expires_at).getTime() - Date.now()) / 1000));
      setRemaining(left);
      if (left === 0) {
        setAttempt(null);
        setResult(null);
        void load();
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [attempt, load]);

  async function startTest(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const st = await candidateApi.startTest(specId, grade);
      setAttempt(st);
      setRemaining(st.remaining_seconds);
      versionRef.current = st.answers_version;
      setAnswers(Object.fromEntries(st.answers.map((a) => [a.question_id, a.option_id])));
      setResult(null);
    } catch (err) {
      const problem = err instanceof ApiError ? err.problem : null;
      if (problem?.extra?.next_allowed_at) {
        setError(`Тест недоступен. ${problem.detail ?? ""} Доступно с ${fmtDate(String(problem.extra.next_allowed_at))}.`);
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось начать тест");
      }
    }
  }

  function pickAnswer(questionId: string, optionId: string) {
    const next = { ...answersRef.current, [questionId]: optionId };
    setAnswers(next);
    setSaveError(null);
    if (!attempt) return;
    // Автосохранение на сервере по мере выбора (перезагрузка не теряет ответы).
    // Ошибки не игнорируются: устаревшая версия (409) — состояние перечитывается,
    // остальные сбои показываются, чтобы пользователь не потерял ответы молча.
    candidateApi
      .saveAttemptAnswers(
        attempt.attempt_id,
        Object.entries(next).map(([q, o]) => ({ question_id: q, option_id: o })),
        versionRef.current,
      )
      .then((st) => {
        versionRef.current = st.answers_version;
      })
      .catch((err) => {
        const problem = err instanceof ApiError ? err.problem : null;
        if (err instanceof ApiError && (err.status === 409 || problem?.code === "CONFLICT")) {
          setSaveError("Ответы изменились в другом окне — состояние обновлено.");
          candidateApi
            .getAttempt(attempt.attempt_id)
            .then((st) => {
              setAttempt(st);
              versionRef.current = st.answers_version;
              setAnswers(Object.fromEntries(st.answers.map((a) => [a.question_id, a.option_id])));
            })
            .catch(() => undefined);
        } else {
          setSaveError(
            err instanceof ApiError
              ? `Автосохранение не удалось: ${err.message}`
              : "Автосохранение не удалось. Проверьте соединение.",
          );
        }
      });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!attempt) return;
    setSubmitting(true);
    setError(null);
    try {
      // Сначала сохраняем последние ответы, затем отправляем (безопасный повтор)
      const saved = await candidateApi.saveAttemptAnswers(
        attempt.attempt_id,
        Object.entries(answersRef.current).map(([q, o]) => ({ question_id: q, option_id: o })),
        versionRef.current,
      );
      versionRef.current = saved.answers_version;
      const res = await candidateApi.submitAttempt(attempt.attempt_id);
      setResult(res);
      setAttempt(null);
      setSummary(await candidateApi.getAssessment());
    } catch (err) {
      const problem = err instanceof ApiError ? err.problem : null;
      if (problem?.code === "INVALID_STATE" && problem.extra?.next_allowed_at) {
        setError(`Повтор теста доступен с ${fmtDate(String(problem.extra.next_allowed_at))}.`);
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось отправить тест");
      }
      setSummary(await candidateApi.getAssessment().catch(() => summary));
    } finally {
      setSubmitting(false);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;

  // --- экран прохождения теста ---
  if (attempt) {
    const total = attempt.questions.length;
    const answered = Object.keys(answers).length;
    const blocks = [1, 2, 3];
    return (
      <form className="card form stack" onSubmit={onSubmit}>
        <div className="row space-between">
          <h2>Тест: {attempt.specialization_name} · {attempt.grade_name}</h2>
          <div className={`score ${remaining < 120 ? "score-danger" : ""}`} title="Оставшееся время">
            ⏱ {fmtDuration(remaining)}
          </div>
        </div>
        <p className="muted">
          Подтверждение категории: ≥ 70% суммарно и ≥ 50% в каждом блоке (3 блока по 2 задания).
          Ответы сохраняются автоматически — после перезагрузки страницы вы продолжите с того же места.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        {saveError && <div className="alert alert-error">{saveError}</div>}
        {blocks.map((b) => (
          <fieldset key={b} className="block">
            <legend>Блок {b}</legend>
            {attempt.questions
              .filter((q) => q.block === b)
              .map((q) => (
                <fieldset key={q.id} className="question">
                  <legend>
                    {q.text}
                  </legend>
                  {q.options.map((opt) => (
                    <label key={opt.id} className="option">
                      <input
                        type="radio"
                        name={q.id}
                        value={opt.id}
                        checked={answers[q.id] === opt.id}
                        onChange={() => pickAnswer(q.id, opt.id)}
                      />
                      {opt.text}
                    </label>
                  ))}
                </fieldset>
              ))}
          </fieldset>
        ))}
        <p className="muted">
          Отвечено: {answered} из {total}
        </p>
        <div className="row">
          <button type="button" className="btn btn-outline" onClick={() => setAttempt(null)}>
            Назад
          </button>
          <button className="btn btn-primary" disabled={submitting || answered < total}>
            {submitting ? "Проверяем…" : "Отправить ответы"}
          </button>
        </div>
      </form>
    );
  }

  // --- экран результата ---
  if (result) {
    return (
      <div className="card stack">
        <h2>Результат теста</h2>
        <p className={result.passed ? "ok-text" : "muted"}>{result.message}</p>
        <ul className="plain-list">
          <li>Верных ответов: {result.correct_count} из {result.total_count} ({result.score_percent}%)</li>
          {result.block_results.map((b) => (
            <li key={b.block}>Блок {b.block}: {b.correct} из {b.total}</li>
          ))}
          {result.grade_name && <li>Подтверждённая категория: {result.grade_name}</li>}
          {result.next_attempt_at && <li>Следующая попытка этой категории: {fmtDate(result.next_attempt_at)}</li>}
        </ul>
        <div className="row">
          <button className="btn btn-primary" onClick={() => { setResult(null); void load(); }}>
            К сводке
          </button>
        </div>
      </div>
    );
  }

  // --- сводка и старт ---
  const canStart = !!summary && (summary.category !== null || !summary.next_attempt_at);

  return (
    <div className="stack">
      {summary?.category && (
        <div className="card">
          <h2>Подтверждённая категория</h2>
          <p>
            <b>{summary.category.specialization_name}</b> · {summary.category.grade_name}
          </p>
          <p className="muted">
            Подтверждена {fmtDate(summary.category.confirmed_at)}. Смена категории доступна через 90 дней.
          </p>
        </div>
      )}

      {summary?.last_attempt && (
        <div className="card">
          <h3>Последняя попытка</h3>
          <ul className="plain-list">
            <li>
              {summary.last_attempt.specialization_name} · {summary.last_attempt.grade_name ?? "—"}:{" "}
              {summary.last_attempt.score_percent}% ({summary.last_attempt.correct_count}/{summary.last_attempt.total_count})
            </li>
            <li>{summary.last_attempt.passed ? "пройдена" : "не пройдена"}</li>
            {summary.last_attempt.next_attempt_at && (
              <li>Пересдача этой категории с {fmtDate(summary.last_attempt.next_attempt_at)}</li>
            )}
          </ul>
        </div>
      )}

      <form className="card form" onSubmit={startTest}>
        <h2>Пройти тест</h2>
        {!canStart && summary?.next_attempt_at && (
          <div className="alert alert-info">Повтор теста доступен с {fmtDate(summary.next_attempt_at)}.</div>
        )}
        {summary?.active_attempt && (
          <div className="alert alert-info">
            У вас есть активная попытка — она будет продолжена автоматически.
          </div>
        )}
        {canStart && (
          <>
            <label>
              Специализация
              <select value={specId} onChange={(e) => setSpecId(e.target.value)} required>
                <option value="">— выберите —</option>
                {(summary?.tests ?? []).map((t) => (
                  <option key={t.specialization_id} value={t.specialization_id}>
                    {t.specialization_name} ({t.questions_count} заданий)
                  </option>
                ))}
              </select>
            </label>
            <label>
              Грейд (категория)
              <select value={grade} onChange={(e) => setGrade(e.target.value as "junior" | "middle")}>
                {(summary?.tests ?? [])
                  .find((t) => t.specialization_id === specId)
                  ?.grades.map((g) => (
                    <option key={g.grade_code} value={g.grade_code}>
                      {g.grade_name} ({g.questions_count} заданий)
                    </option>
                  )) ?? (
                  <>
                    <option value="junior">Junior</option>
                    <option value="middle">Middle</option>
                  </>
                )}
              </select>
            </label>
            <p className="muted">
              Категория подтверждается при ≥ 70% суммарно и ≥ 50% в каждом блоке. Пересдача той же
              категории — через 24 часа; смена подтверждённой — через 90 дней. На тест даётся 20 минут.
            </p>
            {error && <div className="alert alert-error">{error}</div>}
            <button className="btn btn-primary" disabled={!specId}>Начать тест</button>
          </>
        )}
      </form>
    </div>
  );
}