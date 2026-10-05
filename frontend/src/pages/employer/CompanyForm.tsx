import { useEffect, useState, type FormEvent } from "react";
import { ApiError, employerApi, referenceApi } from "../../api/client";
import type { ReferenceItem } from "../../api/types";

interface Draft {
  name: string;
  industry_id: string;
  description: string;
  contact_email: string;
  website: string;
  phone: string;
  version: number;
}

const empty: Draft = {
  name: "",
  industry_id: "",
  description: "",
  contact_email: "",
  website: "",
  phone: "",
  version: 1,
};

export function CompanyForm() {
  const [draft, setDraft] = useState<Draft>(empty);
  const [industries, setIndustries] = useState<ReferenceItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([referenceApi.industries(), employerApi.getCompany()])
      .then(([list, company]) => {
        setIndustries(list);
        if (company) {
          setDraft({
            name: company.name,
            industry_id: company.industry_id ?? "",
            description: company.description ?? "",
            contact_email: company.contact_email,
            website: company.website ?? "",
            phone: company.phone ?? "",
            version: company.version,
          });
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
      const saved = await employerApi.saveCompany({
        name: draft.name,
        industry_id: draft.industry_id || null,
        description: draft.description || null,
        contact_email: draft.contact_email,
        website: draft.website || null,
        phone: draft.phone || null,
        version: draft.version,
      });
      setDraft((d) => ({ ...d, version: saved.version }));
      setStatus("Компания сохранена. Потребности и приглашения принадлежат этой компании.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить компанию");
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return <div className="card">Загрузка…</div>;

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h2>Профиль компании</h2>
      <p className="muted">
        Один аккаунт — одна компания (MVP). Без названия и контактного email нельзя отправить
        приглашение.
      </p>

      <label>
        Название организации <span className="muted">(2–200 символов)</span>
        <input value={draft.name} onChange={(e) => patch({ name: e.target.value })} minLength={2} maxLength={200} required />
      </label>

      <label>
        Направление деятельности
        <select value={draft.industry_id} onChange={(e) => patch({ industry_id: e.target.value })}>
          <option value="">— не выбрано —</option>
          {industries.map((i) => (
            <option key={i.id} value={i.id}>{i.name}</option>
          ))}
        </select>
      </label>

      <label>
        Описание <span className="muted">(10–3000 символов, необязательно)</span>
        <textarea value={draft.description} onChange={(e) => patch({ description: e.target.value })} rows={4} minLength={10} maxLength={3000} />
      </label>

      <label>
        Контактный email
        <input type="email" value={draft.contact_email} onChange={(e) => patch({ contact_email: e.target.value })} required />
      </label>

      <label>
        Сайт <span className="muted">(необязательно)</span>
        <input value={draft.website} onChange={(e) => patch({ website: e.target.value })} maxLength={500} />
      </label>

      <label>
        Телефон <span className="muted">(необязательно)</span>
        <input value={draft.phone} onChange={(e) => patch({ phone: e.target.value })} maxLength={32} />
      </label>

      {status && <div className="alert alert-success">{status}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <button className="btn btn-primary" disabled={saving}>
        {saving ? "Сохраняем…" : "Сохранить компанию"}
      </button>
    </form>
  );
}