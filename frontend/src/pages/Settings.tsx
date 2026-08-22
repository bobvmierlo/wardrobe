import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useWardrobe } from "../wardrobe";
import AppFooter from "../components/AppFooter";
import { INVITATION_STATUS_LABELS, ROLE_LABELS, SIZE_KIND_LABELS, compareSizes, type Category, type ColorLogic, type Invitation, type MemberRole, type SizeKind, type SizeOption, type User, type WardrobeMember } from "../types";

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

  // invitation links (for people without an account yet)
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [linkLabel, setLinkLabel] = useState("");
  const [linkRole, setLinkRole] = useState<MemberRole>("viewer");
  const [linkDays, setLinkDays] = useState("14");
  const [copied, setCopied] = useState<number | null>(null);

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
  async function loadInvitations(wardrobeId: number) {
    try {
      setInvitations(await api.listInvitations(wardrobeId));
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
    if (!ownWardrobe) return;
    loadMembers(ownWardrobe.id);
    loadInvitations(ownWardrobe.id);
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

  /** The full link to share, built from the current origin. */
  function inviteUrl(invitation: Invitation): string {
    return `${window.location.origin}${invitation.path}`;
  }

  async function createLink(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (!ownWardrobe) return;
    try {
      const created = await api.createInvitation(ownWardrobe.id, {
        role: linkRole,
        label: linkLabel.trim() || null,
        expires_days: linkDays ? Number(linkDays) : null,
      });
      setLinkLabel("");
      setMsg("Uitnodigingslink gemaakt — kopieer 'm en stuur 'm door.");
      await loadInvitations(ownWardrobe.id);
      copyLink(created);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Link maken mislukt");
    }
  }

  async function copyLink(invitation: Invitation) {
    const url = inviteUrl(invitation);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(invitation.id);
      setTimeout(() => setCopied((id) => (id === invitation.id ? null : id)), 2000);
    } catch {
      // Clipboard access is blocked outside a secure context (plain http on
      // your LAN, for instance) — the link is on screen to copy by hand.
      setErr("Kopiëren lukte niet; selecteer de link en kopieer 'm handmatig.");
    }
  }

  async function revokeLink(invitation: Invitation) {
    if (!ownWardrobe) return;
    if (!confirm("Deze uitnodigingslink intrekken? Hij werkt daarna niet meer.")) return;
    setErr(null);
    try {
      await api.revokeInvitation(invitation.id);
      await loadInvitations(ownWardrobe.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Intrekken mislukt");
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

  // Users that can still be invited to my kast: everyone except me (the owner)
  // and anyone the kast is already shared with.
  const sharedIds = new Set(members.map((m) => m.user.id));
  const invitable = users
    .filter((u) => u.id !== user?.id && !sharedIds.has(u.id))
    .sort((a, b) => a.display_name.localeCompare(b.display_name, "nl", { sensitivity: "base" }));

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

          {invitable.length === 0 ? (
            <p className="muted" style={{ fontSize: "0.85rem", margin: 0 }}>
              {users.length <= 1
                ? "Er zijn nog geen andere gebruikers om uit te nodigen."
                : "Alle gebruikers hebben al toegang tot deze kast."}
            </p>
          ) : (
            <form onSubmit={invite} className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <select
                value={inviteName}
                onChange={(e) => setInviteName(e.target.value)}
                style={{ flex: "1 1 45%", width: "auto" }}
                required
              >
                <option value="" disabled>Kies een gebruiker…</option>
                {invitable.map((u) => (
                  <option key={u.id} value={u.username}>
                    {u.display_name} (@{u.username})
                  </option>
                ))}
              </select>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as MemberRole)} style={{ flex: "1 1 25%", width: "auto" }}>
                <option value="viewer">{ROLE_LABELS.viewer}</option>
                <option value="editor">{ROLE_LABELS.editor}</option>
              </select>
              <button className="btn-primary" style={{ flex: "none" }}>Uitnodigen</button>
            </form>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />

          <h4 style={{ margin: "0 0 6px" }}>Uitnodigen met een link</h4>
          <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
            Nog geen account? Stuur iemand een persoonlijke link. Daarmee kan diegene
            zelf een account aanmaken en komt 'ie meteen in je kast. Zonder zo'n link
            kan niemand zich registreren.
          </p>

          {invitations.length > 0 && (
            <div className="stack" style={{ marginBottom: 12 }}>
              {invitations.map((inv) => (
                <div key={inv.id} className="invite-row">
                  <div style={{ minWidth: 0 }}>
                    <div>
                      {inv.label || <span className="muted">Zonder omschrijving</span>}{" "}
                      <span className={`status-badge ${inv.status}`}>
                        {INVITATION_STATUS_LABELS[inv.status]}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: "0.78rem" }}>
                      Rol: {ROLE_LABELS[inv.role]}
                      {inv.accepted_by && ` · gebruikt door ${inv.accepted_by.display_name}`}
                      {inv.status === "open" && inv.expires_at &&
                        ` · geldig tot ${new Date(inv.expires_at).toLocaleDateString("nl-NL")}`}
                    </div>
                    {inv.status === "open" && (
                      <div className="invite-link">
                        <input readOnly value={inviteUrl(inv)} onFocus={(e) => e.target.select()} />
                        <button className="btn-ghost btn-small" type="button" onClick={() => copyLink(inv)}>
                          {copied === inv.id ? "✓ Gekopieerd" : "Kopieer"}
                        </button>
                      </div>
                    )}
                  </div>
                  {inv.status === "open" && (
                    <button className="btn-danger btn-small" onClick={() => revokeLink(inv)}>
                      Intrekken
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          <form onSubmit={createLink} className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              placeholder="Voor wie? (naam of e-mail)"
              value={linkLabel}
              onChange={(e) => setLinkLabel(e.target.value)}
              style={{ flex: "1 1 45%" }}
            />
            <select value={linkRole} onChange={(e) => setLinkRole(e.target.value as MemberRole)} style={{ flex: "1 1 25%", width: "auto" }}>
              <option value="viewer">{ROLE_LABELS.viewer}</option>
              <option value="editor">{ROLE_LABELS.editor}</option>
            </select>
            <select value={linkDays} onChange={(e) => setLinkDays(e.target.value)} style={{ flex: "1 1 25%", width: "auto" }}>
              <option value="7">7 dagen geldig</option>
              <option value="14">14 dagen geldig</option>
              <option value="30">30 dagen geldig</option>
              <option value="">Nooit verlopen</option>
            </select>
            <button className="btn-primary" style={{ flex: "none" }}>Link maken</button>
          </form>
        </div>

        {user?.is_admin && (
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Logboek</h3>
            <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
              Wie heeft wat gewijzigd, goedgekeurd of afgekeurd — plus de technische
              logregels van de server, dezelfde als in de container-logs.
            </p>
            <Link to="/logboek" className="btn-ghost btn-block" style={{ display: "block", textAlign: "center", padding: 12 }}>
              📋 Logboek openen
            </Link>
          </div>
        )}

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
