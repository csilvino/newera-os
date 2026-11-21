export type CognitiveLens = 'essence' | 'work' | 'xray';

export type ShellView = 'horizon' | 'canvas' | 'semantic' | 'guardian' | 'continuum';

export interface EssenceMetric {
  label: string;
  value: string;
  status: 'ok' | 'warn' | 'alert' | 'info';
}

export interface WorkspaceEssence {
  headline: string;
  subheadline: string;
  metrics: EssenceMetric[];
  next_actions: string[];
}

export interface WorkspaceBlock {
  id: string;
  type: string;
  title: string;
  capability: string;
  col_span: number;
  data: Record<string, any>;
  accepts_drop: string[];
}

export interface DataWire {
  id: string;
  from_block: string;
  from_field: string;
  to_block: string;
  to_field: string;
  label: string;
}

export interface ExecutionTraceStep {
  step: string;
  component: string;
  duration_ms: number;
  detail: string;
  privacy_checked: boolean;
}

export interface WorkspaceSnapshot {
  version: number;
  timestamp: string;
  summary: string;
  blocks: WorkspaceBlock[];
  essence: WorkspaceEssence;
}

export interface WorkspaceGraph {
  id: string;
  title: string;
  intent_query: string;
  intent_type: string;
  status: 'active' | 'dissolved';
  created_at: string;
  updated_at: string;
  version: number;
  essence: WorkspaceEssence;
  blocks: WorkspaceBlock[];
  wires: DataWire[];
  semantic_sources: Array<{
    id: string;
    title: string;
    kind: string;
    score?: number;
    tags: string[];
  }>;
  trace: ExecutionTraceStep[];
  history: WorkspaceSnapshot[];
}

export interface SemanticObject {
  id: string;
  content_hash: string;
  kind: string;
  title: string;
  summary: string;
  content_text: string;
  mime_type: string;
  original_name: string;
  entities: Record<string, string[]>;
  tags: string[];
  created_at: string;
  updated_at: string;
  score?: number | null;
}

export interface SemanticGraphData {
  nodes: Array<{
    id: string;
    label: string;
    kind: string;
    summary: string;
    tags: string[];
  }>;
  edges: Array<{
    source: string;
    target: string;
    relation: string;
    weight: number;
  }>;
}

export interface CapabilityManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  intents: string[];
  keywords: string[];
  permissions: {
    network: boolean;
    vault: string;
    semantic_fs: string;
  };
  source: 'builtin' | 'contrib';
}

export interface SystemStatus {
  os: string;
  version: string;
  protocol: string;
  llm_provider: string;
  capabilities: CapabilityManifest[];
  active_workspaces: Array<{
    id: string;
    title: string;
    intent_type: string;
    version: number;
    updated_at: string;
    headline: string;
    blocks_count: number;
  }>;
  connected_devices: Array<{
    id: string;
    device_type: string;
    device_name: string;
    connected_at: string;
  }>;
  guardian: {
    identity: {
      identity_id: string;
      fingerprint: string;
      public_key_b64: string;
      created_at: string;
    };
    encryption: string;
    vault_items_count: number;
    pending_approvals: number;
    audit_events_count: number;
    audit_chain_valid: boolean;
  };
}
