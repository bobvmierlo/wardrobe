import { useEffect, useMemo, useRef, useState } from "react";
import { api, photoUrl } from "../api";
import { SEASONS, type Category, type Item, type SizeOption } from "../types";
import PhotoEditor from "./PhotoEditor";
import ImportDialog, { type ImportResult } from "./ImportDialog";

const ALL_SEASONS = "Alle seizoenen";

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
  const [seasons, setSeasons] = useState<string[]>(initial?.seasons ?? []);
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [favorite, setFavorite] = useState(initial?.is_favorite ?? false);

  const [file, setFile] = useState<File | null>(null);
  const [photoRemoteUrl, setPhotoRemoteUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(initial ? photoUrl(initial) : null);

  const [categories, setCategories] = useState<Category[]>([]);
  const [sizes, setSizes] = useState<SizeOption[]>([]);
  const [editorSrc, setEditorSrc] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]));
    api.listSizes().then(setSizes).catch(() => setSizes([]));
  }, []);

  // Include a legacy free-text value so an existing item stays selectable.
  const categoryOptions = useMemo(() => {
    const names = categories.map((c) => c.name);
    if (category && !names.includes(category)) return [category, ...names];
    return names;
  }, [categories, category]);
  const sizeOptions = useMemo(() => {
    const labels = sizes.map((s) => s.label);
    if (size && !labels.includes(size)) return [size, ...labels];
    return labels;
  }, [sizes, size]);

  // A preview is croppable when it's a fresh file or a same-origin stored photo.
  const canEditPhoto = !!preview && (file != null || preview.startsWith("/") || preview.startsWith("blob:"));

  function pickFile(f: File | null) {
    if (!f) return;
    const url = URL.createObjectURL(f);
    setFile(f);
    setPhotoRemoteUrl(null);
    setPreview(url);
    setEditorSrc(url); // jump straight into crop/rotate
  }

  function applyCrop(blob: Blob) {
    const cropped = new File([blob], "photo.jpg", { type: "image/jpeg" });
    const url = URL.createObjectURL(cropped);
    setFile(cropped);
    setPhotoRemoteUrl(null);
    setPreview(url);
    setEditorSrc(null);
  }

  function applyImport(res: ImportResult) {
    if (res.name) setName(res.name);
    if (res.brand) setBrand(res.brand);
    if (res.color) setColor(res.color);
    if (res.notes) setNotes((n) => (n ? n : res.notes!));
    if (res.imageUrl) {
      setFile(null);
      setPhotoRemoteUrl(res.imageUrl);
      setPreview(res.imageUrl);
    }
    setShowImport(false);
  }

  function toggleSeason(s: string) {
    setSeasons((cur) => {
      if (s === ALL_SEASONS) return cur.includes(s) ? [] : [ALL_SEASONS];
      const next = cur.filter((x) => x !== ALL_SEASONS);
      return next.includes(s) ? next.filter((x) => x !== s) : [...next, s];
    });
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
    form.set("season", seasons.join(","));
    form.set("notes", notes);
    form.set("is_favorite", favorite ? "true" : "false");
    if (file) form.set("photo", file);
    else if (photoRemoteUrl) form.set("photo_url", photoRemoteUrl);
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

      <button type="button" className="btn-ghost" onClick={() => setShowImport(true)}>
        🔗 Importeren uit webshop
      </button>

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
        <div className="row" style={{ gap: 10 }}>
          <button type="button" className="btn-ghost" style={{ flex: 1 }} onClick={() => fileRef.current?.click()}>
            Andere foto
          </button>
          <button
            type="button"
            className="btn-ghost"
            style={{ flex: 1 }}
            disabled={!canEditPhoto}
            title={canEditPhoto ? "" : "Bijsnijden kan alleen voor een eigen foto"}
            onClick={() => preview && setEditorSrc(preview)}
          >
            ✂️ Bijsnijden / draaien
          </button>
        </div>
      )}

      <div className="field">
        <label>Naam *</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="bijv. Donkerblauwe polo" required />
      </div>

      <div className="field">
        <label>Categorie *</label>
        <select value={category} onChange={(e) => setCategory(e.target.value)} required>
          <option value="" disabled>Kies een categorie…</option>
          {categoryOptions.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
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

      <div className="field">
        <label>Maat</label>
        <select value={size} onChange={(e) => setSize(e.target.value)}>
          <option value="">—</option>
          {sizeOptions.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Seizoen (meerdere mogelijk)</label>
        <div className="chips" style={{ overflowX: "visible", flexWrap: "wrap", marginBottom: 0 }}>
          {SEASONS.map((s) => (
            <button
              type="button"
              key={s}
              className={`chip ${seasons.includes(s) ? "active" : ""}`}
              onClick={() => toggleSeason(s)}
            >
              {s}
            </button>
          ))}
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

      {editorSrc && (
        <PhotoEditor src={editorSrc} onCancel={() => setEditorSrc(null)} onApply={applyCrop} />
      )}
      {showImport && (
        <ImportDialog onCancel={() => setShowImport(false)} onImport={applyImport} />
      )}
    </form>
  );
}
