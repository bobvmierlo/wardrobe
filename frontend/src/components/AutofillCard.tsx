import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useConfirm } from "../confirm";
import type { AutofillPreview, TaggedItem } from "../types";

interface Props {
  wardrobeId: number;
  /** Called after something was written, so the page can reload itself. */
  onChanged: () => void;
}

const COUNTS = [5, 10, 20];
//: How many the preview looks ahead for. The dropdown never offers more, so
//: "er zijn er N te maken" is never an undercount of what a press would do.
const MAX_PREVIEW = 20;

/** "Laat de app je kast aanvullen" — for a wardrobe that has been in use for
 *  a year with nothing tagged and no looks saved.
 *
 *  Both actions are on request, neither overwrites anything, and both say what
 *  they are about to do before they do it. See app/autofill.py for the rules. */
export default function AutofillCard({ wardrobeId, onChanged }: Props) {
  const confirm = useConfirm();
  const [preview, setPreview] = useState<AutofillPreview | null>(null);
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState<"tags" | "looks" | null>(null);
  const [useAi, setUseAi] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [examples, setExamples] = useState<TaggedItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Deliberately not keyed on `count`: working out what is composable runs the
  // same generator the button does, and the count only decides how many of them
  // get saved. Re-running that on every twiddle of a dropdown is work nobody
  // asked for, on the one screen a large kast opens most.
  const load = useCallback(() => {
    api
      .autofillPreview(wardrobeId, MAX_PREVIEW)
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [wardrobeId]);

  useEffect(() => {
    load();
  }, [load]);

  async function fillTags() {
    setError(null);
    setBusy("tags");
    try {
      // Ask first, showing what it found — this touches every garment in the
      // kast, and "wat gaat dit doen?" deserves an answer before the fact.
      const dry = await api.autofillTags(wardrobeId, true, useAi);
      if (dry.tagged === 0) {
        setResult("Niets aan te vullen — alles heeft al tags, of de categorie zegt te weinig.");
        setExamples([]);
        return;
      }
      const ok = await confirm({
        title: `${dry.tagged} kledingstuk(ken) tags geven?`,
        body:
          "De app vult alleen lege velden in, afgeleid van de categorie en de naam.\n" +
          "Wat je zelf hebt ingevuld blijft staan, en je kunt elk stuk daarna gewoon aanpassen.",
        confirmLabel: "Aanvullen",
        danger: false,
      });
      if (!ok) return;

      const done = await api.autofillTags(wardrobeId, false, useAi);
      setResult(
        `${done.tagged} kledingstuk(ken) aangevuld${
          done.by_ai ? `, waarvan ${done.by_ai} met AI` : ""
        }.${done.ai_note ? ` ${done.ai_note}` : ""}`,
      );
      setExamples(done.examples);
      load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Aanvullen mislukt");
    } finally {
      setBusy(null);
    }
  }

  async function composeLooks() {
    setError(null);
    setBusy("looks");
    try {
      const done = await api.autofillLooks(wardrobeId, count, useAi);
      setResult(
        done.created.length
          ? `${done.created.length} look(s) samengesteld${
              done.by_ai ? `, waarvan ${done.by_ai} door de AI` : ""
            }.${done.note ? ` ${done.note}` : ""}${done.ai_note ? ` ${done.ai_note}` : ""}`
          : (done.note ?? "Geen nieuwe combinaties gevonden."),
      );
      setExamples([]);
      load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Samenstellen mislukt");
    } finally {
      setBusy(null);
    }
  }

  if (!preview || preview.item_count === 0) return null;

  const nothingToDo = preview.taggable === 0 && preview.composable === 0;

  return (
    <div className="card" style={{ padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>Je kast laten aanvullen</h3>
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
        Voor een kast die al een tijd in gebruik is. De app leidt af wat 'ie kan — en verzint
        niets: lege velden worden ingevuld, ingevulde velden blijven met rust.
      </p>

      {error && <div className="error">{error}</div>}
      {result && <div className="notice">{result}</div>}

      {examples.length > 0 && (
        <ul className="muted" style={{ fontSize: "0.82rem", lineHeight: 1.6, paddingLeft: 18 }}>
          {examples.map((example) => (
            <li key={example.id}>
              <strong>{example.name}</strong> → {[...example.weather, ...example.occasions].join(", ")}
            </li>
          ))}
        </ul>
      )}

      {preview.ai_available && (
        <div
          style={{
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "10px 12px",
            marginTop: 12,
          }}
        >
          <label className="row" style={{ gap: 10, cursor: "pointer" }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={useAi}
              onChange={(e) => setUseAi(e.target.checked)}
            />
            <span>✨ Ook AI gebruiken</span>
          </label>
          <p className="muted" style={{ fontSize: "0.78rem", margin: "6px 0 0" }}>
            De AI stelt dan zelf looks samen en vult tags aan waar de regels niets zeggen. Wat
            jullie hebben goedgekeurd krijgt 'ie mee als aanrader; wat is <strong>afgekeurd</strong>
            wordt daarna alsnog afgedwongen door de app — stelt de AI zo'n paar toch voor, dan gaat
            die look eruit en zie je hier hoeveel er zijn afgewezen. Tags die deze app niet kent
            vallen af, en ingevulde velden blijven met rust. Hiervoor gaan naam, categorie, kleur,
            maat en seizoen van je kleding naar de AI-dienst. Geen foto's, geen namen van personen.
          </p>
        </div>
      )}

      <div className="stack" style={{ marginTop: 12 }}>
        <div>
          <button
            className="btn-ghost btn-block"
            onClick={fillTags}
            disabled={busy !== null || preview.taggable === 0}
          >
            {busy === "tags" ? "Bezig…" : "🏷️ Ontbrekende tags aanvullen"}
          </button>
          <p className="muted" style={{ fontSize: "0.78rem", margin: "4px 0 0" }}>
            {preview.taggable > 0
              ? `${preview.taggable} van de ${preview.item_count} stuks kan de app weer- en gelegenheidstags geven.`
              : "Alles heeft al tags, of de categorie zegt er te weinig over."}
          </p>
        </div>

        <div>
          <div className="row" style={{ gap: 8 }}>
            <button
              className="btn-ghost"
              style={{ flex: 1 }}
              onClick={composeLooks}
              disabled={busy !== null || preview.composable === 0}
            >
              {busy === "looks" ? "Bezig…" : "✨ Looks samenstellen"}
            </button>
            <select
              value={count}
              style={{ width: "auto", flex: "none" }}
              aria-label="Hoeveel looks"
              onChange={(e) => setCount(Number(e.target.value))}
            >
              {COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n} stuks
                </option>
              ))}
            </select>
          </div>
          <p className="muted" style={{ fontSize: "0.78rem", margin: "4px 0 0" }}>
            {preview.composable > 0
              ? `Er zijn nu ${preview.composable} nieuwe combinaties te maken uit wat er hangt, met dezelfde kleurregels als de rest van de app — en nooit een paar dat iemand afkeurde.`
              : "Alles wat past staat al als look opgeslagen."}
          </p>
        </div>
      </div>

      {nothingToDo && (
        <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 0 }}>
          Er valt hier op dit moment niets aan te vullen.
        </p>
      )}
    </div>
  );
}
