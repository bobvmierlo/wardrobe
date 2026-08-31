import { useEffect, useState } from "react";
import { api } from "../api";

// Cache the version across the many AppFooter instances (one per page) so we
// only hit the backend once per session.
let cachedVersion: string | null = null;

const REPO = "https://github.com/bobvmierlo/wardrobe";

/** Where the running version comes from.
 *
 * A version is stamped on the code by the release workflow, so for anything
 * that shipped there is a release page with the notes for exactly this
 * version. Anything else (a hand-built image, a branch) has no such page, so
 * that links to the repository itself rather than to a 404. */
function versionLink(version: string): string {
  return /^\d+\.\d+\.\d+$/.test(version) ? `${REPO}/releases/tag/v${version}` : REPO;
}

/** Small muted footer with the running app version, shown on every page.
 * The version comes from the backend (backend/app/_version.py). */
export default function AppFooter() {
  const [version, setVersion] = useState<string | null>(cachedVersion);

  useEffect(() => {
    if (cachedVersion !== null) return;
    api
      .version()
      .then((v) => {
        cachedVersion = v.version;
        setVersion(v.version);
      })
      .catch(() => {
        cachedVersion = "";
        setVersion("");
      });
  }, []);

  return (
    <p className="app-footer">
      Kledingkast
      {version ? (
        <>
          {" · "}
          <a
            className="version-link"
            href={versionLink(version)}
            target="_blank"
            rel="noreferrer noopener"
            title="Bekijk deze versie op GitHub"
          >
            v{version}
          </a>
        </>
      ) : null}
    </p>
  );
}
