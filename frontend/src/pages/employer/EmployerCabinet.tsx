import { NavLink } from "react-router-dom";
import { CabinetLayout } from "../../components/Layout";

export function EmployerCabinet() {
  const nav = (
    <>
      <NavLink to="/employer/company" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Компания
      </NavLink>
      <NavLink to="/employer/needs" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Потребности
      </NavLink>
      <NavLink to="/employer/search" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Подбор кандидатов
      </NavLink>
      <NavLink to="/employer/invites" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Приглашения
      </NavLink>
    </>
  );
  return <CabinetLayout title="кабинет работодателя" nav={nav} />;
}

/** Заготовка: каталог и подбор (FR-18..FR-22) — этап 2/3. */
export function SearchPlaceholder() {
  return (
    <div className="card">
      <h2>Подбор кандидатов</h2>
      <p>
        Здесь появятся рекомендованные категории и кандидаты с объяснением подбора, фильтры по
        специализации, грейду и стеку, а также кнопка отправки приглашения (этап 2).
      </p>
      <div className="alert alert-info">
        Видны только опубликованные профили с подтверждённой категорией.
      </div>
    </div>
  );
}

/** Заготовка: исходящие приглашения (FR-24..FR-27) — этап 2/3. */
export function EmployerInvitesPlaceholder() {
  return (
    <div className="card">
      <h2>Отправленные приглашения</h2>
      <p>Здесь будут статусы предложений: отправлено, просмотрено, принято, отклонено.</p>
    </div>
  );
}