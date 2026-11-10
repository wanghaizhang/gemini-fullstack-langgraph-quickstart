/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MODEL_OPTIONS?: string;
  readonly VITE_DEFAULT_MODEL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
