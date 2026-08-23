import { useEffect, useMemo, useRef, useState } from "react";
import { api, photoUrl } from "../api";
import {
  SEASONS,
  SIZE_KIND_LABELS,
  compareSizes,
  sizeKindForCategory,
  type Category,
  type Item,
  type SizeKind,
  type SizeOption,
} from "../types";
import PhotoEditor from "./PhotoEditor";
import ImportDialog, { type ImportResult } from "./ImportDialog";

const ALL_SEASONS = "Alle seizoenen";
// Sentinel option that switches the brand picker to free-text entry.
const NEW_BRAND = "__new__";

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
  const [brands, setBrands] = useState<string[]>([]);
  // Typing a brand by hand instead of picking an existing one.
  const [brandNew, setBrandNew] = useState(false);
  const [editorSrc, setEditorSrc] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]));
    api.listSizes().then(setSizes).catch(() => setSizes([]));
    // Brands already in use, so Merk is normally a pick from a list instead of
    // retyping (and misspelling) the same brand on every garment.
    api.listBrands().then(setBrands).catch(() => setBrands([]));
  }, []);

  // Include a legacy free-text value so an existing item stays selectable.
  const categoryOptions = useMemo(() => {
    const names = categories.map((c) => c.name);
    if (category && !names.includes(category)) return [category, ...names];
    return names;
  }, [categories, category]);
  // Group sizes by kind, with the group most relevant to the chosen category
  // first, so shoes show EU numbers and hats show One-size up top.
  const sizeGroups = useMemo(() => {
    // Once a category is chosen, only show the sizes for its kind (shoes show
    // EU numbers, accessories show One-size); with no category yet, show all.
    const preferred = category ? sizeKindForCategory(category) : null;
    const order: SizeKind[] = ["clothing", "shoes", "accessory"];
    const groups = order
      .filter((kind) => preferred === null || kind === preferred)
      .map((kind) => ({ kind, items: sizes.filter((s) => s.kind === kind).sort(compareSizes) }))
      .filter((g) => g.items.length > 0);
    // Keep a legacy free-text value selectable even if it's no longer in the list.
    const known = sizes.some((s) => s.label === size);
    return { groups, legacy: size && !known ? size : null };
  }, [sizes, size, category]);

  // Brands to pick from, including the current value when it isn't a known
  // brand yet (an existing item's brand, or one filled in by the webshop
  // import), so the picker can always show what is selected.
  const brandOptions = useMemo(() => {
    const chosen = brand.trim();
    const known = brands.some((b) => b.toLowerCase() === chosen.toLowerCase());
    const list = chosen && !known ? [...brands, chosen] : [...brands];
    return list.sort((a, b) => a.localeCompare(b, "nl", { sensitivity: "base" }));
  }, [brand, brands]);

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
    <>
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
          <img src={preview} alt="" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
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
          {/* Pick from the brands already in use — a native <select> gives a
              proper picker on mobile. Anyone (not just an admin) can add a
              brand by choosing "Nieuw merk" and typing it. */}
          {brandNew || brandOptions.length === 0 ? (
            <>
              <input
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="bijv. Ralph Lauren"
                autoComplete="off"
                autoFocus={brandNew}
              />
              {brandOptions.length > 0 && (
                <button
                  type="button"
                  className="btn-ghost"
                  style={{ marginTop: 8, padding: "8px 12px", fontSize: "0.82rem" }}
                  onClick={() => { setBrand(""); setBrandNew(false); }}
                >
                  ← Kies uit de lijst
                </button>
              )}
            </>
          ) : (
            <select
              value={brand}
              onChange={(e) => {
                if (e.target.value === NEW_BRAND) {
                  setBrand("");
                  setBrandNew(true);
                } else {
                  setBrand(e.target.value);
                }
              }}
            >
              <option value="">—</option>
              {brandOptions.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
              <option value={NEW_BRAND}>➕ Nieuw merk…</option>
            </select>
          )}
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
          {sizeGroups.legacy && <option value={sizeGroups.legacy}>{sizeGroups.legacy}</option>}
          {sizeGroups.groups.map((g) => (
            <optgroup key={g.kind} label={SIZE_KIND_LABELS[g.kind]}>
              {g.items.map((s) => (
                <option key={s.id} value={s.label}>{s.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Seizoen (meerdere mogelijk)</label>
        <div className="chips wrap">
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
    </form>

    {/* Modals live OUTSIDE the form: an <ImportDialog> renders its own <form>,
        and a nested form makes the browser submit the outer one (navigating to
        /add?) instead of running the click handler. */}
    {editorSrc && (
      <PhotoEditor src={editorSrc} onCancel={() => setEditorSrc(null)} onApply={applyCrop} />
    )}
    {showImport && (
      <ImportDialog onCancel={() => setShowImport(false)} onImport={applyImport} />
    )}
    </>
  );
}
