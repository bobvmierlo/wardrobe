import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, photoUrl } from "../api";
import AppFooter from "../components/AppFooter";
import OutfitStrip from "../components/OutfitStrip";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { useWardrobe } from "../wardrobe";
import type { Insights as InsightsData } from "../types";

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

/** "Inzichten": what is in the kast, what never leaves it, and — for anyone
 *  who keeps a wear log — what they actually wear. */
export default function Insights() {
  const { current } = useWardrobe();
  const currentId = current?.id;
  const [data, setData] = useState<InsightsData | null>(null);
  const [loading, setLoading] = useState(true);

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
                <Bars rows={data.palette.map((p) => ({ label: p.color, count: p.count }))} />
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
                  <Link className="card" to={`/item/${item.id}`} key={item.id} style={{ padding: 10 }}>
                    {photoUrl(item, true) ? (
                      <img
                        src={photoUrl(item, true)!}
                        alt=""
                        style={{ width: "100%", borderRadius: 10, aspectRatio: "1", objectFit: "cover" }}
                      />
                    ) : (
                      <div className="center" style={{ fontSize: "1.8rem" }}>
                        👕
                      </div>
                    )}
                    <div style={{ fontSize: "0.85rem", marginTop: 6 }}>{item.name}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {item.category}
                    </div>
                  </Link>
                ))}
              </div>
            )}

            {data.unused_items.length > 0 && (
              <>
                <h2>Nog in geen enkele look</h2>
                <div className="chips wrap">
                  {data.unused_items.slice(0, 40).map((item) => (
                    <Link className="tag" to={`/item/${item.id}`} key={item.id}>
                      {item.name}
                    </Link>
                  ))}
                </div>
              </>
            )}
          </>
        )}
        <AppFooter />
      </div>
    </>
  );
}
