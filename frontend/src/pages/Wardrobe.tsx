import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import type { Item } from "../types";

export default function Wardrobe() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [favOnly, setFavOnly] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setItems(await api.listItems());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Laden mislukt");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(() => {
    const set = new Set(items.map((i) => i.category));
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items.filter((i) => {
      if (favOnly && !i.is_favorite) return false;
      if (category && i.category !== category) return false;
      if (needle) {
        const hay = `${i.name} ${i.brand ?? ""} ${i.color ?? ""} ${i.category}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [items, q, category, favOnly]);

  return (
    <>
      <div className="topbar">
        <h1>Mijn kast {items.length > 0 && <span className="muted">· {items.length}</span>}</h1>
      </div>
      <div className="content">
        <div className="field">
          <input
            placeholder="Zoek op naam, merk, kleur…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <div className="chips">
          <button className={`chip ${!category && !favOnly ? "active" : ""}`} onClick={() => { setCategory(null); setFavOnly(false); }}>
            Alles
          </button>
          <button className={`chip ${favOnly ? "active" : ""}`} onClick={() => { setFavOnly((v) => !v); }}>
            ★ Favoriet
          </button>
          {categories.map((c) => (
            <button key={c} className={`chip ${category === c ? "active" : ""}`} onClick={() => setCategory(category === c ? null : c)}>
              {c}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="error">{error}</div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="big">👗</div>
            {items.length === 0 ? (
              <>
                <p>Je kast is nog leeg.</p>
                <p className="muted">Tik op de knop rechtsonder om je eerste kledingstuk toe te voegen.</p>
              </>
            ) : (
              <p>Geen kledingstukken gevonden.</p>
            )}
          </div>
        ) : (
          <div className="grid">
            {filtered.map((item) => {
              const src = photoUrl(item, true);
              return (
                <Link to={`/item/${item.id}`} key={item.id} className="card">
                  {item.is_favorite && <span className="fav">★</span>}
                  {src ? (
                    <img className="thumb" src={src} alt={item.name} loading="lazy" />
                  ) : (
                    <div className="noimg">👕</div>
                  )}
                  <div className="meta">
                    <div className="name">{item.name}</div>
                    <div className="sub">
                      {item.category}
                      {item.brand ? ` · ${item.brand}` : ""}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
        <AppFooter />
      </div>

      <button className="fab" onClick={() => navigate("/add")} aria-label="Kledingstuk toevoegen">
        <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      </button>
    </>
  );
}
