import type { PipelineState } from '../types';
import AgentCard from './AgentCard';

interface Props {
  pipeline: PipelineState;
}

export default function PipelineTimeline({ pipeline }: Props) {
  const isRunning = pipeline.status === 'running';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-gray-200">Pipeline Progress</h2>
        {isRunning && (
          <span className="flex items-center gap-1.5 text-xs text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Running
          </span>
        )}
        {pipeline.status === 'complete' && (
          <span className="text-xs text-green-500 bg-green-900/30 px-2 py-0.5 rounded">
            ✓ Complete
          </span>
        )}
        {pipeline.status === 'error' && (
          <span className="text-xs text-red-400 bg-red-900/30 px-2 py-0.5 rounded">
            ✗ Error
          </span>
        )}
      </div>

      {/* Name resolution */}
      {pipeline.nameResolution && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-green-400 text-sm">✓</span>
            <span className="text-sm font-medium text-gray-300">Name Resolution</span>
          </div>
          <div className="text-xs text-gray-400 space-y-1">
            <p>
              <span className="text-gray-500">Input:</span>{' '}
              <span className="text-gray-200">{pipeline.nameResolution.original}</span>
            </p>
            <p>
              <span className="text-gray-500">Scientific:</span>{' '}
              <span className="text-green-300 font-medium italic">
                {pipeline.nameResolution.scientific}
              </span>
            </p>
            {pipeline.nameResolution.imppat_url && (
              <p>
                <a
                  href={pipeline.nameResolution.imppat_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 underline"
                >
                  IMPPAT phytochemical page ↗
                </a>
              </p>
            )}
          </div>
        </div>
      )}

      {/* Iterations */}
      {pipeline.iterations.map((iter) => (
        <div key={iter.number} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-300">
              Iteration {iter.number}
            </span>
            {iter.gaps.length > 0 && (
              <span className="text-xs text-yellow-400 bg-yellow-900/30 px-2 py-0.5 rounded">
                {iter.gaps.length} gap{iter.gaps.length > 1 ? 's' : ''} identified
              </span>
            )}
          </div>

          <div className="p-4 space-y-3">
            {Object.values(iter.agents).map((agent) => (
              <AgentCard key={agent.key} agent={agent} />
            ))}

            {Object.keys(iter.agents).length === 0 && (
              <p className="text-xs text-gray-600 italic">Initialising agents…</p>
            )}
          </div>

          {iter.gaps.length > 0 && (
            <div className="border-t border-gray-800 px-4 py-3">
              <p className="text-xs font-medium text-yellow-400 mb-2">Information Gaps:</p>
              <ul className="space-y-1">
                {iter.gaps.map((gap, i) => (
                  <li key={i} className="text-xs text-gray-400 flex gap-2">
                    <span className="text-yellow-600">•</span>
                    {gap}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}

      {/* Loading spinner for first iteration */}
      {isRunning && pipeline.iterations.length === 0 && (
        <div className="flex items-center gap-3 text-sm text-gray-400 bg-gray-900 border border-gray-800 rounded-lg p-4">
          <span className="w-4 h-4 border-2 border-gray-600 border-t-green-400 rounded-full animate-spin" />
          Initialising pipeline…
        </div>
      )}

      {/* Overall gaps summary */}
      {pipeline.status === 'complete' && pipeline.overallGaps.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-lg p-4">
          <p className="text-xs font-medium text-yellow-400 mb-2">
            Overall Information Gaps (across all iterations):
          </p>
          <ul className="space-y-1">
            {pipeline.overallGaps.map((g, i) => (
              <li key={i} className="text-xs text-gray-400">• {g}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
