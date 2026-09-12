import { useEffect, useState } from "react";
import { api, setToken } from "../api";
import { useAuth } from "../auth";

type Mode = "login" | "register";

export default function Login() {
  const { login, refresh, ssoError, clearSsoError } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Whether anyone may sign up here. Assumed closed until the server says
   *  otherwise — that is the default, and it is the safer thing to promise. */
  const [selfRegistration, setSelfRegistration] = useState(false);

  /** What the server offers as ways in. No SSO until it says so, and the
   *  password form stays visible until it says otherwise — an unreachable
   *  server must never leave someone looking at a screen with no way in. */
  const [oidc, setOidc] = useState<{ enabled: boolean; label: string }>({
    enabled: false,
    label: "",
  });
  const [localLogin, setLocalLogin] = useState(true);
  /** The server's minimum, so the form says it instead of bouncing a 422 back. */
  const [minPassword, setMinPassword] = useState(8);
  /** Set when the operator tucked the password form away and the visitor asked
   *  for it anyway — the break-glass, one click deep. */
  const [showPasswordForm, setShowPasswordForm] = useState(false);

  // register form
  const [displayName, setDisplayName] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPassword2, setNewPassword2] = useState("");

  useEffect(() => {
    api
      .authConfig()
      .then((cfg) => {
        setSelfRegistration(cfg.self_registration);
        setOidc({ enabled: cfg.oidc_enabled, label: cfg.oidc_label });
        setLocalLogin(cfg.local_login);
        setMinPassword(cfg.min_password_length);
      })
      .catch(() => {
        /* offline or unreachable: the invitation-only message still holds, and
           the password form stays where it is */
      });
  }, []);

  // Visible when the operator left it visible, when the visitor asked for it,
  // or simply when there is no other way in.
  const passwordFormVisible = localLogin || showPasswordForm || !oidc.enabled;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    clearSsoError();
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
    if (newPassword.length < minPassword)
      return setError(`Wachtwoord moet minimaal ${minPassword} tekens zijn.`);
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

        {(error || ssoError) && <div className="error">{error ?? ssoError}</div>}

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
                minLength={minPassword}
                required
              />
              <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
                Minimaal {minPassword} tekens.
              </div>
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
            {oidc.enabled && (
              <div className="stack">
                {/* A real link, not a fetch: the server answers with a redirect
                    to the provider, which is another origin. */}
                <a className="btn-primary btn-block" href={api.oidcLoginUrl()}>
                  {oidc.label || "Inloggen met SSO"}
                </a>
              </div>
            )}

            {oidc.enabled && passwordFormVisible && <div className="login-or">of</div>}

            {passwordFormVisible ? (
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
            ) : (
              /* Tucked away, never removed: this is the way in when the
                 inlogdienst is down or misconfigured. */
              <button
                type="button"
                className="btn-ghost btn-block"
                onClick={() => setShowPasswordForm(true)}
              >
                Inloggen met gebruikersnaam en wachtwoord
              </button>
            )}

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
                  aanmelden.{" "}
                  {oidc.enabled
                    ? "Heb je al een account bij de inlogdienst hierboven, dan moet een beheerder je nog uitnodigen voor deze Kledingkast."
                    : "Vraag de beheerder van deze Kledingkast om een uitnodigingslink of QR-code — daarmee kies je zelf je naam, gebruikersnaam en wachtwoord."}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
