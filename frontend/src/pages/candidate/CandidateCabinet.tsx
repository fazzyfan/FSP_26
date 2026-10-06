import { NavLink } from "react-router-dom";
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