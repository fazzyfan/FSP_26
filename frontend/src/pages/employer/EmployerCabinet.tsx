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
    </>
  );
  return <CabinetLayout title="кабинет работодателя" nav={nav} />;
}