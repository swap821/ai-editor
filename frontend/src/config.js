// Central API base URL. Points at the local-first FastAPI backend (aios.api.main),
// which serves on :8000 by default. Override at build/run time with VITE_API_BASE.
//
// SECURITY (H5): HTTPS-by-default for non-localhost deployments.
// The AIOS_HTTPS_ONLY env flag forces https:// for all API calls. In production
// deployments, ALWAYS set VITE_AIOS_HTTPS_ONLY=true to prevent credential leakage.
const FORCE_HTTPS = import.meta.env.VITE_AIOS_HTTPS_ONLY === 'true';
const RAW_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? '' : 'http://localhost:8000');

function enforceHttps(url) {
  if (FORCE_HTTPS && url.startsWith('http://') && !url.includes('localhost') && !url.includes('127.0.0.1')) {
    return url.replace('http://', 'https://');
  }
  return url;
}

export const API_BASE = enforceHttps(RAW_BASE);

// SECURITY (C16): API token is NO LONGER read from build-time env vars.
// Embedding tokens in the frontend bundle exposes them to anyone who views the
// page source. The default UI uses httpOnly session cookies for continuity; a
// token-protected non-loopback deployment should put a trusted same-origin
// reverse proxy in front of the API.
export const API_HEADERS = {};
