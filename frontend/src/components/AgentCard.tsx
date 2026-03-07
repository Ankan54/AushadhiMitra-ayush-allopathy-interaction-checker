import { useState } from 'react';
import type { AgentTrace } from '../types';

const AGENT_COLORS: Record<string, string> = {
  planner: 'text-purple-400 border-purple-800',
  ayush: 'text-green-400 border-green-800',
  allopathy: 'text-blue-400 border-blue-800',
  research: 'text-cyan-400 border-cyan-800',
  reasoning: 'text-orange-400 border-orange-800',
};

const AGENT_ICONS: Record<string, string> = {
  planner: '📋',
  ayush: '🌿',
  allopathy: '💊',
  research: '🔬',
  reasoning: '🧠',
};

interface Props {
  agent: AgentTrace;
}

export default function AgentCard({ agent }: Props) {
  const [expanded, setExpanded] = useState(false);
  const colorClass = AGENT_COLORS[agent.key] ?? 'text-gray-400 border-gray-700';
  const icon = AGENT_ICONS[agent.key] ?? '🤖';

  const totalLlmCalls = agent.llm_invocations.reduce((s, inv) => s + inv.llm_calls, 0);
  const hasContent =
    agent.thinking.length > 0 ||
    agent.llm_invocations.length > 0 ||
    agent.tool_calls.length > 0;

  return (
    <div className={`agent-card border ${colorClass.split(' ')[1]}`}>
      <button
        onClick={() => hasContent && setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className={`text-sm font-semibold ${colorClass.split(' ')[0]}`}>
            {agent.label}
          </span>
          {agent.completed && (
            <span className="text-xs text-green-500 bg-green-900/30 px-1.5 py-0.5 rounded">✓</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {totalLlmCalls > 0 && (
            <span className="text-xs text-gray-500">{totalLlmCalls} LLM calls</span>
          )}
          {agent.tool_calls.length > 0 && (
            <span className="text-xs text-gray-500">{agent.tool_calls.length} tools</span>
          )}
          {hasContent && (
            <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
          )}
        </div>
      </button>

      {expanded && hasContent && (
        <div className="border-t border-gray-800 px-4 py-3 space-y-4 text-xs">
          {/* System prompt / LLM invocations */}
          {agent.llm_invocations.length > 0 && (
            <div>
              <p className="text-gray-500 font-medium mb-2 uppercase tracking-wide">
                System Prompt
                {agent.llm_invocations[0].llm_calls > 1 && (
                  <span className="ml-2 text-blue-400 bg-blue-900/30 px-1.5 py-0.5 rounded">
                    × {agent.llm_invocations[0].llm_calls} LLM invocations
                  </span>
                )}
              </p>
              <pre className="bg-gray-950 rounded p-3 text-gray-400 whitespace-pre-wrap break-words leading-relaxed max-h-40 overflow-y-auto">
                {agent.llm_invocations[0].prompt_preview || '(no preview)'}
              </pre>
              {agent.llm_invocations[0].llm_calls > 1 && (
                <p className="text-gray-600 mt-1 italic">
                  The system prompt above is sent once. The agent made {agent.llm_invocations[0].llm_calls} total LLM invocations (e.g. for each tool call).
                </p>
              )}
            </div>
          )}

          {/* Thinking steps */}
          {agent.thinking.length > 0 && (
            <div>
              <p className="text-gray-500 font-medium mb-2 uppercase tracking-wide">Thinking</p>
              <div className="space-y-2">
                {agent.thinking.map((t, i) => (
                  <div key={i} className="bg-gray-950 rounded p-2.5">
                    {agent.thinking.length > 1 && (
                      <span className="text-gray-600 font-medium">Step {i + 1}: </span>
                    )}
                    <span className="text-gray-300">{t}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tool calls */}
          {agent.tool_calls.length > 0 && (
            <div>
              <p className="text-gray-500 font-medium mb-2 uppercase tracking-wide">Tool Calls</p>
              <div className="space-y-1.5">
                {agent.tool_calls.map((tc, i) => (
                  <div key={i} className="bg-gray-950 rounded p-2.5 flex items-start gap-2">
                    <span className="text-yellow-500 mt-0.5">⚙</span>
                    <span className="text-gray-300 break-all">{tc.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tool results */}
          {agent.tool_results.length > 0 && (
            <div>
              <p className="text-gray-500 font-medium mb-2 uppercase tracking-wide">Tool Results</p>
              <div className="space-y-1.5">
                {agent.tool_results.map((tr, i) => (
                  <div key={i} className="bg-gray-950 rounded p-2.5">
                    <span className="text-green-400">↩ </span>
                    <span className="text-gray-400">{tr.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
