import { Link } from "react-router-dom";
import { photoUrl } from "../api";
import type { OutfitSuggestion } from "../types";

/** Renders the system's automatic outfit suggestions as a list of cards. */
export default function SuggestionList({ suggestions }: { suggestions: OutfitSuggestion[] }) {
  return (
    <div className="stack">
      {suggestions.map((s, idx) => (
        <div key={idx} className="card suggest-card">
          <div className="suggest-row">
            {s.items.map((it) => {
              const src = photoUrl(it, true);
              return (
                <Link to={`/item/${it.id}`} key={it.id} className="suggest-item" title={it.name}>
                  {src ? <img src={src} alt={it.name} /> : <div className="noimg-sm">👕</div>}
                  <span>{it.name}</span>
                </Link>
              );
            })}
          </div>
          <div className="suggest-reason">💡 {s.reason}</div>
        </div>
      ))}
    </div>
  );
}
