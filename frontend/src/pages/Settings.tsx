import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { User } from "../types";

export default function Settings() {
  const { user, logout } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // change password
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");

  // users (admin)
  const [users, setUsers] = useState<User[]>([]);
  const [nu, setNu] = useState({ username: "", display_name: "", password: "" });

  async function loadUsers() {
    try {
      setUsers(await api.listUsers());
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    loadUsers();
  }, []);

  async function changePw(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (pw.length < 4) return setErr("Wachtwoord moet minimaal 4 tekens zijn.");
    if (pw !== pw2) return setErr("Wachtwoorden komen niet overeen.");
    try {
      await api.changePassword(pw);
      setPw("");
      setPw2("");
      setMsg("Wachtwoord gewijzigd.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Wijzigen mislukt");
    }
  }

  async function addUser(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      await api.createUser({ ...nu, username: nu.username.trim(), is_admin: false });
      setNu({ username: "", display_name: "", password: "" });
      setMsg("Account aangemaakt.");
      loadUsers();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Aanmaken mislukt");
    }
  }

  async function removeUser(id: number) {
    if (!confirm("Dit account verwijderen?")) return;
    try {
      await api.deleteUser(id);
      loadUsers();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verwijderen mislukt");
    }
  }

  return (
    <>
      <div className="topbar">
        <h1>Instellingen</h1>
      </div>
      <div className="content stack">
        {msg && <div className="notice">{msg}</div>}
        {err && <div className="error">{err}</div>}

        <div className="card" style={{ padding: 16 }}>
          <div className="row spread">
            <div>
              <div style={{ fontWeight: 700 }}>{user?.display_name}</div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                @{user?.username}
                {user?.is_admin ? " · beheerder" : ""}
              </div>
            </div>
            <button className="btn-ghost" onClick={logout}>
              Uitloggen
            </button>
          </div>
        </div>

        <div className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Wachtwoord wijzigen</h3>
          <form onSubmit={changePw} className="stack">
            <input type="password" placeholder="Nieuw wachtwoord" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
            <input type="password" placeholder="Herhaal wachtwoord" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" />
            <button className="btn-primary">Opslaan</button>
          </form>
        </div>

        {user?.is_admin && (
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Accounts</h3>
            <div className="stack" style={{ marginBottom: 16 }}>
              {users.map((u) => (
                <div key={u.id} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
                  <div>
                    <div>{u.display_name}</div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>@{u.username}{u.is_admin ? " · beheerder" : ""}</div>
                  </div>
                  {u.id !== user.id && (
                    <button className="btn-danger" onClick={() => removeUser(u.id)}>
                      Verwijder
                    </button>
                  )}
                </div>
              ))}
            </div>
            <h4 style={{ margin: "0 0 8px" }}>Nieuw account (bijv. je partner)</h4>
            <form onSubmit={addUser} className="stack">
              <input placeholder="Weergavenaam" value={nu.display_name} onChange={(e) => setNu({ ...nu, display_name: e.target.value })} required />
              <input placeholder="Gebruikersnaam" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} autoCapitalize="none" required />
              <input type="password" placeholder="Wachtwoord" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} autoComplete="new-password" required />
              <button className="btn-primary">Account aanmaken</button>
            </form>
          </div>
        )}

        <p className="muted center" style={{ fontSize: "0.8rem" }}>Kledingkast · zelf-gehost</p>
      </div>
    </>
  );
}
