import { Link, NavLink } from "react-router-dom";
import { CabinetLayout } from "../../components/Layout";

export function CandidateCabinet() {
  const nav = (
    <>
      <NavLink to="/candidate/profile" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Профиль и резюме
      </NavLink>
      <NavLink to="/candidate/test" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Опрос и тест
      </NavLink>
      <NavLink to="/candidate/invites" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Приглашения
      </NavLink>
    </>
  );
  return <CabinetLayout title="кабинет кандидата" nav={nav} />;
}

/** Заготовка: опрос и тестирование появятся на этапе 2 (FR-07..FR-13). */
export function TestPlaceholder() {
  return (
    <div className="card">
      <h2>Опрос и тест</h2>
      <p>
        Здесь будет выбор специализации и предполагаемого грейда, затем тест с проверкой на
        сервере и подтверждённая категория (этап 2).
      </p>
      <div className="alert alert-info">
        До первого успешного теста профиль не включается в каталог для работодателей.
      </div>
    </div>
  );
}

/** Заготовка: входящие приглашения (FR-23..FR-27) — этап 2/3. */
export function InvitesPlaceholder() {
  return (
    <div className="card">
      <h2>Входящие приглашения</h2>
      <p>
        Здесь появятся предложения от работодателей: компания, условия, зарплатная вилка и
        кнопки «Принять» / «Отклонить». Контакты открываются только после принятия.
      </p>
      <Link to="/candidate/profile" className="btn btn-outline btn-sm">
        Заполнить профиль
      </Link>
    </div>
  );
}