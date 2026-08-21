import { useCallback, useEffect, useRef, useState } from "react";

export interface PhotoEditorProps {
  /** Same-origin URL or object URL of the image to edit. */
  src: string;
  onCancel: () => void;
  onApply: (blob: Blob) => void;
}

type Rect = { x: number; y: number; w: number; h: number };
type Handle = "move" | "nw" | "ne" | "sw" | "se";

const HANDLE = 22; // touch target size in px
const MIN = 40; // minimum crop size in display px

/**
 * A small, dependency-free crop & rotate editor. The full image is kept on an
 * offscreen canvas at native resolution; rotation re-bakes that canvas, and the
 * crop rectangle is tracked in on-screen pixels and mapped back on apply.
 */
export default function PhotoEditor({ src, onCancel, onApply }: PhotoEditorProps) {
  const baseRef = useRef<HTMLCanvasElement | null>(null); // native-res, current rotation
  const stageRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLCanvasElement | null>(null);
  const [ready, setReady] = useState(false);
  const [dispSize, setDispSize] = useState({ w: 0, h: 0, scale: 1 });
  const [crop, setCrop] = useState<Rect>({ x: 0, y: 0, w: 0, h: 0 });
  const drag = useRef<{ handle: Handle; startX: number; startY: number; start: Rect } | null>(null);

  // Draw the base canvas onto the visible preview.
  const paint = useCallback(() => {
    const base = baseRef.current;
    const prev = previewRef.current;
    if (!base || !prev) return;
    const ctx = prev.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, prev.width, prev.height);
    ctx.drawImage(base, 0, 0, prev.width, prev.height);
  }, []);

  const layout = useCallback(() => {
    const base = baseRef.current;
    const stage = stageRef.current;
    if (!base || !stage) return;
    const maxW = stage.clientWidth;
    const maxH = Math.min(window.innerHeight * 0.55, 520);
    const scale = Math.min(maxW / base.width, maxH / base.height, 1);
    const w = Math.round(base.width * scale);
    const h = Math.round(base.height * scale);
    setDispSize({ w, h, scale });
    setCrop((c) => {
      // Keep full-frame selection when uninitialised or after a rotate.
      if (c.w === 0) return { x: 0, y: 0, w, h };
      return { x: 0, y: 0, w, h };
    });
  }, []);

  // Load the source image into the base canvas.
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth;
      cv.height = img.naturalHeight;
      cv.getContext("2d")!.drawImage(img, 0, 0);
      baseRef.current = cv;
      setReady(true);
      layout();
    };
    img.src = src;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    if (ready) paint();
  }, [ready, dispSize, paint]);

  useEffect(() => {
    const onResize = () => layout();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [layout]);

  function rotate(dir: 1 | -1) {
    const base = baseRef.current;
    if (!base) return;
    const cv = document.createElement("canvas");
    cv.width = base.height;
    cv.height = base.width;
    const ctx = cv.getContext("2d")!;
    ctx.translate(cv.width / 2, cv.height / 2);
    ctx.rotate((dir * Math.PI) / 2);
    ctx.drawImage(base, -base.width / 2, -base.height / 2);
    baseRef.current = cv;
    layout();
  }

  function clampRect(r: Rect): Rect {
    let { x, y, w, h } = r;
    w = Math.max(MIN, w);
    h = Math.max(MIN, h);
    x = Math.min(Math.max(0, x), dispSize.w - w);
    y = Math.min(Math.max(0, y), dispSize.h - h);
    if (x < 0) { x = 0; w = dispSize.w; }
    if (y < 0) { y = 0; h = dispSize.h; }
    return { x, y, w, h };
  }

  function pointer(e: React.PointerEvent) {
    const stage = stageRef.current!;
    const rect = stage.getBoundingClientRect();
    return { px: e.clientX - rect.left, py: e.clientY - rect.top };
  }

  function startDrag(handle: Handle, e: React.PointerEvent) {
    e.preventDefault();
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    const { px, py } = pointer(e);
    drag.current = { handle, startX: px, startY: py, start: crop };
  }

  function onMove(e: React.PointerEvent) {
    if (!drag.current) return;
    const { px, py } = pointer(e);
    const dx = px - drag.current.startX;
    const dy = py - drag.current.startY;
    const s = drag.current.start;
    let r: Rect = { ...s };
    switch (drag.current.handle) {
      case "move":
        r = { ...s, x: s.x + dx, y: s.y + dy };
        break;
      case "nw":
        r = { x: s.x + dx, y: s.y + dy, w: s.w - dx, h: s.h - dy };
        break;
      case "ne":
        r = { x: s.x, y: s.y + dy, w: s.w + dx, h: s.h - dy };
        break;
      case "sw":
        r = { x: s.x + dx, y: s.y, w: s.w - dx, h: s.h + dy };
        break;
      case "se":
        r = { x: s.x, y: s.y, w: s.w + dx, h: s.h + dy };
        break;
    }
    // Prevent inverting when a corner crosses the opposite edge.
    if (r.w < MIN) { r.w = MIN; if (drag.current.handle.includes("w")) r.x = s.x + s.w - MIN; }
    if (r.h < MIN) { r.h = MIN; if (drag.current.handle.startsWith("n")) r.y = s.y + s.h - MIN; }
    setCrop(clampRect(r));
  }

  function endDrag(e: React.PointerEvent) {
    drag.current = null;
    try { (e.target as Element).releasePointerCapture(e.pointerId); } catch { /* ignore */ }
  }

  function apply() {
    const base = baseRef.current;
    if (!base) return;
    const sx = crop.x / dispSize.scale;
    const sy = crop.y / dispSize.scale;
    const sw = crop.w / dispSize.scale;
    const sh = crop.h / dispSize.scale;
    const out = document.createElement("canvas");
    out.width = Math.max(1, Math.round(sw));
    out.height = Math.max(1, Math.round(sh));
    out.getContext("2d")!.drawImage(base, sx, sy, sw, sh, 0, 0, out.width, out.height);
    out.toBlob((blob) => blob && onApply(blob), "image/jpeg", 0.9);
  }

  const cornerStyle = (pos: Handle): React.CSSProperties => {
    const base: React.CSSProperties = {
      position: "absolute",
      width: HANDLE,
      height: HANDLE,
      background: "var(--primary)",
      borderRadius: 6,
      touchAction: "none",
    };
    const off = -HANDLE / 2;
    if (pos === "nw") return { ...base, left: off, top: off, cursor: "nwse-resize" };
    if (pos === "ne") return { ...base, right: off, top: off, cursor: "nesw-resize" };
    if (pos === "sw") return { ...base, left: off, bottom: off, cursor: "nesw-resize" };
    return { ...base, right: off, bottom: off, cursor: "nwse-resize" };
  };

  return (
    <div className="editor-backdrop" role="dialog" aria-modal="true">
      <div className="editor-panel">
        <div className="row spread" style={{ marginBottom: 12 }}>
          <strong>Foto bijsnijden</strong>
          <button type="button" className="btn-ghost" onClick={onCancel}>Annuleren</button>
        </div>

        <div ref={stageRef} className="editor-stage">
          {ready && (
            <div style={{ position: "relative", width: dispSize.w, height: dispSize.h, margin: "0 auto", overflow: "hidden", borderRadius: 8 }}>
              <canvas ref={previewRef} width={dispSize.w} height={dispSize.h} style={{ display: "block", borderRadius: 8 }} />
              <div
                className="crop-box"
                style={{ left: crop.x, top: crop.y, width: crop.w, height: crop.h, touchAction: "none" }}
                onPointerDown={(e) => startDrag("move", e)}
                onPointerMove={onMove}
                onPointerUp={endDrag}
              >
                {(["nw", "ne", "sw", "se"] as Handle[]).map((h) => (
                  <div
                    key={h}
                    style={cornerStyle(h)}
                    onPointerDown={(e) => startDrag(h, e)}
                    onPointerMove={onMove}
                    onPointerUp={endDrag}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="row" style={{ gap: 10, justifyContent: "center", marginTop: 14 }}>
          <button type="button" className="btn-ghost" onClick={() => rotate(-1)} aria-label="Draai linksom">↺ Links</button>
          <button type="button" className="btn-ghost" onClick={() => rotate(1)} aria-label="Draai rechtsom">↻ Rechts</button>
          <button type="button" className="btn-ghost" onClick={() => setCrop({ x: 0, y: 0, w: dispSize.w, h: dispSize.h })}>Reset</button>
        </div>

        <button type="button" className="btn-primary btn-block" style={{ marginTop: 14 }} onClick={apply}>
          Bijsnijden toepassen
        </button>
      </div>
    </div>
  );
}
