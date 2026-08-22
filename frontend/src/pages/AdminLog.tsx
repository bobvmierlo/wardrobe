import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import AppFooter from "../components/AppFooter";
import type { AuditEntry, AuditPage, LogEntry, User } from "../types";

type Tab = "audit" | "system";

const PAGE_SIZE = 50;

/** "22 aug 2026, 14:03" — short, local, and unambiguous about the day. */
function when(iso: string): string {
  const value = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return value.toLocaleString("nl-NL", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The beheerder's window on what the app has been doing.
 *
 * Two tabs, because they answer different questions: the audit trail says who
 * changed what (and survives a restart), the system log is the technical
 * stream from the container, kept in memory only.
 */
export default function AdminLog() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("audit");

  const [page, setPage] = useState<AuditPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [fAction, setFAction] = useState("");
  const [fUser, setFUser] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState<User[]>([]);

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await api.auditTrail({
          action: fAction || undefined,
          user_id: fUser ? Number(fUser) : undefined,
          q: search || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Logboek laden mislukt");
    } finally {
      setLoading(false);
    }
  }, [fAction, fUser, search, offset]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await api.appLogs({ level: level || undefined, limit: 200 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Log laden mislukt");
    } finally {
      setLoading(false);
    }
  }, [level]);

  useEffect(() => {
    api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    if (tab === "audit") loadAudit();
    else loadLogs();
  }, [tab, loadAudit, loadLogs]);

  // Changing a filter starts over at the first page.
  useEffect(() => {
    setOffset(0);
  }, [fAction, fUser, search]);

  if (user && !user.is_admin) {
    return (
      <div className="app">
        <div className="topbar">
          <button className="btn-ghost" onClick={() => navigate(-1)}>← Terug</button>
          <h1>Logboek</h1>
          <span style={{ width: 64 }} />
        </div>
        <div className="content">
          <div className="empty">
            <div className="big">🔒</div>
            <p>Het logboek is alleen voor beheerders.</p>
          </div>
        </div>
      </div>
    );
  }

  const total = page?.total ?? 0;
  const shown = page?.entries.length ?? 0;

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={() => navigate(-1)}>← Terug</button>
        <h1>Logboek</h1>
        <span style={{ width: 64 }} />
      </div>

      <div className="content">
        <div className="seg">
          <button className={`seg-btn ${tab === "audit" ? "active" : ""}`} onClick={() => setTab("audit")}>
            Wie deed wat
          </button>
          <button className={`seg-btn ${tab === "system" ? "active" : ""}`} onClick={() => setTab("system")}>
            Systeemlog
          </button>
        </div>

        {error && <div className="error">{error}</div>}

        {tab === "audit" ? (
          <>
            <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
              Elke wijziging, goedkeuring en afkeuring, met wie het deed en wanneer.
              Dit wordt bewaard in de database.
            </p>

            <div className="filters">
              <select value={fAction} onChange={(e) => setFAction(e.target.value)}>
                <option value="">Alle handelingen</option>
                {(page?.actions ?? []).map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              <select value={fUser} onChange={(e) => setFUser(e.target.value)}>
                <option value="">Iedereen</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.display_name}</option>
                ))}
              </select>
              <form
                className="row"
                style={{ flex: "1 1 100%", gap: 8 }}
                onSubmit={(e) => {
                  e.preventDefault();
                  setSearch(query.trim());
                }}
              >
                <input placeholder="Zoek in omschrijving…" value={query} onChange={(e) => setQuery(e.target.value)} />
                <button className="btn-ghost" style={{ flex: "none" }}>Zoek</button>
              </form>
              {(fAction || fUser || search) && (
                <button
                  className="btn-ghost"
                  onClick={() => { setFAction(""); setFUser(""); setQuery(""); setSearch(""); }}
                >
                  Wis filters
                </button>
              )}
            </div>

            {loading ? (
              <div className="spinner" />
            ) : shown === 0 ? (
              <div className="empty">
                <p className="muted">Geen regels gevonden.</p>
              </div>
            ) : (
              <>
                <div className="log-list">
                  {page!.entries.map((entry) => (
                    <AuditRow key={entry.id} entry={entry} />
                  ))}
                </div>
                <div className="log-pager">
                  <button
                    className="btn-ghost btn-small"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
                  >
                    ← Nieuwer
                  </button>
                  <span className="muted" style={{ fontSize: "0.8rem" }}>
                    {offset + 1}–{offset + shown} van {total}
                  </span>
                  <button
                    className="btn-ghost btn-small"
                    disabled={offset + shown >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Ouder →
                  </button>
                </div>
              </>
            )}
          </>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
              Dezelfde regels als <code>docker compose logs</code>, de nieuwste bovenaan.
              Deze staan alleen in het geheugen en zijn dus leeg na een herstart.
            </p>

            <div className="filters">
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                <option value="">Alles</option>
                <option value="INFO">INFO en hoger</option>
                <option value="WARNING">Alleen waarschuwingen en fouten</option>
                <option value="ERROR">Alleen fouten</option>
              </select>
              <button className="btn-ghost" onClick={loadLogs}>Vernieuwen</button>
            </div>

            {loading ? (
              <div className="spinner" />
            ) : logs.length === 0 ? (
              <div className="empty">
                <p className="muted">Nog geen logregels.</p>
              </div>
            ) : (
              <div className="log-list">
                {logs.map((entry) => (
                  <div key={entry.id} className="log-row">
                    <div className="log-head">
                      <span className={`level-badge ${entry.level}`}>{entry.level}</span>
                      <span>{when(entry.time)}</span>
                      <span>· {entry.logger}</span>
                    </div>
                    <div className="log-detail mono">{entry.message}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        <AppFooter />
      </div>
    </div>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  return (
    <div className="log-row">
      <div className="log-head">
        <span>{when(entry.created_at)}</span>
        <span className="status-badge">{entry.action_label}</span>
        {entry.wardrobe_name && <span>· {entry.wardrobe_name}</span>}
      </div>
      <div className="log-detail">
        <span className="log-actor">{entry.user_name}</span> — {entry.detail}
      </div>
    </div>
  );
}
