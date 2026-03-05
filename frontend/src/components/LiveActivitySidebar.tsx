import { useEffect, useRef } from 'react';
import type { TimelineEvent } from '../types';

interface Props {
  events: TimelineEvent[];
  isRunning: boolean;
}

const AGENT_BADGE_COLORS: Record<string, string> = {
  planner: 'bg-indigo-900/60 text-indigo-300',
  ayush: 'bg-green-900/60 text-green-300',
  allopathy: 'bg-blue-900/60 text-blue-300',
  research: 'bg-cyan-900/60 text-cyan-300',
  reasoning: 'bg-orange-900/60 text-orange-300',
};

const EVENT_ICONS: Record<string, string> = {
  pipeline_status: '⚙',
  agent_thinking: '💭',
  llm_call: '🤖',
  llm_response: '↩',
  tool_call: '🔧',
  tool_result: '📦',
  agent_complete: '✅',
  complete: '🏁',
  error: '❌',
};

function formatRelativeTime(ts: number, baseTs: number): string {
  const diff = Math.round((ts - baseTs) / 1000);
  if (diff < 1) return '+0s';
  if (diff < 60) return `+${diff}s`;
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return `+${m}m${s > 0 ? `${s}s` : ''}`;
}

function truncate(str: string, max: number): string {
  if (str.length <= max) return str;
  return str.slice(0, max) + '…';
}

export default function LiveActivitySidebar({ events, isRunning }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  const baseTs = events.length > 0 ? events[0].timestamp : Date.now();

  return (
    <div className="flex flex-col h-full bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">⚡</span>
          <h2 className="text-sm font-bold text-gray-200 uppercase tracking-wide">Live Activity</h2>
        </div>
        {isRunning && (
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[10px] text-green-400 font-medium">Online</span>
          </span>
        )}
        {!isRunning && events.length > 0 && (
          <span className="text-[10px] text-gray-500">{events.length} events</span>
        )}
      </div>

      {/* Event feed */}
      <div className="flex-1 overflow-y-auto min-h-0 px-3 py-2 space-y-1.5">
        {events.length === 0 && !isRunning && (
          <p className="text-xs text-gray-600 text-center py-8 italic">
            Submit a query to see live pipeline activity
          </p>
        )}
        {events.length === 0 && isRunning && (
          <div className="flex items-center gap-2 text-xs text-gray-500 py-4 justify-center">
            <span className="w-3 h-3 border-2 border-gray-700 border-t-green-400 rounded-full animate-spin" />
            Waiting for events…
          </div>
        )}

        {events.map((evt) => (
          <div
            key={evt.id}
            className="group flex gap-2.5 py-1.5 border-b border-gray-800/50 last:border-0"
          >
            {/* Timeline dot */}
            <div className="flex flex-col items-center pt-1 shrink-0">
              <div className={`w-2 h-2 rounded-full ${
                evt.type === 'agent_complete' ? 'bg-green-500' :
                evt.type === 'error' ? 'bg-red-500' :
                evt.type === 'complete' ? 'bg-green-400' :
                'bg-gray-600'
              }`} />
              <div className="w-px flex-1 bg-gray-800 mt-1" />
            </div>

            {/* Content */}
            <div className="min-w-0 flex-1 pb-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] font-medium text-gray-200 leading-tight">
                  {EVENT_ICONS[evt.type] ?? '•'}{' '}
                  {truncate(evt.message, 80)}
                </span>
                {evt.completed && (
                  <span className="text-green-500 text-[10px]">✓</span>
                )}
              </div>

              {evt.detail && (
                <p className="text-[10px] text-gray-500 mt-0.5 leading-snug">
                  {truncate(evt.detail, 120)}
                </p>
              )}

              <div className="flex items-center gap-2 mt-1">
                <span className="text-[9px] text-gray-600 tabular-nums">
                  {formatRelativeTime(evt.timestamp, baseTs)}
                </span>
                {evt.agent && (
                  <span className={`text-[9px] font-semibold px-1.5 py-px rounded uppercase tracking-wider ${
                    AGENT_BADGE_COLORS[evt.agentKey ?? ''] ?? 'bg-gray-800 text-gray-400'
                  }`}>
                    {evt.agent}
                  </span>
                )}
                {evt.iteration && evt.iteration > 0 && (
                  <span className="text-[9px] text-gray-600">
                    iter {evt.iteration}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Pulsing indicator at bottom when running */}
        {isRunning && events.length > 0 && (
          <div className="flex items-center gap-2 py-2 justify-center">
            <span className="w-1 h-1 rounded-full bg-green-400 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1 h-1 rounded-full bg-green-400 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1 h-1 rounded-full bg-green-400 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
