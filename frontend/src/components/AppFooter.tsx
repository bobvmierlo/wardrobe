import { useEffect, useState } from "react";
import { api } from "../api";

// Cache the version across the many AppFooter instances (one per page) so we
// only hit the backend once per session.
let cachedVersion: string | null = null;

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
      Kledingkast{version ? ` · v${version}` : ""}
    </p>
  );
}
