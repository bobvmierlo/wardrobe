import { Link } from "react-router-dom";
import AppFooter from "../components/AppFooter";

/** The hub for everything that does not fit in the bar under your thumb.
 *
 * Five is about the limit for a bottom bar on a phone; this is where the rest
 * lives, with a line each saying what it is for. */
const tiles = [
  { to: "/week", ico: "🗓️", label: "Weekplanner", hint: "Plan per dag vooruit, met het weer erbij." },
  { to: "/discover", ico: "🧭", label: "Ontdekken", hint: "Laat de app iets samenstellen op gelegenheid en weer." },
  { to: "/insights", ico: "📊", label: "Inzichten", hint: "Wat zit er in je kast, en wat draag je nooit?" },
  { to: "/trips", ico: "🧳", label: "Reistas", hint: "Looks meenemen, paklijst automatisch." },
  { to: "/stijl-dna", ico: "💎", label: "Stijl-DNA", hint: "Jouw kleuren en stijlwoorden." },
  { to: "/stijlgids", ico: "✨", label: "Stijlgids", hint: "Wat past bij wat, in jouw kast." },
  { to: "/combine", ico: "💞", label: "Combineer", hint: "Swipe samen wat bij elkaar past." },
  { to: "/outfits", ico: "🤝", label: "Combinaties", hint: "Wat jullie samen hebben goedgekeurd." },
  { to: "/settings", ico: "⚙️", label: "Instellingen", hint: "Thema, locatie, delen en back-ups." },
];

export default function More() {
  return (
    <>
      <div className="topbar">
        <h1>Meer</h1>
      </div>
      <div className="content">
        <div className="hub-grid">
          {tiles.map((tile) => (
            <Link className="hub-tile" to={tile.to} key={tile.to}>
              <span className="ico" aria-hidden="true">
                {tile.ico}
              </span>
              <span className="hub-label">{tile.label}</span>
              <span className="hub-hint">{tile.hint}</span>
            </Link>
          ))}
        </div>
        <AppFooter />
      </div>
    </>
  );
}
