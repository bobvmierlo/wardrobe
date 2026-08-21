/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** App version baked in at build time (e.g. "v1.2.3"); "dev" when unset. */
  readonly VITE_APP_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
