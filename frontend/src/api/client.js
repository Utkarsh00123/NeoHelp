const API_BASE = import.meta.env.VITE_API_URL 
  ? `${import.meta.env.VITE_API_URL.replace(/\/$/, '')}/api` 
  : '/api';

function getAuthHeader() {
  const token = localStorage.getItem('neohelp_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function loginUser(email, password = 'password123') {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Login failed');
  }
  const data = await res.json();
  localStorage.setItem('neohelp_token', data.access_token);
  return data;
}

export async function switchUser(userId) {
  const res = await fetch(`${API_BASE}/auth/switch/${userId}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('User switch failed');
  const data = await res.json();
  localStorage.setItem('neohelp_token', data.access_token);
  return data;
}

export async function fetchUsers() {
  const res = await fetch(`${API_BASE}/auth/users`);
  if (!res.ok) throw new Error('Failed to fetch user directory');
  return res.json();
}

export async function fetchMe() {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error('Failed to fetch current user profile');
  return res.json();
}

export async function fetchItems({ teamId, queue, status, priority, q, cursor, limit = 20 }) {
  const params = new URLSearchParams();
  if (teamId) params.append('team_id', teamId);
  if (status) params.append('status', status);
  if (priority) params.append('priority', priority);
  if (q) params.append('q', q);
  if (cursor) params.append('cursor', cursor);
  if (limit) params.append('limit', limit);

  if (queue === 'assigned') params.append('assigned_to_me', 'true');
  if (queue === 'urgent') params.append('unassigned_urgent', 'true');
  if (queue === 'approval') params.append('awaiting_approval', 'true');

  const res = await fetch(`${API_BASE}/items?${params.toString()}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch items (${res.status})`);
  }
  return res.json();
}

export async function fetchItem(id) {
  const res = await fetch(`${API_BASE}/items/${id}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch item details');
  }
  return res.json();
}

export async function createItem(payload, idempotencyKey) {
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const res = await fetch(`${API_BASE}/items`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create item (${res.status})`);
  }
  return res.json();
}

export async function claimItem(id, idempotencyKey) {
  const headers = { ...getAuthHeader() };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const res = await fetch(`${API_BASE}/items/${id}/claim`, {
    method: 'POST',
    headers,
  });
  if (res.status === 409) {
    const err = await res.json().catch(() => ({}));
    const customErr = new Error(err.detail || 'Item was already claimed by another operator');
    customErr.status = 409;
    throw customErr;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to claim item (${res.status})`);
  }
  return res.json();
}

export async function updateItem(id, payload, idempotencyKey) {
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const res = await fetch(`${API_BASE}/items/${id}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(payload),
  });
  if (res.status === 409) {
    const err = await res.json().catch(() => ({}));
    const customErr = new Error(err.detail?.message || 'Item was modified concurrently. Please reload.');
    customErr.status = 409;
    customErr.detail = err.detail;
    throw customErr;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update item (${res.status})`);
  }
  return res.json();
}

export async function transitionItem(id, payload, idempotencyKey) {
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const res = await fetch(`${API_BASE}/items/${id}/transition`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const customErr = new Error(err.detail || `Failed to transition item (${res.status})`);
    customErr.status = res.status;
    throw customErr;
  }
  return res.json();
}

export async function fetchItemActivity(id) {
  const res = await fetch(`${API_BASE}/items/${id}/activity`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error('Failed to fetch activity history');
  return res.json();
}

export async function addComment(id, comment) {
  const res = await fetch(`${API_BASE}/items/${id}/comments`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
    },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add comment');
  }
  return res.json();
}
