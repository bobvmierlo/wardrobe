// Version baked in at build time by CI (see Dockerfile). Falls back to "dev"
// for local builds where no release version is set.
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || "dev";

/** Small muted footer with the running app version, shown on every page. */
export default function AppFooter() {
  return (
    <p className="app-footer">
      Kledingkast · {APP_VERSION}
    </p>
  );
}
