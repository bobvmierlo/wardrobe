import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { photoUrl } from "../api";
import type { Item } from "../types";

export interface SwipeCardHandle {
  swipe: (verdict: "yes" | "no") => void;
}

interface Props {
  item: Item;
  onDecide: (verdict: "yes" | "no") => void;
}

const THRESHOLD = 90;

const SwipeCard = forwardRef<SwipeCardHandle, Props>(({ item, onDecide }, ref) => {
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [leaving, setLeaving] = useState<null | "yes" | "no">(null);
  const startX = useRef(0);
  const pointerId = useRef<number | null>(null);

  function decide(verdict: "yes" | "no") {
    if (leaving) return;
    setLeaving(verdict);
    window.setTimeout(() => onDecide(verdict), 220);
  }
  useImperativeHandle(ref, () => ({ swipe: decide }));

  function onDown(e: React.PointerEvent) {
    if (leaving) return;
    setDragging(true);
    startX.current = e.clientX;
    pointerId.current = e.pointerId;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }
  function onMove(e: React.PointerEvent) {
    if (!dragging) return;
    setDx(e.clientX - startX.current);
  }
  function onUp() {
    if (!dragging) return;
    setDragging(false);
    if (dx > THRESHOLD) decide("yes");
    else if (dx < -THRESHOLD) decide("no");
    else setDx(0);
  }

  const src = photoUrl(item);
  const offset = leaving === "yes" ? 600 : leaving === "no" ? -600 : dx;
  const rot = offset / 18;
  const style: React.CSSProperties = {
    transform: `translateX(${offset}px) rotate(${rot}deg)`,
    transition: dragging ? "none" : "transform 0.22s ease-out",
  };
  const yesOpacity = Math.min(Math.max(dx / THRESHOLD, 0), 1) || (leaving === "yes" ? 1 : 0);
  const noOpacity = Math.min(Math.max(-dx / THRESHOLD, 0), 1) || (leaving === "no" ? 1 : 0);

  return (
    <div
      className="swipe-card"
      style={style}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    >
      <div className="stamp yes" style={{ opacity: yesOpacity }}>
        MATCH
      </div>
      <div className="stamp no" style={{ opacity: noOpacity }}>
        NOPE
      </div>
      {src ? <img src={src} alt={item.name} draggable={false} /> : <div className="noimg-lg">👕</div>}
      <div className="cap">
        <div className="name">{item.name}</div>
        <div className="sub">
          {item.category}
          {item.brand ? ` · ${item.brand}` : ""}
          {item.color ? ` · ${item.color}` : ""}
        </div>
      </div>
    </div>
  );
});

export default SwipeCard;
