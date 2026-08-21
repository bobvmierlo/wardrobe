import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, photoUrl } from "../api";
import type { Item, OutfitPartner } from "../types";

export default function Outfits() {
  const [items, setItems] = useState<Item[]>([]);
  const [selected, setSelected] = useState<Item | null>(null);
  const [partners, setPartners] = useState<OutfitPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPartners, setLoadingPartners] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.listItems();
        setItems(list);
        if (list.length) setSelected(list[0]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoadingPartners(true);
    api
      .outfitsFor(selected.id)
      .then(setPartners)
      .finally(() => setLoadingPartners(false));
  }, [selected]);

  return (
    <>
      <div className="topbar">
        <h1>Outfits</h1>
      </div>
      <div className="content">
        {loading ? (
          <div className="spinner" />
        ) : items.length === 0 ? (
          <div className="empty">
            <div className="big">✨</div>
            <p>Nog geen kledingstukken. Voeg eerst wat toe.</p>
          </div>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Kies een stuk om te zien waarmee het (goedgekeurd) combineert.
            </p>
            <div className="chips" style={{ marginBottom: 18 }}>
              {items.map((it) => {
                const s = photoUrl(it, true);
                const active = selected?.id === it.id;
                return (
                  <button
                    key={it.id}
                    onClick={() => setSelected(it)}
                    className="chip"
                    style={{
                      padding: 4,
                      borderColor: active ? "var(--primary)" : "var(--border)",
                      borderWidth: 2,
                    }}
                    title={it.name}
                  >
                    {s ? (
                      <img src={s} alt={it.name} style={{ width: 46, height: 46, borderRadius: 8, objectFit: "cover", display: "block" }} />
                    ) : (
                      <span style={{ display: "inline-flex", width: 46, height: 46, alignItems: "center", justifyContent: "center" }}>👕</span>
                    )}
                  </button>
                );
              })}
            </div>

            {selected && (
              <div className="anchor-band" style={{ marginBottom: 16 }}>
                {photoUrl(selected, true) ? (
                  <img src={photoUrl(selected, true)!} alt={selected.name} />
                ) : (
                  <div className="noimg-sm">👕</div>
                )}
                <div>
                  <div style={{ fontWeight: 700 }}>{selected.name}</div>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>{selected.category}</div>
                </div>
                <Link to={`/item/${selected.id}`} className="pill" style={{ marginLeft: "auto" }}>
                  Details
                </Link>
              </div>
            )}

            {loadingPartners ? (
              <div className="spinner" />
            ) : partners.length === 0 ? (
              <div className="empty">
                <p className="muted">Nog geen goedgekeurde combinaties voor dit stuk.</p>
                <Link to="/combine" state={{ anchorId: selected?.id }} className="btn-primary" style={{ display: "inline-block", marginTop: 8 }}>
                  Ga combineren →
                </Link>
              </div>
            ) : (
              <div className="grid">
                {partners.map(({ item: p, approved_by }) => {
                  const s = photoUrl(p, true);
                  return (
                    <Link to={`/item/${p.id}`} key={p.id} className="card">
                      {s ? <img className="thumb" src={s} alt={p.name} /> : <div className="noimg">👕</div>}
                      <div className="meta">
                        <div className="name">{p.name}</div>
                        <div className="sub">👍 {approved_by.join(", ")}</div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
