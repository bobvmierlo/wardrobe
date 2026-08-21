import { useState } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inloggen mislukt");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand">
          <div className="logo">👕</div>
          <h1>Kledingkast</h1>
          <div className="muted">Log in om verder te gaan</div>
        </div>
        <form onSubmit={submit} className="stack">
          {error && <div className="error">{error}</div>}
          <div className="field">
            <label>Gebruikersnaam</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoCapitalize="none"
              autoComplete="username"
              autoCorrect="off"
              required
            />
          </div>
          <div className="field">
            <label>Wachtwoord</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button className="btn-primary btn-block" disabled={busy}>
            {busy ? "Bezig…" : "Inloggen"}
          </button>
        </form>
      </div>
    </div>
  );
}
