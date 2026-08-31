import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, photoUrl } from "../api";
import ItemForm from "../components/ItemForm";
import AppFooter from "../components/AppFooter";
import BottomNav from "../components/BottomNav";
import PartnerGrid from "../components/PartnerGrid";
import RejectedGrid from "../components/RejectedGrid";
import SuggestionList from "../components/SuggestionList";
import { useConfirm } from "../confirm";
import { useWardrobe } from "../wardrobe";
import type { Item, OutfitPartner, OutfitSuggestion, RejectedPartner } from "../types";

export default function ItemDetail() {
  const { id } = useParams();
  const itemId = Number(id);
  const navigate = useNavigate();
  const { wardrobes } = useWardrobe();
  const confirm = useConfirm();
  const [item, setItem] = useState<Item | null>(null);
  const [partners, setPartners] = useState<OutfitPartner[]>([]);
  const [rejected, setRejected] = useState<RejectedPartner[]>([]);
  const [suggestions, setSuggestions] = useState<OutfitSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [it, ps, rj, sg] = await Promise.all([
        api.getItem(itemId),
        api.outfitsFor(itemId),
        api.rejectedFor(itemId),
        api.suggestionsFor(itemId).catch(() => [] as OutfitSuggestion[]),
      ]);
      setItem(it);
      setPartners(ps);
      setRejected(rj);
      setSuggestions(sg);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Laden mislukt");
    } finally {
      setLoading(false);
    }
  }

  /** Reload everything a verdict can move between: approved, rejected, suggested. */
  async function reloadVerdicts() {
    const [ps, rj, sg] = await Promise.all([
      api.outfitsFor(itemId),
      api.rejectedFor(itemId),
      api.suggestionsFor(itemId).catch(() => [] as OutfitSuggestion[]),
    ]);
    setPartners(ps);
    setRejected(rj);
    setSuggestions(sg);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  async function remove() {
    const ok = await confirm({
      title: "Dit kledingstuk definitief verwijderen?",
      body: "De foto en alle beoordeelde combinaties met dit stuk verdwijnen mee. Dit kan niet ongedaan gemaakt worden.",
    });
    if (!ok) return;
    await api.deleteItem(itemId);
    navigate("/", { replace: true });
  }

  /** Withdraw my approval of one of this garment's combinations. */
  async function undoCombination(partner: OutfitPartner) {
    await api.resetPair(itemId, partner.item.id);
    await reloadVerdicts();
  }

  /** Withdraw my own "nee", so the pair is up for judging again. */
  async function undoRejection(partner: RejectedPartner) {
    await api.resetPair(itemId, partner.item.id);
    await reloadVerdicts();
  }

  /** Adopt a suggested outfit that includes this garment. */
  async function acceptSuggestion(suggestion: OutfitSuggestion) {
    await api.acceptSuggestion(suggestion.items.map((it) => it.id));
    await reloadVerdicts();
  }

  async function duplicate() {
    try {
      const copy = await api.duplicateItem(itemId);
      navigate(`/item/${copy.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dupliceren mislukt");
    }
  }

  const src = item ? photoUrl(item) : null;
  // Whether the current user may change this garment depends on their role in
  // the wardrobe it belongs to (viewers can only look and vote).
  const canEdit = item
    ? wardrobes.find((w) => w.id === item.wardrobe_id)?.can_edit ?? false
    : false;

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={() => navigate(-1)}>
          ← Terug
        </button>
        <h1>{editing ? "Bewerken" : "Kledingstuk"}</h1>
        {item && !editing && canEdit ? (
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
          // Two halves that stack on a phone and stand side by side on a wide
          // screen: the garment itself on the left, everything it is part of on
          // the right. Same order either way, so nothing moves about.
          <div className="stack detail-cols">
            <div className="stack detail-main">
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

            </div>
            <div className="stack detail-side">
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
                  <PartnerGrid partners={partners} anchor={item} onUndo={undoCombination} />
                )}
              </div>

              {rejected.length > 0 && (
                <div>
                  <h3 style={{ margin: "0 0 4px" }}>Past niet bij</h3>
                  <p className="muted" style={{ marginTop: 0, fontSize: "0.82rem" }}>
                    Afgekeurd, dus deze staan niet bij Outfits. Eén "nee" blokkeert een
                    combinatie, ook als iemand anders 'm goedkeurde.
                  </p>
                  <RejectedGrid rejected={rejected} onUndo={undoRejection} />
                </div>
              )}

              {suggestions.length > 0 && (
                <div>
                  <h3 style={{ margin: "0 0 4px" }}>✨ Suggesties van het systeem</h3>
                  <p className="muted" style={{ marginTop: 0, fontSize: "0.82rem" }}>
                    Automatisch samengesteld op kleur en seizoen, met dit stuk erin. Wat je al
                    hebt beoordeeld staat er niet tussen.
                  </p>
                  <SuggestionList suggestions={suggestions} onAccept={acceptSuggestion} />
                </div>
              )}

              {canEdit && (
                <>
                  <button className="btn-ghost btn-block" onClick={duplicate}>
                    ⧉ Dupliceren
                  </button>

                  <button className="btn-danger btn-block" onClick={remove}>
                    Verwijderen
                  </button>
                </>
              )}
            </div>
          </div>
        )}
        <AppFooter />
      </div>
      <BottomNav desktopOnly />
    </div>
  );
}
