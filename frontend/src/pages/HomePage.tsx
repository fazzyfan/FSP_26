import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const steps = [
  {
    n: "1",
    title: "Кандидат подтверждает компетенции",
    text: "Профиль, опрос о специализации и тест с проверкой на сервере. По результатам присваивается категория (специализация + грейд).",
  },
  {
    n: "2",
    title: "Работодатель описывает потребность",
    text: "Задачи команды, специализация, допустимые грейды и нужный стек. Система показывает подходящие категории и кандидатов с объяснением.",
  },
  {
    n: "3",
    title: "Приглашение с зарплатой",
    text: "Работодатель направляет предложение конкретному кандидату. Контакты открываются только после принятия — приватность по умолчанию.",
  },
];

export function HomePage() {
  const { user } = useAuth();
  return (
    <div className="home">
      <section className="hero">
        <h1>Обратный найм ИТ-специалистов</h1>
        <p className="lead">
          Кандидат подтверждает уровень тестом. Работодатель находит подходящих людей и первым
          отправляет предложение с зарплатой.
        </p>
        {!user && (
          <div className="hero-actions">
            <Link to="/register" className="btn btn-primary">
              Начать как кандидат
            </Link>
            <Link to="/register?role=employer" className="btn btn-outline">
              Начать как работодатель
            </Link>
          </div>
        )}
        {user?.role === "candidate" && (
          <div className="hero-actions">
            <Link to="/candidate/test" className="btn btn-primary">
              Пройти тест
            </Link>
            <Link to="/candidate/invites" className="btn btn-outline">
              Приглашения
            </Link>
          </div>
        )}
        {user?.role === "employer" && (
          <div className="hero-actions">
            <Link to="/employer/search" className="btn btn-primary">
              Подбор кандидатов
            </Link>
            <Link to="/employer/invites" className="btn btn-outline">
              Приглашения
            </Link>
          </div>
        )}
      </section>

      <section className="steps">
        {steps.map((s) => (
          <div className="card step" key={s.n}>
            <div className="step-n">{s.n}</div>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </section>

      <section className="demo-note card">
        <h3>Демонстрационные доступы</h3>
        <p>
          После запуска проекта доступны тестовые аккаунты (пароль <code>DemoPass2026!</code>):
        </p>
        <ul>
          <li>
            <code>candidate@example.com</code> — кабинет кандидата
          </li>
          <li>
            <code>employer@example.com</code> — кабинет работодателя
          </li>
        </ul>
      </section>
    </div>
  );
}