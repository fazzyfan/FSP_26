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