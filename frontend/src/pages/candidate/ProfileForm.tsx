import { useEffect, useState, type FormEvent } from "react";
import { ApiError, candidateApi, referenceApi } from "../../api/client";
import type { CandidateProfile, ReferenceItem } from "../../api/types";

interface Draft {
  full_name: string;
  phone: string;
  experience_months: number;
  role_ids: string[];
  skill_ids: string[];
  claimed_level_id: string;
  soft_skills: string;
  about: string;
  is_published: boolean;
  show_fsp: boolean;
  fsp_member_id: string;
  version: number;
}

const empty: Draft = {
  full_name: "",
  phone: "",
  experience_months: 0,
  role_ids: [],
  skill_ids: [],
  claimed_level_id: "",
  soft_skills: "",
  about: "",
  is_published: false,
  show_fsp: false,
  fsp_member_id: "",
  version: 1,
};

function toDraft(p: CandidateProfile): Draft {
  return {
    full_name: p.full_name,
    phone: p.phone ?? "",
    experience_months: p.experience_months,
    role_ids: [],
    skill_ids: [],
    claimed_level_id: p.claimed_level_code ?? "",
    soft_skills: (p.soft_skills ?? []).join(", "),
    about: p.about ?? "",
    is_published: p.is_published,
    show_fsp: p.show_fsp,
    fsp_member_id: p.fsp_member_id ?? "",
    version: p.version,
  };
}

export function ProfileForm() {
  const [draft, setDraft] = useState<Draft>(empty);
  const [grades, setGrades] = useState<ReferenceItem[]>([]);
  const [roles, setRoles] = useState<ReferenceItem[]>([]);
  const [skills, setSkills] = useState<ReferenceItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([referenceApi.grades(), referenceApi.roles(), referenceApi.skills(), candidateApi.getProfile()])
      .then(([g, r, s, profile]) => {
        setGrades(g);
        setRoles(r);
        setSkills(s);
        if (profile) {
          const d = toDraft(profile);
          // маппим коды грейда/ролей/скиллов на ID через справочники
          d.claimed_level_id = g.find((x) => x.code === profile.claimed_level_code)?.id ?? "";
          d.role_ids = profile.roles
            .map((name) => r.find((x) => x.name === name)?.id)
            .filter((x): x is string => Boolean(x));
          d.skill_ids = profile.skills
            .map((name) => s.find((x) => x.name === name)?.id)
            .filter((x): x is string => Boolean(x));
          setDraft(d);
        }
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  function patch(p: Partial<Draft>) {
    setDraft((d) => ({ ...d, ...p }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    setError(null);
    try {
      const saved = await candidateApi.saveProfile({
        full_name: draft.full_name,
        phone: draft.phone || null,
        experience_months: draft.experience_months,
        role_ids: draft.role_ids,
        skill_ids: draft.skill_ids,
        claimed_level_id: draft.claimed_level_id || null,
        soft_skills: draft.soft_skills.split(",").map((s) => s.trim()).filter(Boolean),
        about: draft.about || null,
        is_published: draft.is_published,
        show_fsp: draft.show_fsp,
        fsp_member_id: draft.fsp_member_id || null,
        version: draft.version,
      });
      setDraft((d) => ({ ...d, version: saved.version }));
      setStatus("Профиль сохранён. Заявленные навыки отмечены как непроверенные.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.status === 409) setStatus(null);
      } else {
        setError("Не удалось сохранить профиль");
      }
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h2>Профиль кандидата</h2>
      <p className="muted">
        Обязательные поля: ФИО, хотя бы одна роль и один навык. Стаж может быть нулевым.
      </p>

      <label>
        ФИО <span className="muted">(2–150 символов)</span>
        <input value={draft.full_name} onChange={(e) => patch({ full_name: e.target.value })} required />
      </label>

      <label>
        Телефон <span className="muted">(необязательно)</span>
        <input value={draft.phone} onChange={(e) => patch({ phone: e.target.value })} maxLength={32} />
      </label>

      <label>
        Стаж, месяцев <span className="muted">(0–720)</span>
        <input
          type="number"
          min={0}
          max={720}
          value={draft.experience_months}
          onChange={(e) => patch({ experience_months: Number(e.target.value) })}
        />
      </label>

      <label>
        Желаемые роли
        <select multiple value={draft.role_ids} onChange={(e) => patch({ role_ids: [...e.target.selectedOptions].map((o) => o.value) })}>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </label>

      <label>
        Навыки
        <select multiple value={draft.skill_ids} onChange={(e) => patch({ skill_ids: [...e.target.selectedOptions].map((o) => o.value) })}>
          {skills.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </label>

      <label>
        Заявленный уровень <span className="muted">(самооценка; категорию даёт тест)</span>
        <select value={draft.claimed_level_id} onChange={(e) => patch({ claimed_level_id: e.target.value })}>
          <option value="">Не определён</option>
          {grades.map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
      </label>

      <label>
        Софт-скиллы <span className="muted">(через запятую, необязательно)</span>
        <input value={draft.soft_skills} onChange={(e) => patch({ soft_skills: e.target.value })} />
      </label>

      <label>
        О себе и опыт <span className="muted">(до 3000 символов, необязательно)</span>
        <textarea value={draft.about} onChange={(e) => patch({ about: e.target.value })} rows={4} maxLength={3000} />
      </label>

      <label>
        ID участника ФСП <span className="muted">(необязательно; демонстрационная связь)</span>
        <input value={draft.fsp_member_id} onChange={(e) => patch({ fsp_member_id: e.target.value })} maxLength={64} />
      </label>

      <label className="checkbox-row">
        <input type="checkbox" checked={draft.is_published} onChange={(e) => patch({ is_published: e.target.checked })} />
        <span>Публиковать профиль в каталоге (FR-04: по умолчанию выключено)</span>
      </label>
      <label className="checkbox-row">
        <input type="checkbox" checked={draft.show_fsp} onChange={(e) => patch({ show_fsp: e.target.checked })} />
        <span>Показывать достижения ФСП работодателям (при наличии)</span>
      </label>

      {status && <div className="alert alert-success">{status}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <button className="btn btn-primary" disabled={saving}>
        {saving ? "Сохраняем…" : "Сохранить профиль"}
      </button>
    </form>
  );
}