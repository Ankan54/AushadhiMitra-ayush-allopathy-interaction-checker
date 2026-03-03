// ── Supported AYUSH drugs (demo whitelist — exactly 5 plants) ────────────────
export const SUPPORTED_AYUSH_DRUGS = [
  "Curcuma longa",
  "Glycyrrhiza glabra",
  "Zingiber officinale",
  "Hypericum perforatum",
  "Withania somnifera",
];

// ── WebSocket event types ─────────────────────────────────────
export type PipelineStatusEvent = {
  type: "pipeline_status";
  status:
    | "name_resolution"
    | "input_validation"
    | "iteration_start"
    | "iteration_retry"
    | "phase_proposer"
    | "phase_evaluator"
    | "phase_scorer"
    | "gap_identified"
    | "formatting";
  message: string;
  iteration?: number;
  gap?: string;
  valid?: boolean;
  scientific_name?: string;
  original_name?: string;
  imppat_url?: string;
  supported_drugs?: string[];
};

export type AgentThinkingEvent = {
  type: "agent_thinking";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
};

export type LlmCallEvent = {
  type: "llm_call";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
  prompt_preview?: string;
};

export type LlmResponseEvent = {
  type: "llm_response";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
  tokens?: { inputTokens?: number; outputTokens?: number };
};

export type ToolCallEvent = {
  type: "tool_call";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
  function?: string;
  parameters?: Record<string, string>;
};

export type ToolResultEvent = {
  type: "tool_result";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
};

export type AgentCompleteEvent = {
  type: "agent_complete";
  agent: string;
  agent_key?: string;
  iteration?: number;
  message: string;
};

export type CompleteEvent = {
  type: "complete";
  result: InteractionResult;
  cached: boolean;
  session_id?: string;
  sources?: unknown[];
};

export type ErrorEvent = {
  type: "error";
  message: string;
  supported_drugs?: string[];
};

export type WsEvent =
  | PipelineStatusEvent
  | AgentThinkingEvent
  | LlmCallEvent
  | LlmResponseEvent
  | ToolCallEvent
  | ToolResultEvent
  | AgentCompleteEvent
  | CompleteEvent
  | ErrorEvent;

// ── Pipeline state ────────────────────────────────────────────

export type LlmInvocation = {
  prompt_preview?: string;
  llm_calls: number;
  last_tokens?: { inputTokens?: number; outputTokens?: number };
};

export type AgentTrace = {
  key: string;
  label: string;
  thinking: string[];
  llm_invocations: LlmInvocation[];
  tool_calls: { message: string; function?: string }[];
  tool_results: { message: string }[];
  completed: boolean;
};

export type PipelineIteration = {
  number: number;
  agents: Record<string, AgentTrace>;
  gaps: string[];
  phase: string;
};

export type PipelineState = {
  status: "running" | "complete" | "error";
  currentIteration: number;
  iterations: PipelineIteration[];
  nameResolution?: {
    original: string;
    scientific: string;
    imppat_url?: string;
  };
  overallGaps: string[];
};

// ── Final interaction result ──────────────────────────────────

export type PhytochemicalDetail = {
  name: string;
  type?: string;
  effect?: string;
  confidence?: string;
};

export type Mechanism = {
  type?: string;
  description: string;
  phytochemicals?: string[];
  enzymes?: string[];
  confidence?: string;
};

export type ReasoningStep = {
  step: number;
  reasoning: string;
  evidence?: string;
};

export type Source = {
  url: string;
  title?: string;
  snippet?: string;
  source_type?: string;
  score?: number;
};

export type KnowledgeGraphNode = {
  data: { id: string; label: string; type: string };
};

export type KnowledgeGraphEdge = {
  data: { source: string; target: string; label: string };
};

export type KnowledgeGraph = {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
};

export type InteractionData = {
  interaction_key: string;
  ayush_name: string;
  allopathy_name: string;
  interaction_exists: boolean;
  interaction_summary: string;
  severity: "NONE" | "MINOR" | "MODERATE" | "MAJOR";
  severity_score: number;
  is_nti: boolean;
  scoring_factors: string[];
  mechanisms: {
    pharmacokinetic: (string | Mechanism)[];
    pharmacodynamic: (string | Mechanism)[];
  };
  phytochemicals_involved: (string | PhytochemicalDetail)[];
  clinical_effects: string[];
  recommendations: string[];
  evidence_quality: "LOW" | "MODERATE" | "HIGH";
  reasoning_chain: ReasoningStep[];
  knowledge_graph: KnowledgeGraph;
  sources: Source[];
  imppat_url?: string;
  drugbank_url?: string;
  disclaimer: string;
  generated_at: string;
};

export type InteractionResult = {
  status: "Success" | "Failed";
  interaction_data?: InteractionData;
  failure_reason?: string;
};
