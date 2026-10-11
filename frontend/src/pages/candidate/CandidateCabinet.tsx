import { NavLink } from "react-router-dom";
import { CabinetLayout } from "../../components/Layout";

export function CandidateCabinet() {
  const nav = (
    <>
      <NavLink to="/candidate/profile" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Профиль и резюме
      </NavLink>
    </>
  );
  return <CabinetLayout title="кабинет кандидата" nav={nav} />;
}