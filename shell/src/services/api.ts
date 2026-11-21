import type {
  SemanticGraphData,
  SemanticObject,
  SystemStatus,
  WorkspaceGraph,
} from '../types';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getStatus: () => request<SystemStatus>('/api/system/status'),

  runIntent: (query: string, device_type: 'desktop' | 'mobile' = 'desktop') =>
    request<WorkspaceGraph>('/api/intent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, device_type }),
    }),

  getWorkspace: (id: string) => request<WorkspaceGraph>(`/api/workspaces/${id}`),

  refineWorkspace: (id: string, command: string) =>
    request<WorkspaceGraph>(`/api/workspaces/${id}/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command }),
    }),

  updateBlock: (wsId: string, blockId: string, data: Record<string, any>, summary = 'Edição no bloco') =>
    request<WorkspaceGraph>(`/api/workspaces/${wsId}/blocks/${blockId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, summary }),
    }),

  mergeSemanticIntoBlock: (wsId: string, blockId: string, semanticObjectId: string) =>
    request<{ workspace: WorkspaceGraph; message: string }>(`/api/workspaces/${wsId}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: blockId, semantic_object_id: semanticObjectId }),
    }),

  restoreSnapshot: (wsId: string, version: number) =>
    request<WorkspaceGraph>(`/api/workspaces/${wsId}/restore/${version}`, { method: 'POST' }),

  dissolveWorkspace: (wsId: string) =>
    request<{ workspace_id: string; status: string; archived_semantic_id: string }>(
      `/api/workspaces/${wsId}/dissolve`,
      { method: 'POST' }
    ),

  // SemanticFS
  listSemantic: () => request<SemanticObject[]>('/api/semantic/objects'),
  searchSemantic: (q: string) => request<SemanticObject[]>(`/api/semantic/search?q=${encodeURIComponent(q)}`),
  getSemanticGraph: () => request<SemanticGraphData>('/api/semantic/graph'),
  ingestNote: (title: string, content: string, tags: string[], people: string[]) =>
    request<SemanticObject>('/api/semantic/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content, tags, people }),
    }),
  uploadFile: (file: File, tags = '', people = '') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('tags', tags);
    fd.append('people', people);
    return request<SemanticObject>('/api/semantic/upload', { method: 'POST', body: fd });
  },

  // Continuum
  getHandoff: (workspaceId?: string) => {
    const port = window.location.port || '5173';
    const qs = new URLSearchParams({ shell_port: port });
    if (workspaceId) qs.set('workspace_id', workspaceId);
    return request<{
      lan_ip: string;
      url: string;
      qr_svg: string;
      connected_devices: Array<{ id: string; device_type: string; device_name: string }>;
    }>(`/api/continuum/handoff?${qs.toString()}`);
  },

  // Guardian
  listVault: () => request<Array<{ key: string; category: string; label: string; updated_at: string }>>('/api/guardian/vault'),
  storeVault: (key: string, value: string, category: string, label: string) =>
    request('/api/guardian/vault', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value, category, label }),
    }),
  revealVault: (key: string) => request<{ key: string; value: string; label: string }>(`/api/guardian/vault/${encodeURIComponent(key)}/reveal`),
  deleteVault: (key: string) => request(`/api/guardian/vault/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  sanitizePII: (text: string) =>
    request<{ sanitized_text: string; redacted_count: number; findings: Array<{ kind: string; replacement: string }> }>(
      '/api/guardian/proxy/sanitize',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }
    ),
  listTokens: () => request<any[]>('/api/guardian/tokens'),
  requestToken: (audience: string, scope: string, vault_keys: string[], reason: string) =>
    request('/api/guardian/tokens/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audience, scope, vault_keys, reason }),
    }),
  approveToken: (id: string) => request(`/api/guardian/tokens/${id}/approve`, { method: 'POST' }),
  denyToken: (id: string) => request(`/api/guardian/tokens/${id}/deny`, { method: 'POST' }),
  getAudit: () => request<any[]>('/api/guardian/audit'),
};
