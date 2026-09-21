import { Fragment } from "react";
import { NavLink } from "react-router-dom";

interface Link {
  to: string;
  label: string;
  ico: string;
  end?: boolean;
  /** Only on the rail. On a phone this destination lives under "Meer". */
  railOnly?: boolean;
}

/** The whole app, in the order you would walk through it.
 *
 * On a phone only the first five are rendered plus "Meer": five is what fits
 * under a thumb, and the rest hangs under that one button.
 *
 * On a wide screen every one of them is shown. The rail is 232 pixels wide and
 * a screen tall; below five links it is empty. Hiding half the app behind an
 * extra click to save room that was never short is the wrong trade, and it is
 * what made the planner, Ontdekken and Inzichten feel like afterthoughts on a
 * desktop.
 */
const GROUPS: { title: string; links: Link[] }[] = [
  {
    title: "Dagelijks",
    links: [
      { to: "/vandaag", label: "Vandaag", ico: "🌤️" },
      { to: "/", label: "Kast", ico: "👕", end: true },
      { to: "/looks", label: "Looks", ico: "✨" },
      { to: "/week", label: "Weekplanner", ico: "🗓️" },
    ],
  },
  {
    title: "Ontdekken",
    links: [
      { to: "/discover", label: "Ontdekken", ico: "🧭", railOnly: true },
      { to: "/combine", label: "Combineer", ico: "💞", railOnly: true },
      { to: "/outfits", label: "Combinaties", ico: "🤝", railOnly: true },
      { to: "/insights", label: "Inzichten", ico: "📊", railOnly: true },
    ],
  },
  {
    title: "Jouw stijl",
    links: [
      { to: "/stijl-dna", label: "Stijl-DNA", ico: "💎", railOnly: true },
      { to: "/stijlgids", label: "Stijlgids", ico: "🎨", railOnly: true },
      { to: "/trips", label: "Reistas", ico: "🧳", railOnly: true },
      { to: "/settings", label: "Instellingen", ico: "⚙️", railOnly: true },
    ],
  },
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

function Item({ link }: { link: Link }) {
  return (
    <NavLink to={link.to} end={link.end ?? false} className={link.railOnly ? "rail-only" : ""}>
      <span className="ico">{link.ico}</span>
      <span>{link.label}</span>
    </NavLink>
  );
}

/** The app's main navigation: a bar under the thumb on a phone, a rail down
 *  the left on a wide screen. Both are this one element; the layout is CSS —
 *  including which destinations appear, so neither layout has to know the
 *  other exists. */
export default function BottomNav({ desktopOnly = false }: Props) {
  return (
    <nav className={`bottomnav${desktopOnly ? " nav-desktop-only" : ""}`} aria-label="Hoofdnavigatie">
      {/* Only shown on the rail: on a phone the top bar already names the page. */}
      <div className="rail-brand">
        <span className="logo" aria-hidden="true">👕</span>
        <span>Kledingkast</span>
      </div>

      <div className="inner">
        {/* Every destination, once. Which of them a phone shows is CSS: the
            group headings and the rail-only links are hidden there, and
            "Meer" — the phone's door to exactly those — is hidden here.

            Fragments rather than a wrapper per group: the bar and the rail are
            both one flex line/column of links, and a <div> around a group
            would lay its members out separately from the rest. */}
        {GROUPS.map((group) => (
          <Fragment key={group.title}>
            <div className="rail-group">{group.title}</div>
            {group.links.map((link) => (
              <Item link={link} key={link.to} />
            ))}
          </Fragment>
        ))}
        <NavLink to="/meer" className="phone-only">
          <span className="ico">☰</span>
          <span>Meer</span>
        </NavLink>
      </div>
    </nav>
  );
}
