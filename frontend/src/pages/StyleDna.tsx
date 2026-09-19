import { useEffect, useState } from "react";
import AppFooter from "../components/AppFooter";
import TagPicker from "../components/TagPicker";
import { api } from "../api";
import type { StyleProfile } from "../types";

/** "Stijl-DNA": the colours and words you dress by.
 *
 * A preference, never a filter — an outfit in your own palette scores higher,
 * but a kast you share with someone whose taste differs keeps working for
 * both of you. See app/recommendations.py. */
export default function StyleDna() {
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [colors, setColors] = useState<string[]>([]);
  const [styles, setStyles] = useState<string[]>([]);
  const [occasions, setOccasions] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .styleProfile()
      .then((p) => {
        setProfile(p);
        setColors(p.colors);
        setStyles(p.styles);
        setOccasions(p.occasions);
        setNotes(p.notes ?? "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Ophalen mislukt"));
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.saveStyleProfile({ colors, styles, occasions, notes });
      setProfile(updated);
      setColors(updated.colors);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="topbar">
        <h1>Stijl-DNA</h1>
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}
        <p className="muted" style={{ marginTop: 0, fontSize: "0.9rem" }}>
          Waar voel jij je goed in? De app gebruikt dit om voorstellen te ordenen — outfits in jouw
          kleuren en jouw stijl komen bovenaan. Het filtert nooit iets weg, en het geldt alleen voor
          jou, ook in een gedeelde kast.
        </p>

        {profile && (
          <>
            <TagPicker
              label="Mijn kleuren"
              hint="De tinten waar je je prettig in voelt."
              options={profile.available_colors}
              value={colors}
              onChange={setColors}
            />
            <TagPicker
              label="Mijn stijlwoorden"
              options={profile.available_styles}
              value={styles}
              onChange={setStyles}
              allowCustom
            />
            <TagPicker
              label="Waar kleed ik me meestal voor?"
              options={profile.available_occasions}
              value={occasions}
              onChange={setOccasions}
            />
            <div className="field">
              <label>Notities</label>
              <textarea
                value={notes}
                placeholder="Bijv. 'geen felle prints', 'liefst hoge taille'…"
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            <button className="btn-primary btn-block" onClick={save} disabled={busy}>
              {busy ? "Bezig…" : saved ? "✓ Opgeslagen" : "Opslaan"}
            </button>
          </>
        )}
        <AppFooter />
      </div>
    </>
  );
}
