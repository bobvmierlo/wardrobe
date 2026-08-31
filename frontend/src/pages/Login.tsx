import { useEffect, useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth";

type Mode = "login" | "register";

export default function Login() {
  const { login, refresh } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Whether anyone may sign up here. Assumed closed until the server says
   *  otherwise — that is the default, and it is the safer thing to promise. */
  const [selfRegistration, setSelfRegistration] = useState(false);

  // register form
  const [displayName, setDisplayName] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPassword2, setNewPassword2] = useState("");

  useEffect(() => {
    api
      .authConfig()
      .then((cfg) => setSelfRegistration(cfg.self_registration))
      .catch(() => {
        /* offline or unreachable: the invitation-only message still holds */
      });
  }, []);

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

  async function register(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 4) return setError("Wachtwoord moet minimaal 4 tekens zijn.");
    if (newPassword !== newPassword2) return setError("Wachtwoorden komen niet overeen.");
    setBusy(true);
    try {
      const res = await api.register({
        username: newUsername.trim(),
        display_name: displayName.trim(),
        password: newPassword,
      });
      // Registering signs you straight in, same as a login would.
      setToken(res.access_token);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registreren mislukt");
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand">
          <div className="logo">👕</div>
          <h1>Kledingkast</h1>
          <div className="muted">
            {mode === "register" ? "Maak een account aan" : "Log in om verder te gaan"}
          </div>
        </div>

        {error && <div className="error">{error}</div>}

        {mode === "register" ? (
          <form onSubmit={register} className="stack">
            <div className="field">
              <label>Je naam</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                required
              />
            </div>
            <div className="field">
              <label>Gebruikersnaam</label>
              <input
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
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
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <div className="field">
              <label>Herhaal wachtwoord</label>
              <input
                type="password"
                value={newPassword2}
                onChange={(e) => setNewPassword2(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <button className="btn-primary btn-block" disabled={busy}>
              {busy ? "Bezig…" : "Account aanmaken"}
            </button>
            <button
              type="button"
              className="btn-ghost btn-block"
              onClick={() => {
                setMode("login");
                setError(null);
              }}
            >
              Ik heb al een account
            </button>
          </form>
        ) : (
          <>
            <form onSubmit={submit} className="stack">
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

            {/* The one thing a newcomer needs to be told, and the reason the
                login screen has no sign-up button to look for. */}
            {selfRegistration ? (
              <div className="login-foot">
                <div className="muted">Nog geen account?</div>
                <button
                  type="button"
                  className="btn-ghost btn-block"
                  onClick={() => {
                    setMode("register");
                    setError(null);
                  }}
                >
                  Account aanmaken
                </button>
              </div>
            ) : (
              <div className="login-foot">
                <div className="notice">
                  <strong>Alleen op uitnodiging.</strong> Je kunt je hier niet zelf
                  aanmelden. Vraag de beheerder van deze Kledingkast om een
                  uitnodigingslink of QR-code — daarmee kies je zelf je naam,
                  gebruikersnaam en wachtwoord.
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
