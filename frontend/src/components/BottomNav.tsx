import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Kast", ico: "👕", end: true },
  { to: "/combine", label: "Combineer", ico: "💞", end: false },
  { to: "/outfits", label: "Outfits", ico: "✨", end: false },
  { to: "/settings", label: "Instellingen", ico: "⚙️", end: false },
];

export default function BottomNav() {
  return (
    <nav className="bottomnav">
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
