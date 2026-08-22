import { useWardrobe } from "../wardrobe";
import { ROLE_LABELS } from "../types";

/**
 * Compact wardrobe picker for page top bars. Only renders a dropdown when the
 * user can reach more than one kast (their own plus shared ones, or — for an
 * admin — everyone's). A read-only kast shows a small role badge.
 */
export default function WardrobeSwitcher() {
  const { wardrobes, current, select } = useWardrobe();
  if (!current || wardrobes.length <= 1) {
    if (current && current.my_role !== "owner") {
      return <span className={`role-badge ${current.my_role === "viewer" ? "" : "admin"}`}>{ROLE_LABELS[current.my_role]}</span>;
    }
    return null;
  }
  return (
    <div className="row" style={{ gap: 6, alignItems: "center" }}>
      <select
        className="wardrobe-select"
        value={current.id}
        onChange={(e) => select(Number(e.target.value))}
        aria-label="Kies een kast"
      >
        {wardrobes.map((w) => (
          <option key={w.id} value={w.id}>
            {w.my_role === "owner" ? "Mijn kast" : w.name}
            {w.my_role !== "owner" ? ` · ${ROLE_LABELS[w.my_role]}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
