import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, photoUrl } from "../api";
import ItemForm from "../components/ItemForm";
import type { Item, OutfitPartner } from "../types";

export default function ItemDetail() {
  const { id } = useParams();
  const itemId = Number(id);
  const navigate = useNavigate();
  const [item, setItem] = useState<Item | null>(null);
  const [partners, setPartners] = useState<OutfitPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [it, ps] = await Promise.all([api.getItem(itemId), api.outfitsFor(itemId)]);
      setItem(it);
      setPartners(ps);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Laden mislukt");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  async function remove() {
    if (!confirm("Dit kledingstuk definitief verwijderen?")) return;
    await api.deleteItem(itemId);
    navigate("/", { replace: true });
  }

  const src = item ? photoUrl(item) : null;

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={() => navigate(-1)}>
          ← Terug
        </button>
        <h1>{editing ? "Bewerken" : "Kledingstuk"}</h1>
        {item && !editing ? (
          <button className="btn-ghost" onClick={() => setEditing(true)}>
            Bewerk
          </button>
        ) : (
          <span style={{ width: 64 }} />
        )}
      </div>

      <div className="content">
        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="error">{error}</div>
        ) : !item ? (
          <div className="empty">Niet gevonden.</div>
        ) : editing ? (
          <ItemForm
            initial={item}
            submitLabel="Wijzigingen opslaan"
            onSubmit={async (form) => {
              const updated = await api.updateItem(itemId, form);
              setItem(updated);
              setEditing(false);
            }}
          />
        ) : (
          <div className="stack">
            {src ? (
              <img className="detail-photo" src={src} alt={item.name} />
            ) : (
              <div className="detail-photo noimg" style={{ display: "flex", alignItems: "center", justifyContent: "center", fontSize: "3rem", height: 220 }}>
                👕
              </div>
            )}

            <div className="row spread">
              <h2 style={{ margin: 0 }}>
                {item.is_favorite && <span style={{ color: "var(--fav)" }}>★ </span>}
                {item.name}
              </h2>
              <span className="pill">{item.category}</span>
            </div>

            <div>
              {item.brand && (
                <div className="kv">
                  <span className="k">Merk</span>
                  <span>{item.brand}</span>
                </div>
              )}
              {item.color && (
                <div className="kv">
                  <span className="k">Kleur</span>
                  <span>{item.color}</span>
                </div>
              )}
              {item.size && (
                <div className="kv">
                  <span className="k">Maat</span>
                  <span>{item.size}</span>
                </div>
              )}
              {item.seasons.length > 0 && (
                <div className="kv">
                  <span className="k">Seizoen</span>
                  <span>{item.seasons.join(", ")}</span>
                </div>
              )}
              {item.notes && (
                <div className="kv">
                  <span className="k">Notities</span>
                  <span style={{ textAlign: "right", maxWidth: "60%" }}>{item.notes}</span>
                </div>
              )}
            </div>

            <div>
              <div className="row spread" style={{ marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>Combineert met</h3>
                <Link to="/combine" state={{ anchorId: item.id }} className="pill">
                  Combineer →
                </Link>
              </div>
              {partners.length === 0 ? (
                <p className="muted">Nog geen goedgekeurde combinaties. Ga naar Combineer om te swipen.</p>
              ) : (
                <div className="grid">
                  {partners.map(({ item: p, approved_by }) => {
                    const psrc = photoUrl(p, true);
                    return (
                      <Link to={`/item/${p.id}`} key={p.id} className="card">
                        {psrc ? <img className="thumb" src={psrc} alt={p.name} /> : <div className="noimg">👕</div>}
                        <div className="meta">
                          <div className="name">{p.name}</div>
                          <div className="sub">👍 {approved_by.join(", ")}</div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>

            <button className="btn-danger btn-block" onClick={remove}>
              Verwijderen
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
