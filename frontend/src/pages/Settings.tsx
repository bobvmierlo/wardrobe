import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SIZE_KIND_LABELS, compareSizes, type Category, type SizeKind, type SizeOption, type User } from "../types";

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

  // categories & sizes (admin)
  const [categories, setCategories] = useState<Category[]>([]);
  const [sizes, setSizes] = useState<SizeOption[]>([]);
  const [newCat, setNewCat] = useState("");
  const [newSize, setNewSize] = useState("");
  const [newSizeKind, setNewSizeKind] = useState<SizeKind>("clothing");

  async function loadUsers() {
    try {
      setUsers(await api.listUsers());
    } catch {
      /* ignore */
    }
  }
  async function loadCatalog() {
    try {
      setCategories(await api.listCategories());
      setSizes(await api.listSizes());
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    loadUsers();
    loadCatalog();
  }, []);

  async function addCategory(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (!newCat.trim()) return;
    try {
      await api.createCategory(newCat.trim());
      setNewCat("");
      loadCatalog();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Toevoegen mislukt");
    }
  }
  async function removeCategory(id: number) {
    setErr(null);
    try {
      await api.deleteCategory(id);
      loadCatalog();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verwijderen mislukt");
    }
  }
  async function addSize(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (!newSize.trim()) return;
    try {
      await api.createSize(newSize.trim(), newSizeKind);
      setNewSize("");
      loadCatalog();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Toevoegen mislukt");
    }
  }
  async function removeSize(id: number) {
    setErr(null);
    try {
      await api.deleteSize(id);
      loadCatalog();
    } catch (e) {
      // When the size is still assigned to items the API refuses (409); warn the
      // admin and let them confirm before deleting it anyway.
      const status = (e as { status?: number }).status;
      const detail = e instanceof Error ? e.message : "Verwijderen mislukt";
      if (status === 409 && confirm(`${detail}.\n\nToch verwijderen? De kledingstukken behouden hun huidige maat.`)) {
        try {
          await api.deleteSize(id, true);
          loadCatalog();
        } catch (e2) {
          setErr(e2 instanceof Error ? e2.message : "Verwijderen mislukt");
        }
        return;
      }
      if (status !== 409) setErr(detail);
    }
  }

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
            <h3 style={{ marginTop: 0 }}>Categorieën</h3>
            <div className="tag-list">
              {categories.map((c) => (
                <span key={c.id} className="tag">
                  {c.name}
                  <button type="button" className="tag-x" onClick={() => removeCategory(c.id)} aria-label={`Verwijder ${c.name}`}>
                    ✕
                  </button>
                </span>
              ))}
            </div>
            <form onSubmit={addCategory} className="row" style={{ gap: 8, marginTop: 12 }}>
              <input placeholder="Nieuwe categorie" value={newCat} onChange={(e) => setNewCat(e.target.value)} />
              <button className="btn-primary" style={{ flex: "none" }}>Toevoegen</button>
            </form>
          </div>
        )}

        {user?.is_admin && (
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Maten</h3>
            {(["clothing", "shoes", "accessory"] as SizeKind[]).map((kind) => {
              const group = sizes.filter((s) => s.kind === kind).sort(compareSizes);
              if (group.length === 0) return null;
              return (
                <div key={kind} style={{ marginBottom: 12 }}>
                  <div className="muted" style={{ fontSize: "0.78rem", marginBottom: 6 }}>{SIZE_KIND_LABELS[kind]}</div>
                  <div className="tag-list">
                    {group.map((s) => (
                      <span key={s.id} className="tag">
                        {s.label}
                        <button type="button" className="tag-x" onClick={() => removeSize(s.id)} aria-label={`Verwijder ${s.label}`}>
                          ✕
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
            <form onSubmit={addSize} className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <input placeholder="Nieuwe maat" value={newSize} onChange={(e) => setNewSize(e.target.value)} style={{ flex: "1 1 40%" }} />
              <select value={newSizeKind} onChange={(e) => setNewSizeKind(e.target.value as SizeKind)} style={{ flex: "1 1 30%", width: "auto" }}>
                <option value="clothing">Kleding</option>
                <option value="shoes">Schoenen</option>
                <option value="accessory">One-size</option>
              </select>
              <button className="btn-primary" style={{ flex: "none" }}>Toevoegen</button>
            </form>
          </div>
        )}

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
