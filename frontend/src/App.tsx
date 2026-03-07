import { useState, useRef, useCallback } from 'react';
import DrugInputForm from './components/DrugInputForm';
import PipelineGraph from './components/PipelineGraph';
import LiveActivitySidebar from './components/LiveActivitySidebar';
import ResultPanel from './components/ResultPanel';
import ErrorDisplay from './components/ErrorDisplay';
import PipelineFlowModal from './components/PipelineFlowModal';
import type {
  WsEvent,
  PipelineState,
  PipelineIteration,
  AgentTrace,
  InteractionResult,
  TimelineEvent,
} from './types';

const AGENT_LABELS_MAP: Record<string, string> = {
  Planner: 'planner',
  AYUSH: 'ayush',
  Allopathy: 'allopathy',
  Research: 'research',
  Reasoning: 'reasoning',
};

function makeAgentTrace(label: string): AgentTrace {
  return {
    key: AGENT_LABELS_MAP[label] ?? label.toLowerCase(),
    label,
    thinking: [],
    llm_invocations: [],
    tool_calls: [],
    tool_results: [],
    completed: false,
  };
}

function makeIteration(num: number): PipelineIteration {
  return { number: num, agents: {}, gaps: [], phase: 'proposer' };
}

function ensureIteration(state: PipelineState, num: number): PipelineState {
  const exists = state.iterations.find((it) => it.number === num);
  if (exists) return state;
  return {
    ...state,
    iterations: [...state.iterations, makeIteration(num)],
    currentIteration: num,
  };
}

function ensureAgent(iter: PipelineIteration, agentLabel: string): PipelineIteration {
  if (iter.agents[agentLabel]) return iter;
  return {
    ...iter,
    agents: { ...iter.agents, [agentLabel]: makeAgentTrace(agentLabel) },
  };
}

function applyEvent(state: PipelineState, e: WsEvent): PipelineState {
  if (e.type === 'pipeline_status') {
    if (e.status === 'name_resolution' && e.valid && e.scientific_name) {
      return {
        ...state,
        nameResolution: {
          original: e.original_name ?? '',
          scientific: e.scientific_name,
          imppat_url: e.imppat_url,
        },
      };
    }
    if (e.status === 'iteration_start' || (e as any).status === 'iteration') {
      const num = e.iteration ?? state.currentIteration + 1;
      return ensureIteration({ ...state, currentIteration: num }, num);
    }
    if (e.status === 'gap_identified' && e.gap) {
      const num = e.iteration ?? state.currentIteration;
      let s = ensureIteration(state, num);
      const idx = s.iterations.findIndex((it) => it.number === num);
      if (idx >= 0) {
        const iters = [...s.iterations];
        iters[idx] = { ...iters[idx], gaps: [...iters[idx].gaps, e.gap!] };
        return { ...s, iterations: iters };
      }
    }
    return state;
  }

  // Agent trace events — auto-create iteration 1 if needed
  const iterNum =
    (e as any).iteration ?? (state.currentIteration > 0 ? state.currentIteration : 1);
  let s = ensureIteration(state, iterNum);
  const idx = s.iterations.findIndex((it) => it.number === iterNum);
  if (idx < 0) return s;

  const iterCopy = { ...s.iterations[idx] };
  const agentLabel = (e as any).agent ?? '';

  if (!agentLabel) return s;

  const iterWithAgent = ensureAgent(iterCopy, agentLabel);
  const agentCopy = { ...iterWithAgent.agents[agentLabel] };

  if (e.type === 'agent_thinking') {
    // Deduplicate consecutive identical thinking messages
    const last = agentCopy.thinking[agentCopy.thinking.length - 1];
    if (e.message && e.message !== last) {
      agentCopy.thinking = [...agentCopy.thinking, e.message];
    }
  } else if (e.type === 'llm_call') {
    if (agentCopy.llm_invocations.length === 0) {
      // First call — store system prompt preview
      agentCopy.llm_invocations = [{ prompt_preview: e.prompt_preview, llm_calls: 1 }];
    } else {
      // Subsequent calls — increment counter, don't duplicate prompt
      const last = agentCopy.llm_invocations[agentCopy.llm_invocations.length - 1];
      agentCopy.llm_invocations = [
        ...agentCopy.llm_invocations.slice(0, -1),
        { ...last, llm_calls: last.llm_calls + 1 },
      ];
    }
  } else if (e.type === 'llm_response') {
    if (agentCopy.llm_invocations.length > 0) {
      const last = agentCopy.llm_invocations[agentCopy.llm_invocations.length - 1];
      agentCopy.llm_invocations = [
        ...agentCopy.llm_invocations.slice(0, -1),
        { ...last, last_tokens: e.tokens },
      ];
    }
  } else if (e.type === 'tool_call') {
    agentCopy.tool_calls = [
      ...agentCopy.tool_calls,
      { message: e.message, function: e.function },
    ];
  } else if (e.type === 'tool_result') {
    agentCopy.tool_results = [...agentCopy.tool_results, { message: e.message }];
  } else if (e.type === 'agent_complete') {
    agentCopy.completed = true;
  }

  const updatedAgents = { ...iterWithAgent.agents, [agentLabel]: agentCopy };
  const updatedIters = [...s.iterations];
  updatedIters[idx] = { ...iterWithAgent, agents: updatedAgents };
  return { ...s, iterations: updatedIters };
}

let _eventIdCounter = 0;

function wsEventToTimeline(e: WsEvent): TimelineEvent | null {
  const base = {
    id: ++_eventIdCounter,
    timestamp: Date.now(),
    type: e.type as TimelineEvent['type'],
  };

  if (e.type === 'pipeline_status') {
    return { ...base, message: e.message, detail: e.status, iteration: e.iteration };
  }
  if (e.type === 'agent_thinking') {
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `Thinking…`, detail: e.message, iteration: e.iteration };
  }
  if (e.type === 'llm_call') {
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `LLM invocation`, detail: e.prompt_preview?.slice(0, 100), iteration: e.iteration };
  }
  if (e.type === 'llm_response') {
    const tokens = e.tokens ? `${e.tokens.inputTokens ?? '?'}in / ${e.tokens.outputTokens ?? '?'}out` : undefined;
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `LLM response`, detail: tokens, iteration: e.iteration };
  }
  if (e.type === 'tool_call') {
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `Tool: ${e.function ?? 'unknown'}`, detail: e.message, iteration: e.iteration };
  }
  if (e.type === 'tool_result') {
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `Tool result`, detail: e.message, iteration: e.iteration };
  }
  if (e.type === 'agent_complete') {
    return { ...base, agent: e.agent, agentKey: e.agent_key ?? AGENT_LABELS_MAP[e.agent], message: `${e.agent} complete`, completed: true, iteration: e.iteration };
  }
  if (e.type === 'complete') {
    return { ...base, message: 'Analysis complete', completed: true };
  }
  if (e.type === 'error') {
    return { ...base, message: `Error: ${e.message}` };
  }
  return null;
}

export default function App() {
  const [ayushDrug, setAyushDrug] = useState('');
  const [allopathyDrug, setAllopathyDrug] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [result, setResult] = useState<InteractionResult | null>(null);
  const [error, setError] = useState<{ message: string; supported_drugs?: string[] } | null>(null);
  const [showFlowModal, setShowFlowModal] = useState(false);
  const [eventLog, setEventLog] = useState<TimelineEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!ayushDrug.trim() || !allopathyDrug.trim()) return;

    // Reset state
    setIsLoading(true);
    setResult(null);
    setError(null);
    _eventIdCounter = 0;
    setEventLog([{
      id: ++_eventIdCounter,
      timestamp: Date.now(),
      type: 'pipeline_status',
      message: 'Analysis started',
      detail: `${ayushDrug.trim()} + ${allopathyDrug.trim()}`,
    }]);
    setPipeline({
      status: 'running',
      currentIteration: 0,
      iterations: [],
      overallGaps: [],
    });

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      // Step 1: POST to start the pipeline
      const resp = await fetch('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ayush_name: ayushDrug.trim(),
          allopathy_name: allopathyDrug.trim(),
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
        const msg = err.detail ?? JSON.stringify(err);
        setError({ message: msg });
        setIsLoading(false);
        setPipeline((p) => p ? { ...p, status: 'error' } : null);
        return;
      }

      const { session_id } = await resp.json();

      // Step 2: Connect WebSocket to stream events
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}/ws/${session_id}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (msg) => {
        let e: WsEvent;
        try {
          e = JSON.parse(msg.data);
        } catch {
          return;
        }

        // Push to timeline log
        const tlEvent = wsEventToTimeline(e);
        if (tlEvent) {
          setEventLog((prev) => [...prev, tlEvent]);
        }

        if (e.type === 'error') {
          setError({ message: e.message, supported_drugs: e.supported_drugs });
          setIsLoading(false);
          setPipeline((p) => p ? { ...p, status: 'error' } : null);
          ws.close();
          return;
        }

        if (e.type === 'complete') {
          setResult(e.result);
          setIsLoading(false);
          setPipeline((p) => p ? { ...p, status: 'complete' } : null);
          return;
        }

        setPipeline((prev) => {
          if (!prev) return prev;
          return applyEvent(prev, e);
        });
      };

      ws.onerror = () => {
        setError({ message: 'WebSocket connection failed. Is the backend running?' });
        setIsLoading(false);
        setPipeline((p) => p ? { ...p, status: 'error' } : null);
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to backend';
      setError({ message: msg });
      setIsLoading(false);
      setPipeline((p) => p ? { ...p, status: 'error' } : null);
    }
  }, [ayushDrug, allopathyDrug]);

  const showSidebar = pipeline !== null || eventLog.length > 0;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="mx-auto px-4 py-3 flex items-center justify-between" style={{ maxWidth: '90rem' }}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">🌿</span>
            <div>
              <h1 className="text-lg font-bold text-white leading-tight">AushadhiMitra</h1>
              <p className="text-xs text-gray-400">AYUSH–Allopathy Interaction Checker</p>
            </div>
          </div>
          <button
            onClick={() => setShowFlowModal(true)}
            className="text-xs text-green-400 hover:text-green-300 border border-green-800 hover:border-green-600 rounded-md px-3 py-1.5 transition-colors"
          >
            CO-MAS Agent Pipeline ↗
          </button>
        </div>
      </header>

      <div className="flex" style={{ minHeight: 'calc(100vh - 57px)' }}>
        {/* Main content area */}
        <main className={`flex-1 min-w-0 px-4 py-6 ${showSidebar ? 'mr-0' : ''}`} style={{ maxWidth: showSidebar ? 'calc(100% - 340px)' : '100%' }}>
          {/* Drug Input Form */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-6 py-5 mb-6 max-w-4xl">
            <DrugInputForm
              ayushDrug={ayushDrug}
              allopathyDrug={allopathyDrug}
              onAyushChange={setAyushDrug}
              onAllopathyChange={setAllopathyDrug}
              onSubmit={handleSubmit}
              isLoading={isLoading}
            />
          </div>

          {/* Error */}
          {error && (
            <div className="max-w-4xl">
              <ErrorDisplay message={error.message} supportedDrugs={error.supported_drugs} />
            </div>
          )}

          {/* Pipeline Graph */}
          {pipeline && !error && (
            <div className="mb-6">
              <PipelineGraph pipeline={pipeline} />
            </div>
          )}

          {/* Result Panel (below pipeline) */}
          {result && !error && (
            <div>
              <ResultPanel result={result} />
            </div>
          )}
        </main>

        {/* Right sidebar: Live Activity */}
        {showSidebar && (
          <aside className="w-[340px] shrink-0 border-l border-gray-800 sticky top-[57px] h-[calc(100vh-57px)]">
            <LiveActivitySidebar events={eventLog} isRunning={isLoading} />
          </aside>
        )}
      </div>

      {/* CO-MAS flow modal */}
      {showFlowModal && <PipelineFlowModal onClose={() => setShowFlowModal(false)} />}
    </div>
  );
}
