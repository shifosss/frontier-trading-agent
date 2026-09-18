export const number = (n: unknown, digits = 2) =>
  typeof n === "number" && Number.isFinite(n)
    ? n.toLocaleString("en-CA", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      })
    : "Not enough observations";
export const percent = (n: unknown) =>
  typeof n === "number" ? `${number(n * 100)}%` : "Not enough observations";
export const day = (s: string) => (s ? s.slice(0, 10) : "—");
export const ratio = (value: unknown) =>
  typeof value === "number"
    ? `${(value * 100).toFixed(2)}%`
    : "Not enough observations";
export const readable = (value: unknown) =>
  typeof value === "string" ? value.replaceAll("_", " ") : "Unknown";
export const savedText = (value: unknown) =>
  typeof value === "string" || typeof value === "number"
    ? String(value)
    : value == null
      ? "Not provided"
      : JSON.stringify(value);
