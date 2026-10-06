import { useEffect, useState, type FormEvent } from "react";
import { ApiError, candidateApi } from "../../api/client";
import type { AssessmentSummary, AttemptResult, TestQuestion } from "../../api/types";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU");
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "ожидает ответа",
    accepted: "принято",
    declined: "отклонено",
    withdrawn: "отозвано",
  };
  return labels[status] ?? status;
}

export function AssessmentPage() {
  const [summary, setSummary] = useState<AssessmentSummary | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [specId, setSpecId] = useState("");
  const [questions, setQuestions] = useState<TestQuestion[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = () =>
    candidateApi
      .getAssessment()
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные"))
      .finally(() => setLoaded(true));

  useEffect(() => {
    void load();
  }, []);

  async function startTest(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const qs = await candidateApi.getTestQuestions(specId);
      setQuestions(qs);
      setAnswers({});
      setResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить тест");
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = Object.entries(answers).map(([question_id, option_id]) => ({ question_id, option_id }));
      const res = await candidateApi.submitTest(specId, payload);
      setResult(res);
      setQuestions(null);
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
  if (questions) {
    const total = questions.length;
    const answered = Object.keys(answers).length;
    return (
      <form className="card form stack" onSubmit={onSubmit}>
        <h2>Тест: подтверждение категории</h2>
        <p className="muted">
          Ответьте на все вопросы — проверка выполняется на сервере. Пороги: Junior ≥ 50%, Middle ≥ 70%.
        </p>
        {questions.map((q, idx) => (
          <fieldset key={q.id} className="question">
            <legend>
              {idx + 1}. {q.text}
            </legend>
            {q.options.map((opt) => (
              <label key={opt.id} className="option">
                <input
                  type="radio"
                  name={q.id}
                  value={opt.id}
                  checked={answers[q.id] === opt.id}
                  onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt.id }))}
                />
                {opt.text}
              </label>
            ))}
          </fieldset>
        ))}
        <p className="muted">
          Отвечено: {answered} из {total}
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="row">
          <button type="button" className="btn btn-outline" onClick={() => setQuestions(null)}>
            Назад
          </button>
          <button className="btn btn-primary" disabled={submitting || answered < total}>
            {submitting ? "Проверяем…" : "Отправить ответы"}
          </button>
        </div>
      </form>
    );
  }

  // --- экран результата после попытки ---
  if (result) {
    return (
      <div className="stack">
        <div className={`card ${result.passed ? "" : ""}`}>
          <h2>Результат теста</h2>
          <p className={result.passed ? "muted" : "muted"}>
            {result.message}
          </p>
          <ul className="plain-list">
            <li>Верных ответов: {result.correct_count} из {result.total_count}</li>
            <li>Результат: {result.score_percent}%</li>
            <li>Статус: {result.passed ? "пройден" : "не пройден"}</li>
            {result.grade_name && <li>Подтверждённый грейд: {result.grade_name}</li>}
            <li>Следующая попытка: {fmtDate(result.next_attempt_at)}</li>
          </ul>
          <button className="btn btn-primary" onClick={() => setResult(null)}>
            К сводке
          </button>
        </div>
      </div>
    );
  }

  const canStart = !!summary && (summary.category !== null || !summary.next_attempt_at);

  return (
    <div className="stack">
      {summary?.category && (
        <div className="card">
          <h2>Подтверждённая категория</h2>
          <p>
            <b>{summary.category.specialization_name}</b> · {summary.category.grade_name}
          </p>
          <p className="muted">Подтверждена {fmtDate(summary.category.confirmed_at)}. Категория открыта работодателям в подборе.</p>
        </div>
      )}

      {summary?.last_attempt && (
        <div className="card">
          <h3>Последняя попытка</h3>
          <ul className="plain-list">
            <li>{summary.last_attempt.specialization_name}: {summary.last_attempt.score_percent}% ({summary.last_attempt.correct_count}/{summary.last_attempt.total_count})</li>
            <li>{statusLabel(summary.last_attempt.status)}</li>
            {summary.last_attempt.grade_name && <li>Грейд: {summary.last_attempt.grade_name}</li>}
          </ul>
        </div>
      )}

      <form className="card form" onSubmit={startTest}>
        <h2>Пройти тест</h2>
        {!canStart && summary?.next_attempt_at && (
          <div className="alert alert-info">Повтор теста доступен с {fmtDate(summary.next_attempt_at)}.</div>
        )}
        {canStart && (
          <>
            <label>
              Специализация
              <select value={specId} onChange={(e) => setSpecId(e.target.value)} required>
                <option value="">— выберите —</option>
                {(summary?.tests ?? []).map((t) => (
                  <option key={t.specialization_id} value={t.specialization_id}>
                    {t.specialization_name} ({t.questions_count} вопросов)
                  </option>
                ))}
              </select>
            </label>
            <p className="muted">
              После успешного теста категория (специализация + грейд) станет подтверждённой и профиль
              попадёт в подбор работодателей.
            </p>
            {error && <div className="alert alert-error">{error}</div>}
            <button className="btn btn-primary" disabled={!specId}>Начать тест</button>
          </>
        )}
      </form>
    </div>
  );
}