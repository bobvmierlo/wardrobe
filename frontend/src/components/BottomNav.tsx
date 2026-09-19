import { NavLink } from "react-router-dom";

// Five is what fits under a thumb. Everything else — the planner, Ontdekken,
// Inzichten, Reistas, Stijl-DNA, de Stijlgids, Combineer en Instellingen —
// hangt onder "Meer", zodat de bar leesbaar blijft op een telefoon.
const links = [
  { to: "/vandaag", label: "Vandaag", ico: "🌤️", end: false },
  { to: "/", label: "Kast", ico: "👕", end: true },
  { to: "/looks", label: "Looks", ico: "✨", end: false },
  { to: "/week", label: "Week", ico: "🗓️", end: false },
  { to: "/meer", label: "Meer", ico: "☰", end: false },
];

interface Props {
  /** Render the nav for wide screens only.
   *
   * Sub-pages (a garment, the form, the log) navigate with "← Terug" on a
   * phone and deliberately have no bar. On a desktop the same rail is what
   * tells you where you are, so there it is worth keeping — and a rail costs
   * no room a phone would miss, because it is not rendered at all. */
  desktopOnly?: boolean;
}

/** The app's main navigation: a bar under the thumb on a phone, a rail down
 *  the left on a wide screen. Both are this one element; the layout is CSS. */
export default function BottomNav({ desktopOnly = false }: Props) {
  return (
    <nav className={`bottomnav${desktopOnly ? " nav-desktop-only" : ""}`} aria-label="Hoofdnavigatie">
      {/* Only shown on the rail: on a phone the top bar already names the page. */}
      <div className="rail-brand">
        <span className="logo" aria-hidden="true">👕</span>
        <span>Kledingkast</span>
      </div>
      <div className="inner">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}>
            <span className="ico">{l.ico}</span>
            <span>{l.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
