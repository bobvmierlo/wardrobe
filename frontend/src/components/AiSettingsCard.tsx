import { useEffect, useState } from "react";
import { api } from "../api";
import type { AiSettings } from "../types";

/** De AI-laag, te bedienen door een beheerder zonder aan een compose-bestand
 *  te komen — inclusief hoe je aan een sleutel komt, want dat is de vraag die
 *  je krijgt zodra je zo'n schakelaar ergens neerzet. */
export default function AiSettingsCard() {
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    api
      .aiSettings()
      .then(setAi)
      .catch(() => setAi(null));
  }, []);

  async function save(changes: Parameters<typeof api.saveAiSettings>[0], said: string) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      setAi(await api.saveAiSettings(changes));
      setNote(said);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Opslaan mislukt");
    } finally {
      setBusy(false);
    }
  }

  if (!ai) return null;

  const locked = (field: string) => ai.locked.includes(field);
  const anyLocked = ai.locked.length > 0;

  return (
    <div className="card" id="ai" style={{ padding: 16, scrollMarginTop: 80 }}>
      <h3 style={{ marginTop: 0 }}>AI (optioneel)</h3>
      <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
        De app doet het aanvullen van tags en het samenstellen van looks gewoon zelf, met de
        kleurregels van deze installatie. Zet je dit aan, dan komt daar een taalmodel bovenop dat
        looks samenstelt en tags invult waar de regels niets zeggen — maar wat jullie hebben
        afgekeurd blijft afgekeurd, dat dwingt de app af.
      </p>
      <p className="muted" style={{ fontSize: "0.82rem" }}>
        Hiervoor gaan naam, categorie, kleur, maat en seizoen van kledingstukken naar Anthropic.
        Geen foto's, geen namen van personen. Het kost geld per gebruik — zie de uitleg hieronder.
      </p>

      {error && <div className="error">{error}</div>}
      {note && <div className="notice">{note}</div>}

      {anyLocked && (
        <div className="notice">
          Sommige velden staan vast in de omgeving van de server (
          {ai.locked.map((f) => f.toUpperCase().replace("AI_", "WARDROBE_AI_")).join(", ")}). Die
          pas je daar aan, niet hier.
        </div>
      )}

      <label className="row" style={{ gap: 10, cursor: locked("ai_enabled") ? "default" : "pointer" }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={ai.enabled}
          disabled={busy || locked("ai_enabled")}
          onChange={(e) =>
            save({ enabled: e.target.checked }, e.target.checked ? "AI staat aan." : "AI staat uit.")
          }
        />
        <span>AI-laag aanzetten</span>
      </label>
      {ai.enabled && !ai.key_set && (
        <p className="muted" style={{ fontSize: "0.8rem", margin: "6px 0 0" }}>
          Staat aan, maar er is nog geen sleutel — de knoppen met AI blijven daardoor verborgen.
        </p>
      )}

      <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />

      <h4 style={{ margin: "0 0 6px" }}>API-sleutel</h4>
      <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
        {ai.key_set
          ? `Er staat een sleutel (${ai.key_hint}). Je kunt 'm vervangen, niet uitlezen — ook niet als beheerder.`
          : "Nog geen sleutel ingesteld."}
      </p>
      {!locked("ai_api_key") && (
        <>
          <div className="row" style={{ gap: 8 }}>
            <input
              type="password"
              value={key}
              placeholder="sk-ant-…"
              autoComplete="off"
              onChange={(e) => setKey(e.target.value)}
            />
            <button
              className="btn-primary"
              style={{ flex: "none" }}
              disabled={busy || !key.trim()}
              onClick={() => {
                save({ api_key: key.trim() }, "Sleutel opgeslagen.");
                setKey("");
              }}
            >
              Opslaan
            </button>
          </div>
          {ai.key_set && (
            <button
              className="btn-ghost btn-block"
              style={{ marginTop: 8 }}
              disabled={busy}
              onClick={() => save({ api_key: "" }, "Sleutel gewist.")}
            >
              Sleutel wissen
            </button>
          )}
        </>
      )}

      <button
        className="btn-ghost btn-block"
        style={{ marginTop: 10 }}
        onClick={() => setHelp((open) => !open)}
        aria-expanded={help}
      >
        {help ? "Uitleg verbergen" : "Hoe kom ik aan een API-sleutel?"}
      </button>

      {help && (
        <div
          style={{
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "12px 14px",
            marginTop: 10,
            fontSize: "0.85rem",
            lineHeight: 1.6,
          }}
        >
          <ol style={{ margin: 0, paddingLeft: 18 }}>
            <li>
              Maak een account aan op{" "}
              <a href="https://platform.claude.com" target="_blank" rel="noreferrer noopener">
                platform.claude.com
              </a>
              . Dat is een <strong>ontwikkelaarsaccount</strong> en staat los van een
              Claude-abonnement — een betaald abonnement geeft je dus géén sleutel.
            </li>
            <li>
              Zet er tegoed op onder{" "}
              <a
                href="https://platform.claude.com/settings/billing"
                target="_blank"
                rel="noreferrer noopener"
              >
                Billing
              </a>
              . Je betaalt per gebruik; zonder tegoed werkt de sleutel niet.
            </li>
            <li>
              Maak een sleutel onder{" "}
              <a
                href="https://platform.claude.com/settings/keys"
                target="_blank"
                rel="noreferrer noopener"
              >
                API keys
              </a>
              . Hij begint met <code>sk-ant-</code> en is daarna <strong>nooit meer te zien</strong>
              , dus kopieer 'm meteen hierheen.
            </li>
            <li>
              Zet een uitgavenlimiet onder{" "}
              <a
                href="https://platform.claude.com/settings/limits"
                target="_blank"
                rel="noreferrer noopener"
              >
                Limits
              </a>
              . Aan te raden: dit is jouw sleutel en jouw rekening.
            </li>
          </ol>
          <p className="muted" style={{ marginBottom: 0 }}>
            Wat het kost hangt af van het model en hoe groot je kast is. Een kast van tweehonderd
            stuks laten taggen is één verzoek; de tarieven per model staan op{" "}
            <a
              href="https://platform.claude.com/docs/en/about-claude/pricing"
              target="_blank"
              rel="noreferrer noopener"
            >
              de prijzenpagina
            </a>
            . Kies hieronder een goedkoper model als je het scherp wilt houden — dit is invulwerk,
            geen redeneerwerk.
          </p>
        </div>
      )}

      <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />

      <div className="field">
        <label>Model</label>
        <select
          value={ai.model}
          disabled={busy || locked("ai_model")}
          onChange={(e) => save({ model: e.target.value }, "Model gewijzigd.")}
        >
          {ai.models.some((m) => m.value === ai.model) ? null : (
            <option value={ai.model}>{ai.model} (uit de omgeving)</option>
          )}
          {ai.models.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="field" style={{ marginBottom: 0 }}>
        <label>Hoeveel denkwerk</label>
        <select
          value={ai.effort}
          disabled={busy || locked("ai_effort")}
          onChange={(e) => save({ effort: e.target.value }, "Effort gewijzigd.")}
        >
          {ai.efforts.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <p className="muted" style={{ fontSize: "0.78rem", margin: "6px 0 0" }}>
          Hoger kost meer en levert hier weinig op: tags invullen en outfits samenstellen is geen
          redeneerwerk. "low" is de standaard.
        </p>
      </div>
    </div>
  );
}
