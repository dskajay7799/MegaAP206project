// Where the API lives.
//  - Same-origin (recommended; Netlify proxies /api/* to the backend, so cookies are first-party): leave empty.
//  - Cross-origin (frontend and API on different domains): set the backend URL and make sure the backend allows this origin:
//      window.VERITY_API_BASE = "https://your-api.onrender.com";   // also set CORS_ORIGINS and COOKIE_SAMESITE=None on the backend
// Never put API keys or secrets in this file: it is public.
window.VERITY_API_BASE = "";
