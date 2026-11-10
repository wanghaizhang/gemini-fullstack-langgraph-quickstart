export interface ModelOption {
  value: string;
  label: string;
}

// Single source of truth for the Model dropdown. The list must contain model names
// the backend endpoint actually serves. Configure it in frontend/.env:
//   VITE_MODEL_OPTIONS=qwen3.8-flash-next-iq2_xs|Qwen 3.8 Flash,deepseek-chat|DeepSeek
// and pick the initial selection with VITE_DEFAULT_MODEL.
const FALLBACK: ModelOption[] = [
  { value: "gemini-2.0-flash", label: "2.0 Flash" },
  { value: "gemini-2.5-flash-preview-04-17", label: "2.5 Flash" },
  { value: "gemini-2.5-pro-preview-05-06", label: "2.5 Pro" },
];

export function parseOptions(raw: string): ModelOption[] {
  return raw
    .split(",")
    .map((chunk) => {
      const [value, label] = chunk.split("|").map((part) => part.trim());
      return value ? { value, label: label || value } : null;
    })
    .filter((option): option is ModelOption => Boolean(option));
}

const parsed = parseOptions((import.meta.env?.VITE_MODEL_OPTIONS ?? "").trim());

export const MODEL_OPTIONS: ModelOption[] = parsed.length ? parsed : FALLBACK;

export const DEFAULT_MODEL: string =
  (import.meta.env?.VITE_DEFAULT_MODEL ?? "").trim() || MODEL_OPTIONS[0]?.value || FALLBACK[0].value;
