const API_BASE = '/api';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail?.status || `Health check failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function pingBackend() {
  const res = await fetch(`${API_BASE}/health/ping`);
  if (!res.ok) {
    throw new Error(`Ping failed with HTTP ${res.status}`);
  }
  return res.json();
}
