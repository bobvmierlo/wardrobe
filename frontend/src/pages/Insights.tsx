import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, photoUrl } from "../api";
import { colorHex } from "../colors";
import AppFooter from "../components/AppFooter";
import OutfitStrip from "../components/OutfitStrip";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import type { Insights as InsightsData, Item } from "../types";

function Tile({ value, label }: { value: number; label: string }) {
  return (
    <div className="card stat-tile">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function Bars({ rows }: { rows: { label: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div>
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <span className="bar-label" title={row.label}>
            {row.label}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(row.count / max) * 100}%` }} />
          </span>
          <span className="bar-count">{row.count}</span>
        </div>
      ))}
    </div>
  );
}

/** A garment as a card with its photo, for the two lists at the bottom.
 *
 * Both of those used to be text: a row of names, or a row of tag-shaped
 * links. Neither is a way to decide anything about clothes — "Blauwe trui" is
 * not enough to know which one that is, let alone whether you want to keep
 * it, and both lists exist to be decided about. */
function ItemCard({ item }: { item: Item }) {
  const src = photoUrl(item, true);
  return (
    <Link className="card" to={`/item/${item.id}`} style={{ padding: 10 }}>
      {src ? (
        <img
          src={src}
          alt=""
          style={{ width: "100%", borderRadius: 10, aspectRatio: "1", objectFit: "cover" }}
        />
      ) : (
        // No photo: show the colour it is tagged with rather than a shrug.
        <div
          style={{
            width: "100%",
            borderRadius: 10,
            aspectRatio: "1",
            background: colorHex(item.color),
          }}
        />
      )}
      <div style={{ fontSize: "0.85rem", marginTop: 6 }}>{item.name}</div>
      <div className="muted" style={{ fontSize: "0.75rem" }}>
        {item.category}
      </div>
    </Link>
  );
}

/** "Inzichten": what is in the kast, what never leaves it, and — for anyone
 *  who keeps a wear log — what they actually wear. */
export default function Insights() {
  const { current } = useWardrobe();
  const currentId = current?.id;
  const [data, setData] = useState<InsightsData | null>(null);
  const [loading, setLoading] = useState(true);
  // A kast of two hundred can have fifty of these; showing all of them by
  // default buries the rest of the page under a wall of photos.
  const [showAllUnused, setShowAllUnused] = useState(false);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api
      .insights(currentId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [currentId]);

  return (
    <>
      <div className="topbar">
        <h1>Inzichten</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {loading && <div className="spinner" />}
        {data && (
          <>
            <div className="stat-grid">
              <Tile value={data.item_count} label="Kledingstukken" />
              <Tile value={data.outfit_count} label="Looks" />
              <Tile value={data.favorite_count} label="Favorieten" />
              <Tile value={data.unused_items.length} label="In geen look" />
            </div>

            {data.wear_log_enabled ? (
              <>
                <h2>Wat je draagt</h2>
                <div className="stat-grid">
                  <Tile value={data.total_wears} label="Keer een look gedragen" />
                </div>
                {data.most_worn.map((outfit) => (
                  <div className="card rec-card" key={outfit.id}>
                    <div className="rec-head">
                      <span className="rec-title">{outfit.name}</span>
                      <span className="rec-source">{outfit.wear_count}×</span>
                    </div>
                    <OutfitStrip items={outfit.items} size={56} />
                  </div>
                ))}
                {data.most_worn.length === 0 && (
                  <p className="muted">Nog niets afgevinkt — dat vult zich vanzelf.</p>
                )}
              </>
            ) : (
              <div className="notice" style={{ marginTop: 16 }}>
                Het draaglogboek staat uit, dus "wat draag je echt" kan de app niet zeggen.{" "}
                <Link to="/settings#draaglogboek">Aanzetten bij Instellingen</Link>.
              </div>
            )}

            {data.palette.length > 0 && (
              <>
                <h2>Kleuren in je kast</h2>
                {/* A colour is the one property a bar chart labelled in words
                    describes badly. The band shows the proportions at a glance;
                    the swatches below it give the numbers. */}
                <div className="palette-bar">
                  {data.palette.map((p) => (
                    <span
                      key={p.color}
                      title={`${p.color} · ${p.count}`}
                      style={{ background: colorHex(p.color), flex: p.count }}
                    />
                  ))}
                </div>
                <div className="swatch-grid" style={{ marginBottom: 8 }}>
                  {data.palette.map((p) => (
                    <span className="swatch" key={p.color}>
                      <span className="dot" style={{ background: colorHex(p.color) }} />
                      {p.color}
                      <span className="count">{p.count}</span>
                    </span>
                  ))}
                </div>
              </>
            )}

            {data.by_category.length > 0 && (
              <>
                <h2>Per categorie</h2>
                <Bars rows={data.by_category} />
              </>
            )}

            {data.by_occasion.length > 0 && (
              <>
                <h2>Per gelegenheid</h2>
                <Bars rows={data.by_occasion} />
              </>
            )}

            <h2>Opruimen</h2>
            <p className="muted" style={{ fontSize: "0.88rem", marginTop: 0 }}>
              {data.wear_log_enabled
                ? "Al lang niet gedragen, volgens je draaglogboek."
                : "Al een tijd in je kast en in geen enkele look — zonder draaglogboek is dit een inschatting, geen feit."}
            </p>
            {data.neglected.length === 0 ? (
              <p className="muted">Niets dat stof ligt te vangen. Mooi zo.</p>
            ) : (
              <div className="grid">
                {data.neglected.map((item) => (
                  <ItemCard item={item} key={item.id} />
                ))}
              </div>
            )}

            {data.unused_items.length > 0 && (
              <>
                <h2>
                  Nog in geen enkele look{" "}
                  <span className="muted" style={{ fontSize: "0.9rem", fontWeight: 400 }}>
                    · {data.unused_items.length}
                  </span>
                </h2>
                <p className="muted" style={{ fontSize: "0.88rem", marginTop: 0 }}>
                  Deze stukken hangen er wel, maar zitten in geen enkele opgeslagen look. Tik er
                  een aan om er alsnog iets mee te doen.
                </p>
                <div className="grid">
                  {data.unused_items.slice(0, showAllUnused ? undefined : 12).map((item) => (
                    <ItemCard item={item} key={item.id} />
                  ))}
                </div>
                {data.unused_items.length > 12 && (
                  <button
                    className="btn-ghost btn-block"
                    style={{ marginTop: 12 }}
                    onClick={() => setShowAllUnused((v) => !v)}
                  >
                    {showAllUnused
                      ? "Minder tonen"
                      : `Alle ${data.unused_items.length} tonen`}
                  </button>
                )}
              </>
            )}
          </>
        )}
        <AppFooter />
      </div>
    </>
  );
}
