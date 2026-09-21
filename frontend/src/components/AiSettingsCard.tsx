import { useEffect, useState } from "react";
import { api } from "../api";
import { useConfirm } from "../confirm";
import type { AiSettings, AiUsage } from "../types";

/** Thousandths of a dollar cent as something a person reads.
 *
 * Kept that small on the wire because one tagging run on a small kast costs
 * well under a cent, and rounding those to whole cents would make every row
 * read "€0,00" — which is exactly the number somebody switching this on wants
 * to be able to trust. So: tenths of a cent while it is tiny, cents after.
 * Shown in dollars because that is what Anthropic bills in. */
function money(millicents: number): string {
  const dollars = millicents / 100_000;
  if (millicents === 0) return "$0";
  if (dollars < 0.01) return `< $0,01`;
  if (dollars < 1) return `$${dollars.toFixed(2).replace(".", ",")}`;
  return `$${dollars.toFixed(2).replace(".", ",")}`;
}

function thousands(n: number): string {
  return n.toLocaleString("nl-NL");
}

/** De AI-laag, te bedienen door een beheerder zonder aan een compose-bestand
 *  te komen — inclusief hoe je aan een sleutel komt, want dat is de vraag die
 *  je krijgt zodra je zo'n schakelaar ergens neerzet. */
export default function AiSettingsCard() {
  const confirm = useConfirm();
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [detail, setDetail] = useState(false);
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
    // Separate request, and a failure is silent: the meter is worth showing
    // when it works, and never worth hiding the settings over.
    api
      .aiUsage()
      .then(setUsage)
      .catch(() => setUsage(null));
  }, []);

  async function clearMeter() {
    const ok = await confirm({
      title: "Verbruiksteller wissen?",
      body:
        "Het overzicht begint weer bij nul. Dit raakt verder niets — geen kleding, geen looks —" +
        " en het verandert niets aan wat er bij Anthropic op je rekening staat.",
      confirmLabel: "Wissen",
      danger: true,
    });
    if (!ok) return;
    try {
      setUsage(await api.clearAiUsage());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wissen mislukt");
    }
  }

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

      {/* What it has actually cost. This is the only feature in the app that
          spends money, and it spends the money of whoever put the key in — so
          the switch that bills per press says how often it was pressed. */}
      {usage && (
        <>
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0" }} />
          <h4 style={{ margin: "0 0 6px" }}>Verbruik</h4>
          {usage.calls === 0 ? (
            <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
              Er is nog geen enkel verzoek naar de AI-dienst gegaan. Zolang je de knoppen met AI
              niet gebruikt, blijft dat zo — en kost dit dus niets.
            </p>
          ) : (
            <>
              <div className="stat-grid" style={{ marginTop: 10 }}>
                <div className="card stat-tile">
                  <div className="stat-value">{thousands(usage.calls)}</div>
                  <div className="stat-label">Verzoeken</div>
                </div>
                <div className="card stat-tile">
                  <div className="stat-value">{money(usage.cost_millicents)}</div>
                  <div className="stat-label">Totaal (schatting)</div>
                </div>
                <div className="card stat-tile">
                  <div className="stat-value">{money(usage.month_cost_millicents)}</div>
                  <div className="stat-label">Laatste 30 dagen</div>
                </div>
              </div>

              <p className="muted" style={{ fontSize: "0.78rem", margin: "10px 0 0" }}>
                {thousands(usage.input_tokens)} tokens erheen, {thousands(usage.output_tokens)}{" "}
                terug. Het bedrag is <strong>een schatting</strong>: het is onze eigen rekensom op
                de gepubliceerde tarieven (overgenomen in {usage.prices_as_of}), niet je factuur.
                Die staat op{" "}
                <a
                  href="https://platform.claude.com/settings/usage"
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  platform.claude.com
                </a>
                .
                {usage.partial &&
                  " Er zitten verzoeken bij met een model waarvan we het tarief niet kennen," +
                    " dus het werkelijke bedrag ligt hoger."}
              </p>

              <button
                className="btn-ghost btn-block"
                style={{ marginTop: 10 }}
                onClick={() => setDetail((open) => !open)}
                aria-expanded={detail}
              >
                {detail ? "Uitsplitsing verbergen" : "Waar ging het heen?"}
              </button>

              {detail && (
                <>
                  <div className="meter-rows">
                    {usage.by_purpose.map((line) => (
                      <div className="meter-row" key={`p-${line.label}`}>
                        <span>{line.label}</span>
                        <span className="meter-value">
                          {thousands(line.calls)}× · {money(line.cost_millicents)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <h5 style={{ margin: "14px 0 0", fontSize: "0.8rem", color: "var(--muted)" }}>
                    Per model
                  </h5>
                  <div className="meter-rows">
                    {usage.by_model.map((line) => (
                      <div className="meter-row" key={`m-${line.label}`}>
                        <span>{line.label}</span>
                        <span className="meter-value">
                          {thousands(line.calls)}× ·{" "}
                          {line.partial ? "tarief onbekend" : money(line.cost_millicents)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <button className="btn-ghost btn-block" style={{ marginTop: 12 }} onClick={clearMeter}>
                    Teller wissen
                  </button>
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
