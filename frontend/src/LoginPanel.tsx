import { useState } from "react";
import { api } from "./api";
import type { Session } from "./types";

export function LoginPanel({
  onLogin,
}: {
  onLogin: (session: Session) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <main className="session-gate">
      <p className="eyebrow">Integrity · Revisión documental</p>
      <h1>Iniciar sesión</h1>
      <p>Acceso para el equipo autorizado.</p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            await api("/auth/login", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ username, password }),
            });
            setPassword("");
            onLogin(await api<Session>("/session"));
          } catch (e) {
            setError((e as Error).message);
            setPassword("");
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="login-user">Usuario</label>
        <input
          id="login-user"
          autoComplete="username"
          maxLength={80}
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <label htmlFor="login-password">Contraseña</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          maxLength={256}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p role="alert">{error}</p>}
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "Verificando…" : "Ingresar"}
        </button>
      </form>
      <p>
        Solicite al administrador una cuenta o el restablecimiento de su
        contraseña.
      </p>
    </main>
  );
}
