/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The panel's URL segment. Chosen per deployment; never linked publicly. */
  readonly VITE_PANEL_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
