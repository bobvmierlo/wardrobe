import { useState } from "react";
import { api } from "../api";
import type { ScrapeResult } from "../types";

export interface ImportResult {
  name?: string;
  brand?: string;
  color?: string;
  notes?: string;
  imageUrl?: string;
}

export interface ImportDialogProps {
  onCancel: () => void;
  onImport: (result: ImportResult) => void;
}

/**
 * Fetches product data from a webshop URL. The user picks one of the found
 * images and the fields are handed back to the form for editing before saving.
 */
export default function ImportDialog({ onCancel, onImport }: ImportDialogProps) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ScrapeResult | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);

  async function fetchData(e: React.FormEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.scrape(url.trim());
      setChosen(res.images[0] ?? null);
      if (!res.name && !res.brand && res.images.length === 0) {
        // Fetched fine, but the page exposed nothing we could use.
        setData(null);
        setError("Geen productgegevens gevonden op deze pagina. Vul de gegevens handmatig in.");
      } else {
        setData(res);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ophalen mislukt");
    } finally {
      setBusy(false);
    }
  }

  function confirm() {
    if (!data) return;
    onImport({
      name: data.name ?? undefined,
      brand: data.brand ?? undefined,
      color: data.color ?? undefined,
      notes: data.price ? `Prijs: ${data.price}` : undefined,
      imageUrl: chosen ?? undefined,
    });
  }

  return (
    <div className="editor-backdrop" role="dialog" aria-modal="true">
      <div className="editor-panel">
        <div className="row spread" style={{ marginBottom: 12 }}>
          <strong>Importeren uit webshop</strong>
          <button type="button" className="btn-ghost" onClick={onCancel}>Sluiten</button>
        </div>

        <form onSubmit={fetchData} className="row" style={{ gap: 8 }}>
          <input
            type="url"
            placeholder="https://webshop.nl/product/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoCapitalize="none"
          />
          <button type="submit" className="btn-primary" disabled={busy} style={{ flex: "none" }}>
            {busy ? "…" : "Ophalen"}
          </button>
        </form>

        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}

        {data && (
          <div className="stack" style={{ marginTop: 14 }}>
            {(data.name || data.brand) && (
              <div className="card" style={{ padding: 12 }}>
                {data.name && <div style={{ fontWeight: 700 }}>{data.name}</div>}
                {data.brand && <div className="muted" style={{ fontSize: "0.85rem" }}>{data.brand}</div>}
                {data.price && <div className="muted" style={{ fontSize: "0.85rem" }}>{data.price}</div>}
              </div>
            )}

            {data.images.length > 0 ? (
              <>
                <label>Kies een foto</label>
                <div className="import-grid">
                  {data.images.map((img) => (
                    <button
                      type="button"
                      key={img}
                      className={`import-thumb ${chosen === img ? "sel" : ""}`}
                      onClick={() => setChosen(img)}
                    >
                      <img src={img} alt="" loading="lazy" />
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Geen foto gevonden op deze pagina — je kunt er na het overnemen zelf één toevoegen.
              </p>
            )}

            <button type="button" className="btn-primary btn-block" onClick={confirm}>
              Overnemen &amp; bewerken
            </button>
            <p className="muted center" style={{ fontSize: "0.78rem" }}>
              Je kunt alle gegevens hierna nog aanpassen voor je opslaat.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
