import { useState, type ReactNode } from "react";

interface Props {
  label: string;
  /** What to offer. Anything already chosen but missing here is added, so a
   *  tag typed months ago stays visible after it left the default list. */
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
  /** Let people type a tag of their own (style words, not weather). */
  allowCustom?: boolean;
  hint?: string;
  /** Something to draw inside each chip, ahead of its label. Used by the
   *  colour picker, where the word "beige" is a far worse description of the
   *  option than the colour itself is. */
  decorate?: (tag: string) => ReactNode;
}

/** A row of chips you switch on and off. The tag vocabularies (occasion,
 *  weather, style) all behave the same way, so they all use this. */
export default function TagPicker({
  label,
  options,
  value,
  onChange,
  allowCustom = false,
  hint,
  decorate,
}: Props) {
  const [typed, setTyped] = useState("");
  const all = [...options, ...value.filter((v) => !options.includes(v))];

  function toggle(tag: string) {
    onChange(value.includes(tag) ? value.filter((v) => v !== tag) : [...value, tag]);
  }

  function addTyped() {
    const clean = typed.trim();
    if (!clean) return;
    if (!value.includes(clean)) onChange([...value, clean]);
    setTyped("");
  }

  return (
    <div className="field">
      <label>{label}</label>
      {hint && (
        <p className="muted" style={{ margin: "-2px 0 8px", fontSize: "0.8rem" }}>
          {hint}
        </p>
      )}
      <div className="chips wrap">
        {all.map((tag) => (
          <button
            type="button"
            key={tag}
            className={`chip ${value.includes(tag) ? "active" : ""}`}
            aria-pressed={value.includes(tag)}
            onClick={() => toggle(tag)}
          >
            {decorate?.(tag)}
            {tag}
          </button>
        ))}
      </div>
      {allowCustom && (
        <div className="row" style={{ gap: 8, marginTop: 10 }}>
          <input
            value={typed}
            placeholder="Eigen woord toevoegen…"
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                // Otherwise this submits whichever form the picker sits in.
                e.preventDefault();
                addTyped();
              }
            }}
          />
          <button type="button" className="btn-ghost" onClick={addTyped} disabled={!typed.trim()}>
            Toevoegen
          </button>
        </div>
      )}
    </div>
  );
}
