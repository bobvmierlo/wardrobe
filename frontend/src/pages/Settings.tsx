import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useWardrobe } from "../wardrobe";
import AppFooter from "../components/AppFooter";
import { ROLE_LABELS, SIZE_KIND_LABELS, compareSizes, type Category, type ColorLogic, type MemberRole, type SizeKind, type SizeOption, type User, type WardrobeMember } from "../types";

export default function Settings() {
  const { user, logout } = useAuth();
  const { wardrobes, refresh: refreshWardrobes } = useWardrobe();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // change password
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");

  // sharing my own kast
  const ownWardrobe = wardrobes.find((w) => w.my_role === "owner") ?? null;
  const [members, setMembers] = useState<WardrobeMember[]>([]);
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState<MemberRole>("viewer");

  // users (admin)
  const [users, setUsers] = useState<User[]>([]);
  const [nu, setNu] = useState({ username: "", display_name: "", password: "", is_admin: false });

  // colour-combination logic (admin)
  const [logic, setLogic] = useState<ColorLogic | null>(null);
  const [ruleA, setRuleA] = useState("");
  const [ruleB, setRuleB] = useState("");
  const [ruleVerdict, setRuleVerdict] = useState<"good" | "bad">("good");

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
  async function loadLogic() {
    try {
      setLogic(await api.colorLogic());
    } catch {
      /* ignore */
    }
  }
  async function loadMembers(wardrobeId: number) {
    try {
      setMembers(await api.wardrobeMembers(wardrobeId));
    } catch {
      /* ignore */
    }
  }
  useEffect(() => {
    loadUsers();
    loadCatalog();
    loadLogic();
  }, []);
  useEffect(() => {
    if (ownWardrobe) loadMembers(ownWardrobe.id);
  }, [ownWardrobe?.id]);
  // When linked to from the "Delen" button (/settings#delen), scroll the
  // sharing card into view and highlight it briefly.
  useEffect(() => {
    if (window.location.hash !== "#delen") return;
    const el = document.getElementById("delen");
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("flash");
    const t = setTimeout(() => el.classList.remove("flash"), 1600);
    return () => clearTimeout(t);
  }, []);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (!ownWardrobe || !inviteName.trim()) return;
    try {
      await api.inviteMember(ownWardrobe.id, inviteName.trim(), inviteRole);
      setInviteName("");
      setInviteRole("viewer");
      setMsg("Uitnodiging toegevoegd.");
      await loadMembers(ownWardrobe.id);
      refreshWardrobes();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Uitnodigen mislukt");
    }
  }
  async function changeMemberRole(userId: number, role: MemberRole) {
    if (!ownWardrobe) return;
    setErr(null);
    try {
      await api.updateMember(ownWardrobe.id, userId, role);
      await loadMembers(ownWardrobe.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Wijzigen mislukt");
    }
  }
  async function removeMember(userId: number) {
    if (!ownWardrobe) return;
    setErr(null);
    try {
      await api.removeMember(ownWardrobe.id, userId);
      await loadMembers(ownWardrobe.id);
      refreshWardrobes();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verwijderen mislukt");
    }
  }

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
      await api.createUser({ ...nu, username: nu.username.trim() });
      setNu({ username: "", display_name: "", password: "", is_admin: false });
      setMsg("Account aangemaakt.");
      loadUsers();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Aanmaken mislukt");
    }
  }

  async function toggleAdmin(u: User) {
    setErr(null);
    try {
      await api.updateUser(u.id, { is_admin: !u.is_admin });
      loadUsers();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Wijzigen mislukt");
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

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!ruleA || !ruleB) return;
    try {
      await api.addColorRule({ color_a: ruleA, color_b: ruleB, verdict: ruleVerdict });
      setRuleA("");
      setRuleB("");
      loadLogic();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Toevoegen mislukt");
    }
  }

  async function removeRule(id: number) {
    setErr(null);
    try {
      await api.deleteColorRule(id);
      loadLogic();
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

        <div className="card" id="delen" style={{ padding: 16, scrollMarginTop: 80 }}>
          <h3 style={{ marginTop: 0 }}>Mijn kast delen</h3>
          <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
            Nodig iemand uit voor je kast. Een <strong>bewerker</strong> kan kledingstukken
            toevoegen en aanpassen; een <strong>kijker</strong> kan alleen kijken, maar wél
            meestemmen op combinaties.
          </p>

          <div className="stack" style={{ marginBottom: 12 }}>
            {members.length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem", margin: 0 }}>
                Je kast is nog met niemand gedeeld.
              </p>
            ) : (
              members.map((m) => (
                <div key={m.user.id} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8, gap: 8 }}>
                  <div>
                    <div>{m.user.display_name}</div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>@{m.user.username}</div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    <select
                      value={m.role}
                      onChange={(e) => changeMemberRole(m.user.id, e.target.value as MemberRole)}
                      style={{ width: "auto", padding: "6px 10px" }}
                      aria-label={`Rol van ${m.user.display_name}`}
                    >
                      <option value="viewer">{ROLE_LABELS.viewer}</option>
                      <option value="editor">{ROLE_LABELS.editor}</option>
                    </select>
                    <button className="btn-danger" style={{ padding: "6px 10px" }} onClick={() => removeMember(m.user.id)}>
                      Verwijder
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <form onSubmit={invite} className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              placeholder="Gebruikersnaam"
              value={inviteName}
              onChange={(e) => setInviteName(e.target.value)}
              autoCapitalize="none"
              style={{ flex: "1 1 45%" }}
            />
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as MemberRole)} style={{ flex: "1 1 25%", width: "auto" }}>
              <option value="viewer">{ROLE_LABELS.viewer}</option>
              <option value="editor">{ROLE_LABELS.editor}</option>
            </select>
            <button className="btn-primary" style={{ flex: "none" }}>Uitnodigen</button>
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
                <div key={u.id} className="row spread" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8, gap: 8 }}>
                  <div>
                    <div>
                      {u.display_name}{" "}
                      <span className={`role-badge ${u.is_admin ? "admin" : ""}`}>
                        {u.is_admin ? "Beheerder" : "Gebruiker"}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>@{u.username}</div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    <button className="btn-ghost" style={{ padding: "6px 10px", fontSize: "0.82rem" }} onClick={() => toggleAdmin(u)}>
                      {u.is_admin ? "Maak gebruiker" : "Maak beheerder"}
                    </button>
                    {u.id !== user.id && (
                      <button className="btn-danger" style={{ padding: "6px 10px" }} onClick={() => removeUser(u.id)}>
                        Verwijder
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <p className="muted" style={{ fontSize: "0.8rem", marginTop: 0 }}>
              Een <strong>beheerder</strong> kan accounts, categorieën, maten en de combinatie-logica beheren.
              Een gewone <strong>gebruiker</strong> kan kledingstukken toevoegen en bewerken, combineren en outfits bekijken.
            </p>
            <h4 style={{ margin: "0 0 8px" }}>Nieuw account (bijv. je partner)</h4>
            <form onSubmit={addUser} className="stack">
              <input placeholder="Weergavenaam" value={nu.display_name} onChange={(e) => setNu({ ...nu, display_name: e.target.value })} required />
              <input placeholder="Gebruikersnaam" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} autoCapitalize="none" required />
              <input type="password" placeholder="Wachtwoord" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} autoComplete="new-password" required />
              <label className="row" style={{ gap: 10, cursor: "pointer" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={nu.is_admin} onChange={(e) => setNu({ ...nu, is_admin: e.target.checked })} />
                <span>Beheerder (mag instellingen beheren)</span>
              </label>
              <button className="btn-primary">Account aanmaken</button>
            </form>
          </div>
        )}

        {user?.is_admin && logic && (
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Combinatie-logica</h3>
            <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
              Suggesties worden gescoord op kleur en seizoen. Neutrale kleuren
              (<em>{logic.neutrals.join(", ")}</em>) passen bij vrijwel alles. Daarnaast tellen
              deze regels: een <strong>goed</strong> paar krijgt pluspunten, een <strong>botst</strong>-paar
              minpunten. Stukken zonder kleur of afgekeurde paren worden overgeslagen.
            </p>

            <div style={{ marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: "0.78rem", marginBottom: 6 }}>👍 Past mooi samen</div>
              <div className="tag-list">
                {logic.rules.filter((r) => r.verdict === "good").map((r) => (
                  <span key={r.id} className="tag good">
                    {r.color_a} + {r.color_b}
                    <button type="button" className="tag-x" onClick={() => removeRule(r.id)} aria-label="Verwijder regel">✕</button>
                  </span>
                ))}
                {logic.rules.every((r) => r.verdict !== "good") && <span className="muted" style={{ fontSize: "0.8rem" }}>Geen regels</span>}
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div className="muted" style={{ fontSize: "0.78rem", marginBottom: 6 }}>👎 Botst</div>
              <div className="tag-list">
                {logic.rules.filter((r) => r.verdict === "bad").map((r) => (
                  <span key={r.id} className="tag bad">
                    {r.color_a} + {r.color_b}
                    <button type="button" className="tag-x" onClick={() => removeRule(r.id)} aria-label="Verwijder regel">✕</button>
                  </span>
                ))}
                {logic.rules.every((r) => r.verdict !== "bad") && <span className="muted" style={{ fontSize: "0.8rem" }}>Geen regels</span>}
              </div>
            </div>

            <form onSubmit={addRule} className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <select value={ruleA} onChange={(e) => setRuleA(e.target.value)} style={{ flex: "1 1 28%", width: "auto" }} required>
                <option value="" disabled>Kleur 1…</option>
                {logic.colors.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={ruleB} onChange={(e) => setRuleB(e.target.value)} style={{ flex: "1 1 28%", width: "auto" }} required>
                <option value="" disabled>Kleur 2…</option>
                {logic.colors.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={ruleVerdict} onChange={(e) => setRuleVerdict(e.target.value as "good" | "bad")} style={{ flex: "1 1 20%", width: "auto" }}>
                <option value="good">Past</option>
                <option value="bad">Botst</option>
              </select>
              <button className="btn-primary" style={{ flex: "none" }}>Toevoegen</button>
            </form>
          </div>
        )}

        <AppFooter />
      </div>
    </>
  );
}
