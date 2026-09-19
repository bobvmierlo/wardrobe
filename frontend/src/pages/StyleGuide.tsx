import { useEffect, useState } from "react";
import AppFooter from "../components/AppFooter";
import WardrobeSwitcher from "../components/WardrobeSwitcher";
import { api } from "../api";
import { useWardrobe } from "../wardrobe";
import type { StyleGuide as Guide } from "../types";

/** "Stijlgids": what this kast's own colours go with, and where the holes are.
 *
 * Not generic fashion advice — every line comes from the installation's own
 * colour rules (editable by a beheerder) and the garments actually in the
 * kast, so advice you disagree with is advice you can change. */
export default function StyleGuide() {
  const { current } = useWardrobe();
  const currentId = current?.id;
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api
      .styleGuide(currentId)
      .then(setGuide)
      .catch(() => setGuide(null))
      .finally(() => setLoading(false));
  }, [currentId]);

  return (
    <>
      <div className="topbar">
        <h1>Stijlgids</h1>
        <WardrobeSwitcher />
      </div>
      <div className="content">
        {loading && <div className="spinner" />}
        {guide && (
          <>
            <h2 style={{ marginTop: 0 }}>Jouw kleuren, en wat erbij past</h2>
            {guide.colors.length === 0 && (
              <p className="muted">
                Nog geen kleuren bekend. Vul de kleur in bij je kledingstukken, dan vult deze gids
                zich vanzelf.
              </p>
            )}
            {guide.colors.map((color) => (
              <div className="card rec-card" key={color.color}>
                <div className="rec-head">
                  <span className="rec-title">
                    {color.color} {color.in_profile && <span title="Zit in je stijl-DNA">★</span>}
                  </span>
                  <span className="rec-source">{color.count} stuk(s)</span>
                </div>
                <p className="rec-reason">
                  <strong>Past bij:</strong> {color.goes_with.join(", ") || "nog geen regel hiervoor"}
                </p>
                {color.clashes_with.length > 0 && (
                  <p className="rec-reason">
                    <strong>Botst met:</strong> {color.clashes_with.join(", ")}
                  </p>
                )}
              </div>
            ))}

            {guide.gaps.length > 0 && (
              <>
                <h2>Wat opvalt</h2>
                {guide.gaps.map((gap) => (
                  <div className="card rec-card" key={gap.title}>
                    <span className="rec-title">{gap.title}</span>
                    <p className="rec-reason">{gap.detail}</p>
                  </div>
                ))}
              </>
            )}

            {guide.uncovered_weather.length > 0 && (
              <>
                <h2>Nog niets getagd voor</h2>
                <div className="chips wrap">
                  {guide.uncovered_weather.map((tag) => (
                    <span className="tag" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  Bij dit weer kan "Vandaag" nog niets gericht voorstellen.
                </p>
              </>
            )}

            <h2>Vuistregels</h2>
            <ul className="muted" style={{ fontSize: "0.9rem", lineHeight: 1.6 }}>
              {guide.tips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
            <p className="muted" style={{ fontSize: "0.8rem" }}>
              Neutrale tinten in deze installatie: {guide.neutrals.join(", ")}. Een beheerder past de
              kleurregels aan bij Instellingen.
            </p>
          </>
        )}
        <AppFooter />
      </div>
    </>
  );
}
