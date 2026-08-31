import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, setToken } from "../api";
import { useAuth } from "../auth";
import { ROLE_LABELS, type InvitationInfo } from "../types";

type Mode = "choose" | "register" | "login";

/**
 * The page an invitation link opens — reachable without being signed in.
 *
 * It serves both kinds of link. A **kast** link has three ways in, depending on
 * who is holding it: an already signed-in user accepts with one tap; someone
 * with an account signs in first; a newcomer registers right here. An
 * **account** link has only that last one — it shares no kast, it just lets one
 * person in.
 *
 * Registering here is the way to an account whenever a beheerder keeps
 * self-registration closed, which is the default.
 */
export default function Invite() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading, login, refresh } = useAuth();

  const [info, setInfo] = useState<InvitationInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<Mode>("choose");

  // register form
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");

  // login form
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  useEffect(() => {
    api
      .invitationInfo(token)
      .then((loaded) => {
        setInfo(loaded);
        // An account link has nothing to choose between: registering is the
        // only thing it does.
        if (loaded.kind === "account") setMode("register");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Uitnodiging laden mislukt"))
      .finally(() => setLoading(false));
  }, [token]);

  /** Redeem the link for the user who is already (or just now) signed in. */
  async function accept() {
    setBusy(true);
    setError(null);
    try {
      await api.acceptInvitation(token);
      await refresh();
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accepteren mislukt");
      setBusy(false);
    }
  }

  async function register(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 4) return setError("Wachtwoord moet minimaal 4 tekens zijn.");
    if (password !== password2) return setError("Wachtwoorden komen niet overeen.");
    setBusy(true);
    try {
      // Registering redeems the link and signs the newcomer in at once.
      const res = await api.registerViaInvitation(token, {
        username: username.trim(),
        display_name: displayName.trim(),
        password,
      });
      setToken(res.access_token);
      await refresh();
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registreren mislukt");
      setBusy(false);
    }
  }

  async function signInThenAccept(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(loginName.trim(), loginPassword);
      // An account link grants no access to accept — signing in is all there
      // is to do with it.
      if (info?.kind !== "account") await api.acceptInvitation(token);
      await refresh();
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Inloggen mislukt");
      setBusy(false);
    }
  }

  if (loading || authLoading) {
    return (
      <div className="login-wrap">
        <div className="spinner" />
      </div>
    );
  }

  if (!info) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <div className="brand">
            <div className="logo">🔗</div>
            <h1>Uitnodiging</h1>
          </div>
          <div className="error">{error ?? "Deze uitnodiging is niet (meer) geldig."}</div>
          <button className="btn-ghost btn-block" onClick={() => navigate("/login", { replace: true })}>
            Naar inloggen
          </button>
        </div>
      </div>
    );
  }

  const account = info.kind === "account";

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand">
          <div className="logo">👕</div>
          <h1>Je bent uitgenodigd</h1>
          <div className="muted">
            {account ? (
              <>Maak je eigen account aan voor deze <strong>Kledingkast</strong></>
            ) : (
              <>
                <strong>{info.owner_name}</strong> deelt de kast{" "}
                <strong>{info.wardrobe_name}</strong> met je
              </>
            )}
          </div>
        </div>

        <p className="muted" style={{ fontSize: "0.85rem" }}>
          {account ? (
            <>
              Je kiest zelf je naam, gebruikersnaam en wachtwoord. Daarna heb je een
              eigen kast om je kleding in te zetten.
            </>
          ) : (
            <>
              Je krijgt de rol <strong>{info.role ? ROLE_LABELS[info.role] : "kijker"}</strong>.{" "}
              {info.role === "editor"
                ? "Je mag kledingstukken toevoegen en aanpassen, en meestemmen over combinaties."
                : "Je mag alles bekijken en meestemmen over combinaties."}
            </>
          )}
        </p>

        {error && <div className="error">{error}</div>}

        {user && account ? (
          <div className="stack">
            <div className="notice">
              Je bent al ingelogd als <strong>{user.display_name}</strong>. Deze
              uitnodiging is bedoeld voor iemand zonder account — geef 'm door, of log
              uit om er zelf een nieuw account mee te maken.
            </div>
            <button className="btn-primary btn-block" onClick={() => navigate("/", { replace: true })}>
              Naar mijn kast
            </button>
          </div>
        ) : user ? (
          <div className="stack">
            <div className="notice">
              Je bent ingelogd als <strong>{user.display_name}</strong>.
            </div>
            <button className="btn-primary btn-block" onClick={accept} disabled={busy}>
              {busy ? "Bezig…" : "Uitnodiging accepteren"}
            </button>
          </div>
        ) : mode === "register" ? (
          <form onSubmit={register} className="stack">
            <div className="field">
              <label>Je naam</label>
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </div>
            <div className="field">
              <label>Gebruikersnaam</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoCapitalize="none"
                autoCorrect="off"
                required
              />
            </div>
            <div className="field">
              <label>Wachtwoord</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
            </div>
            <div className="field">
              <label>Herhaal wachtwoord</label>
              <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} autoComplete="new-password" required />
            </div>
            <button className="btn-primary btn-block" disabled={busy}>
              {busy ? "Bezig…" : account ? "Account aanmaken" : "Account aanmaken en accepteren"}
            </button>
            <button
              type="button"
              className="btn-ghost btn-block"
              onClick={() => setMode(account ? "login" : "choose")}
            >
              {account ? "Ik heb al een account" : "Terug"}
            </button>
          </form>
        ) : mode === "login" ? (
          <form onSubmit={signInThenAccept} className="stack">
            <div className="field">
              <label>Gebruikersnaam</label>
              <input
                value={loginName}
                onChange={(e) => setLoginName(e.target.value)}
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
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <button className="btn-primary btn-block" disabled={busy}>
              {busy ? "Bezig…" : account ? "Inloggen" : "Inloggen en accepteren"}
            </button>
            <button
              type="button"
              className="btn-ghost btn-block"
              onClick={() => setMode(account ? "register" : "choose")}
            >
              {account ? "Toch een nieuw account aanmaken" : "Terug"}
            </button>
          </form>
        ) : (
          <div className="stack">
            <button className="btn-primary btn-block" onClick={() => setMode("register")}>
              Ik ben nieuw — account aanmaken
            </button>
            <button className="btn-ghost btn-block" onClick={() => setMode("login")}>
              Ik heb al een account — inloggen
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
