import { useRef, useState } from "react";
import { photoUrl } from "../api";
import { CATEGORIES, SEASONS, type Item } from "../types";

export interface ItemFormProps {
  initial?: Item;
  submitLabel: string;
  onSubmit: (form: FormData) => Promise<void>;
}

export default function ItemForm({ initial, submitLabel, onSubmit }: ItemFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [brand, setBrand] = useState(initial?.brand ?? "");
  const [color, setColor] = useState(initial?.color ?? "");
  const [size, setSize] = useState(initial?.size ?? "");
  const [season, setSeason] = useState(initial?.season ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [favorite, setFavorite] = useState(initial?.is_favorite ?? false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(initial ? photoUrl(initial) : null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function pickFile(f: File | null) {
    setFile(f);
    if (f) setPreview(URL.createObjectURL(f));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !category.trim()) {
      setError("Naam en categorie zijn verplicht.");
      return;
    }
    setError(null);
    setBusy(true);
    const form = new FormData();
    form.set("name", name.trim());
    form.set("category", category.trim());
    form.set("brand", brand);
    form.set("color", color);
    form.set("size", size);
    form.set("season", season);
    form.set("notes", notes);
    form.set("is_favorite", favorite ? "true" : "false");
    if (file) form.set("photo", file);
    try {
      await onSubmit(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Opslaan mislukt");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="stack">
      {error && <div className="error">{error}</div>}

      <div
        className="card"
        style={{ aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}
        onClick={() => fileRef.current?.click()}
      >
        {preview ? (
          <img src={preview} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div className="center muted">
            <div style={{ fontSize: "2.6rem" }}>📷</div>
            <div>Foto maken of kiezen</div>
          </div>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
      />
      {preview && (
        <button type="button" className="btn-ghost" onClick={() => fileRef.current?.click()}>
          Andere foto kiezen
        </button>
      )}

      <div className="field">
        <label>Naam *</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="bijv. Donkerblauwe polo" required />
      </div>

      <div className="field">
        <label>Categorie *</label>
        <input
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Kies of typ…"
          list="category-list"
          required
        />
        <datalist id="category-list">
          {CATEGORIES.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </div>

      <div className="row" style={{ gap: 10 }}>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Merk</label>
          <input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="bijv. Ralph Lauren" />
        </div>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Kleur</label>
          <input value={color} onChange={(e) => setColor(e.target.value)} placeholder="bijv. Donkerblauw" />
        </div>
      </div>

      <div className="row" style={{ gap: 10 }}>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Maat</label>
          <input value={size} onChange={(e) => setSize(e.target.value)} placeholder="bijv. L" />
        </div>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Seizoen</label>
          <select value={season} onChange={(e) => setSeason(e.target.value)}>
            <option value="">—</option>
            {SEASONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="field">
        <label>Notities</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Extra info…" />
      </div>

      <label className="row" style={{ gap: 10, cursor: "pointer" }}>
        <input type="checkbox" style={{ width: "auto" }} checked={favorite} onChange={(e) => setFavorite(e.target.checked)} />
        <span>★ Markeer als favoriet</span>
      </label>

      <button className="btn-primary btn-block" disabled={busy}>
        {busy ? "Bezig…" : submitLabel}
      </button>
    </form>
  );
}
