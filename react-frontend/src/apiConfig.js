/**
 * API URL builder.
 * - Dev: empty REACT_APP_API_BASE → same-origin `/api/...` (webpack proxy adds X-API-Key).
 * - Prod: set REACT_APP_API_BASE to your API origin; put API behind same domain or a gateway that adds the key.
 */
export function apiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = (process.env.REACT_APP_API_BASE || "").replace(/\/$/, "");
  if (base) {
    return `${base}${p}`;
  }
  return `/api${p}`;
}
