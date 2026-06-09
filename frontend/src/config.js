// Central API base URL. Points at the local-first FastAPI backend (aios.api.main),
// which serves on :8000 by default. Override at build/run time with VITE_API_BASE.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_TOKEN = import.meta.env.VITE_AIOS_API_TOKEN || '';
export const API_HEADERS = API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
