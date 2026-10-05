import { useEffect, useState, type FormEvent } from "react";
import { ApiError, employerApi, referenceApi } from "../../api/client";
import type { EmployerNeed, ReferenceItem } from "../../api/types";

export function NeedsPage() {
  const [needs, setNeeds] = useState<EmployerNeed[]>([]);
  const [industries, setIndustries] = useState<ReferenceItem[]>([]);
  const [specializations, setSpecializations] = useState<ReferenceItem[]>([]);
  const [grades, setGrades] = useState<ReferenceItem[]>([]);
  const [skills, setSkills] = useState<ReferenceItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [companyMissing, setCompanyMissing] = useState(false);

  const [title, setTitle] = useState("");
  const [tasks, setTasks] = useState("");
  const [industryId, setIndustryId] = useState("");
  const [specializationId, setSpecializationId] = useState("");
  const [gradeIds, setGradeIds] = useState<string[]>([]);
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    Promise.all([
      referenceApi.industries(),
      referenceApi.specializations(),
      referenceApi.grades(),
      referenceApi.skills(),
      employerApi.listNeeds(),
      employerApi.getCompany(),
    ])
      .then(([ind, spec, gr, sk, list, company]) => {
        setIndustries(ind);
        setSpecializations(spec);
        setGrades(gr);
        setSkills(sk);
        setNeeds(list);
        setCompanyMissing(!company);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  };

  useEffect(load, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const need = await employerApi.createNeed({
        title,
        tasks_text: tasks,
        industry_id: industryId || null,
        specialization_id: specializationId || null,
        grade_ids: gradeIds,
        skill_ids: skillIds,
      });
      setNeeds((list) => [need, ...list]);
      setTitle("");
      setTasks("");
      setGradeIds([]);
      setSkillIds([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать потребность");
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;
  if (companyMissing) {
    return (
      <div className="card">
        <h2>Потребности</h2>
        <div className="alert alert-info">
          Сначала заполните профиль компании — потребности создаются от её имени.
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <form className="card form" onSubmit={onSubmit}>
        <h2>Новая потребность</h2>
        <p className="muted">
          Потребность — внутренний объект для подбора; как вакансия не публикуется (FR-17).
        </p>

        <label>
          Название роли <span className="muted">(3–150 символов)</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} maxLength={150} required />
        </label>

        <label>
          Задачи команды <span className="muted">(20–3000 символов)</span>
          <textarea value={tasks} onChange={(e) => setTasks(e.target.value)} rows={4} minLength={20} maxLength={3000} required />
        </label>

        <div className="grid-2">
          <label>
            Отрасль
            <select value={industryId} onChange={(e) => setIndustryId(e.target.value)}>
              <option value="">— не выбрано —</option>
              {industries.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </label>
          <label>
            Специализация
            <select value={specializationId} onChange={(e) => setSpecializationId(e.target.value)}>
              <option value="">— не выбрано —</option>
              {specializations.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </label>
        </div>

        <label>
          Допустимые грейды <span className="muted">(хотя бы один)</span>
          <select multiple value={gradeIds} onChange={(e) => setGradeIds([...e.target.selectedOptions].map((o) => o.value))}>
            {grades.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </label>

        <label>
          Нужные навыки <span className="muted">(хотя бы один)</span>
          <select multiple value={skillIds} onChange={(e) => setSkillIds([...e.target.selectedOptions].map((o) => o.value))}>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>

        {error && <div className="alert alert-error">{error}</div>}
        <button className="btn btn-primary" disabled={saving}>
          {saving ? "Сохраняем…" : "Создать потребность"}
        </button>
      </form>

      <div className="card">
        <h3>Сохранённые потребности</h3>
        {needs.length === 0 && <p className="muted">Потребностей пока нет.</p>}
        <ul className="plain-list">
          {needs.map((n) => (
            <li key={n.id}>
              <b>{n.title}</b>
              <p className="muted">{n.tasks_text.slice(0, 160)}…</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}