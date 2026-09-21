import { useEffect, useState } from "react";
import AppFooter from "../components/AppFooter";
import TagPicker from "../components/TagPicker";
import { api } from "../api";
import { colorHex } from "../colors";
import type { StyleProfile } from "../types";

/** "Stijl-DNA": the colours and words you dress by.
 *
 * Two halves, and they are different in kind — which is why the screen says so
 * out loud instead of running them together.
 *
 * The **top half** the app reads: an outfit in your own palette, in the style
 * words you picked, is scored above one that merely matches the weather. A
 * preference, never a filter — a kast you share with someone whose taste
 * differs keeps working for both of you. See app/recommendations.py.
 *
 * The **bottom half** the app never reads. Necklines, silhouettes, fabrics,
 * the sentence you want in your head while getting dressed: none of that is
 * something the suggestion engine can see, and all of it is what you actually
 * want to look up when you are standing in a shop. So it is stored, shown
 * back, and never argued with.
 */
export default function StyleDna() {
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [colors, setColors] = useState<string[]>([]);
  const [styles, setStyles] = useState<string[]>([]);
  const [occasions, setOccasions] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [identity, setIdentity] = useState("");
  const [colorSeason, setColorSeason] = useState("");
  const [aesthetics, setAesthetics] = useState<string[]>([]);
  const [necklines, setNecklines] = useState<string[]>([]);
  const [silhouettes, setSilhouettes] = useState<string[]>([]);
  const [fabrics, setFabrics] = useState<string[]>([]);
  const [mantra, setMantra] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function adopt(p: StyleProfile) {
    setProfile(p);
    setColors(p.colors);
    setStyles(p.styles);
    setOccasions(p.occasions);
    setNotes(p.notes ?? "");
    setIdentity(p.identity ?? "");
    setColorSeason(p.color_season ?? "");
    setAesthetics(p.aesthetics);
    setNecklines(p.necklines);
    setSilhouettes(p.silhouettes);
    setFabrics(p.fabrics);
    setMantra(p.mantra ?? "");
  }

  useEffect(() => {
    api
      .styleProfile()
      .then(adopt)
      .catch((e) => setError(e instanceof Error ? e.message : "Ophalen mislukt"));
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.saveStyleProfile({
        colors,
        styles,
        occasions,
        notes,
        identity,
        color_season: colorSeason,
        aesthetics,
        necklines,
        silhouettes,
        fabrics,
        mantra,
      });
      adopt(updated);
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
          Jouw persoonlijke stijlprofiel. Het bovenste deel gebruikt de app om voorstellen te
          ordenen — outfits in jouw kleuren en jouw stijl komen bovenaan. Het onderste deel is
          naslag voor jezelf: dat leest de app niet, dat lees jij als je in een winkel staat. Alles
          hier geldt alleen voor jou, ook in een gedeelde kast.
        </p>

        {profile && (
          <>
            <div className="card" style={{ padding: 16, marginBottom: 16 }}>
              <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Wat de app meeweegt</h2>

              {/* The one picker on this page where the word is a worse
                  description of the option than the thing itself. */}
              <TagPicker
                label="Mijn kleuren"
                hint="De tinten waar je je prettig in voelt."
                options={profile.available_colors}
                value={colors}
                onChange={setColors}
                decorate={(color) => (
                  <span className="chip-dot" style={{ background: colorHex(color) }} />
                )}
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
              <div className="field" style={{ marginBottom: 0 }}>
                <label>Notities</label>
                <textarea
                  value={notes}
                  placeholder="Bijv. 'geen felle prints', 'liefst hoge taille'…"
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
            </div>

            <div className="card" style={{ padding: 16, marginBottom: 16 }}>
              <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Naslag voor jezelf</h2>
              <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
                Vrije tekst, in jouw eigen woorden. De app corrigeert hier niets en weegt hier
                niets mee — er is geen lijst met halslijnen waarmee 'ie jou zou kunnen
                tegenspreken.
              </p>

              <div className="dna-cols">
                <div className="field">
                  <label>Stijlidentiteit</label>
                  <input
                    value={identity}
                    placeholder="bijv. Modern, klassiek & elegant"
                    onChange={(e) => setIdentity(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label>Kleurseizoen</label>
                  <input
                    value={colorSeason}
                    placeholder="bijv. Warm & diep"
                    onChange={(e) => setColorSeason(e.target.value)}
                  />
                </div>
              </div>

              <TagPicker
                label="Overall aesthetic"
                hint="Eigen woorden voor het geheel — bijv. quiet luxury, feminien, tijdloos."
                options={[]}
                value={aesthetics}
                onChange={setAesthetics}
                allowCustom
              />
              <TagPicker
                label="Beste halslijnen"
                hint="bijv. V-hals, scoop neck, open kraag."
                options={[]}
                value={necklines}
                onChange={setNecklines}
                allowCustom
              />
              <TagPicker
                label="Beste silhouetten"
                hint="bijv. getailleerd, high-waist, rechte lijnen."
                options={[]}
                value={silhouettes}
                onChange={setSilhouettes}
                allowCustom
              />
              <TagPicker
                label="Stofkeuzes die bij je passen"
                hint="bijv. linnen, zijde, fijne breisels."
                options={[]}
                value={fabrics}
                onChange={setFabrics}
                allowCustom
              />

              <div className="field" style={{ marginBottom: 0 }}>
                <label>Persoonlijk mantra / notitie</label>
                <textarea
                  value={mantra}
                  placeholder="Waar je aan wilt denken als je jezelf kleedt…"
                  onChange={(e) => setMantra(e.target.value)}
                />
              </div>
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
