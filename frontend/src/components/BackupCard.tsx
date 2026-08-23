import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useConfirm } from "../confirm";
import type { BackupPreview, RestoreResult, RestoreTarget, Wardrobe } from "../types";

interface Props {
  /** The kast the current user owns — the one they can export for themselves. */
  ownWardrobe: Wardrobe | null;
  isAdmin: boolean;
}

/** Downloading a kast, and (for beheerders) putting one back.
 *
 * Everyone can take their own kast with them: a ZIP with an Excel workbook,
 * the photos as ordinary files, and the data a restore needs. Restoring is a
 * beheerder's job — it writes over garments and verdicts that may belong to
 * several people at once, so it is never one click: pick a file, read what is
 * in it, then choose to merge or replace.
 */
export default function BackupCard({ ownWardrobe, isAdmin }: Props) {
  const confirm = useConfirm();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // restore (admin)
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BackupPreview | null>(null);
  const [targets, setTargets] = useState<RestoreTarget[]>([]);
  const [target, setTarget] = useState<number | null>(null);
  const [mode, setMode] = useState<"merge" | "replace">("merge");
  const [result, setResult] = useState<RestoreResult | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isAdmin) return;
    api
      .restoreTargets()
      .then((list) => {
        setTargets(list);
        setTarget((current) => current ?? list[0]?.id ?? null);
      })
      .catch(() => setTargets([]));
  }, [isAdmin]);

  async function run(key: string, action: () => Promise<void>, done?: string) {
    setBusy(key);
    setError(null);
    setNote(null);
    try {
      await action();
      if (done) setNote(done);
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Er ging iets mis");
    } finally {
      setBusy(null);
    }
  }

  async function choose(chosen: File | null) {
    setFile(chosen);
    setPreview(null);
    setResult(null);
    if (!chosen) return;
    await run("inspect", async () => {
      setPreview(await api.inspectBackup(chosen));
    });
  }

  async function restore() {
    if (!file || !target) return;
    const kast = targets.find((t) => t.id === target);
    const ok = await confirm({
      title:
        mode === "replace"
          ? `Alles in "${kast?.name}" vervangen?`
          : `Back-up samenvoegen met "${kast?.name}"?`,
      body:
        mode === "replace"
          ? "Elk kledingstuk in deze kast wordt eerst verwijderd, met foto's en beoordelingen, en daarna vervangen door de inhoud van het bestand. Dit kan niet ongedaan worden gemaakt."
          : "Kledingstukken uit het bestand worden toegevoegd; stukken die er al staan worden bijgewerkt. Er wordt niets verwijderd.",
      confirmLabel: mode === "replace" ? "Vervangen" : "Samenvoegen",
    });
    if (!ok) return;
    await run("restore", async () => {
      const outcome = await api.restoreBackup(file, target, mode);
      setResult(outcome);
      setPreview(null);
      setFile(null);
      if (picker.current) picker.current.value = "";
    });
  }

  return (
    <div className="card" style={{ padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>Back-up &amp; export</h3>

      {error && <div className="error">{error}</div>}
      {note && <div className="notice">{note}</div>}

      <p className="muted" style={{ fontSize: "0.82rem", marginTop: 0 }}>
        Je krijgt één ZIP-bestand: een Excel-bestand met al je kledingstukken (met
        foto en al), de foto's als losse bestanden in een map, en de gegevens die
        nodig zijn om de kast ooit terug te zetten.
      </p>

      <button
        className="btn-primary btn-block"
        disabled={!ownWardrobe || busy !== null}
        onClick={() =>
          ownWardrobe &&
          run("export", () => api.exportWardrobe(ownWardrobe.id), "Je kast is gedownload.")
        }
      >
        {busy === "export" ? "Bezig…" : "⬇ Exporteer mijn kast"}
      </button>

      {isAdmin && (
        <>
          <hr className="rule" />
          <h4 className="backup-heading">Voor beheerders</h4>

          <div className="backup-actions">
            <button
              className="btn-ghost"
              disabled={busy !== null}
              onClick={() =>
                run("full", () => api.exportEverything(), "De volledige back-up is gedownload.")
              }
            >
              {busy === "full" ? "Bezig…" : "⬇ Volledige back-up"}
            </button>
            <button
              className="btn-ghost"
              disabled={busy !== null}
              onClick={() =>
                run("snapshot", () => api.exportSnapshot(), "De momentopname is gedownload.")
              }
            >
              {busy === "snapshot" ? "Bezig…" : "⬇ Momentopname (database)"}
            </button>
          </div>
          <p className="muted backup-hint">
            De <strong>volledige back-up</strong> bevat alle kasten, accounts en instellingen —
            overdraagbaar, en ook een versie later nog te lezen. De <strong>momentopname</strong> is
            een exacte kopie van de database en de foto's: die zet je op de server terug, niet via de
            app. Beide bestanden bevatten gegevens van iedereen; bewaar ze zorgvuldig.
          </p>

          <hr className="rule" />
          <h4 className="backup-heading">Terugzetten</h4>
          <input
            ref={picker}
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
            disabled={busy !== null}
          />

          {busy === "inspect" && <div className="spinner" />}

          {preview && (
            <>
              <div className="backup-preview">
                <div className="row spread">
                  <strong>
                    {preview.scope === "instance" ? "Volledige back-up" : "Export van één kast"}
                  </strong>
                  <span className="muted" style={{ fontSize: "0.78rem" }}>
                    {preview.generated_at.slice(0, 10)} · v{preview.app_version}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: "0.82rem" }}>
                  Gemaakt door {preview.generated_by}
                  {preview.wardrobe_names.length > 0 && ` · ${preview.wardrobe_names.join(", ")}`}
                </div>
                <ul className="backup-counts">
                  <li>
                    <strong>{preview.items}</strong> kledingstukken
                  </li>
                  <li>
                    <strong>{preview.photos}</strong> foto's
                  </li>
                  <li>
                    <strong>{preview.combinations}</strong> combinaties
                  </li>
                  <li>
                    <strong>{preview.people}</strong> personen
                  </li>
                </ul>
              </div>

              <label className="backup-label" htmlFor="restore-target">
                Terugzetten in
              </label>
              <select
                id="restore-target"
                value={target ?? ""}
                onChange={(e) => setTarget(Number(e.target.value))}
              >
                {targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} — {t.owner}
                  </option>
                ))}
              </select>

              <div className="seg" style={{ marginTop: 10 }}>
                <button
                  className={`seg-btn ${mode === "merge" ? "active" : ""}`}
                  onClick={() => setMode("merge")}
                  aria-pressed={mode === "merge"}
                >
                  Samenvoegen
                </button>
                <button
                  className={`seg-btn ${mode === "replace" ? "active" : ""}`}
                  onClick={() => setMode("replace")}
                  aria-pressed={mode === "replace"}
                >
                  Vervangen
                </button>
              </div>
              <p className="muted backup-hint">
                {mode === "merge"
                  ? "Voegt toe wat ontbreekt en werkt bij wat er al staat. Er wordt niets verwijderd."
                  : "Leegt de gekozen kast eerst helemaal — inclusief foto's en beoordelingen — en zet daarna het bestand terug."}
              </p>

              <button
                className={mode === "replace" ? "btn-danger btn-block" : "btn-primary btn-block"}
                disabled={busy !== null || !target}
                onClick={restore}
              >
                {busy === "restore"
                  ? "Bezig…"
                  : mode === "replace"
                    ? "Kast vervangen"
                    : "Samenvoegen"}
              </button>
            </>
          )}

          {result && (
            <div className="notice">
              Teruggezet in <strong>{result.wardrobe}</strong>: {result.added} toegevoegd,{" "}
              {result.updated} bijgewerkt, {result.combinations} combinaties en {result.photos}{" "}
              foto's.
            </div>
          )}
        </>
      )}
    </div>
  );
}
