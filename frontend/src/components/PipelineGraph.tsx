import type { PipelineState, PipelineIteration } from '../types';

interface Props {
  pipeline: PipelineState;
}

type NodeStatus = 'idle' | 'active' | 'completed' | 'error';

const AGENT_NODE_COLORS: Record<string, { ring: string; bg: string; text: string; label: string }> = {
  input:       { ring: 'ring-gray-500',    bg: 'bg-gray-800',    text: 'text-gray-300',   label: 'User Input' },
  name_res:    { ring: 'ring-emerald-500', bg: 'bg-emerald-950', text: 'text-emerald-300', label: 'Name Resolution' },
  whitelist:   { ring: 'ring-emerald-500', bg: 'bg-emerald-950', text: 'text-emerald-300', label: 'Whitelist' },
  planner:     { ring: 'ring-indigo-500',  bg: 'bg-indigo-950',  text: 'text-indigo-300',  label: 'Planner' },
  ayush:       { ring: 'ring-green-500',   bg: 'bg-green-950',   text: 'text-green-300',   label: 'AYUSH' },
  allopathy:   { ring: 'ring-blue-500',    bg: 'bg-blue-950',    text: 'text-blue-300',    label: 'Allopathy' },
  research:    { ring: 'ring-cyan-500',    bg: 'bg-cyan-950',    text: 'text-cyan-300',    label: 'Research' },
  reasoning:   { ring: 'ring-orange-500',  bg: 'bg-orange-950',  text: 'text-orange-300',  label: 'Reasoning' },
  compile:     { ring: 'ring-purple-500',  bg: 'bg-purple-950',  text: 'text-purple-300',  label: 'Compile' },
  scorer:      { ring: 'ring-stone-400',   bg: 'bg-stone-900',   text: 'text-stone-300',   label: 'Scorer' },
  output:      { ring: 'ring-emerald-500', bg: 'bg-emerald-950', text: 'text-emerald-300', label: 'Output' },
};

const AGENT_ICONS: Record<string, string> = {
  input: '🔤', name_res: '🔎', whitelist: '✅', planner: '🗺',
  ayush: '🌿', allopathy: '💊', research: '🔬', reasoning: '🧠',
  compile: 'λ', scorer: '📊', output: '📄',
};

function PipelineNode({ nodeKey, status }: { nodeKey: string; status: NodeStatus }) {
  const colors = AGENT_NODE_COLORS[nodeKey] ?? AGENT_NODE_COLORS.input;
  const icon = AGENT_ICONS[nodeKey] ?? '⚙';

  const ringColor =
    status === 'completed' ? 'ring-green-500' :
    status === 'active' ? colors.ring :
    status === 'error' ? 'ring-red-500' :
    'ring-gray-700';

  const bgColor = status === 'idle' ? 'bg-gray-900' : colors.bg;
  const textColor = status === 'idle' ? 'text-gray-600' : colors.text;
  const opacity = status === 'idle' ? 'opacity-50' : 'opacity-100';

  return (
    <div className={`flex flex-col items-center gap-1.5 ${opacity} transition-all duration-500`}>
      <div className={`relative w-12 h-12 rounded-full ${bgColor} ring-2 ${ringColor} flex items-center justify-center transition-all duration-500`}>
        {status === 'active' && (
          <span className="absolute inset-0 rounded-full animate-ping-slow ring-2 ring-current opacity-30" style={{ color: 'inherit' }} />
        )}
        {status === 'completed' ? (
          <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : (
          <span className="text-base">{icon}</span>
        )}
      </div>
      <span className={`text-[10px] font-medium ${textColor} text-center leading-tight max-w-[4.5rem]`}>
        {colors.label}
      </span>
    </div>
  );
}

function Arrow({ active = false }: { active?: boolean }) {
  return (
    <div className="flex items-center self-center -mx-1">
      <div className={`w-6 h-0.5 ${active ? 'bg-gray-500' : 'bg-gray-800'} transition-colors duration-500`} />
      <div
        className={`w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] ${active ? 'border-l-gray-500' : 'border-l-gray-800'} transition-colors duration-500`}
      />
    </div>
  );
}

function FanOutArrows({ active = false }: { active?: boolean }) {
  const c = active ? 'stroke-gray-500' : 'stroke-gray-800';
  return (
    <svg width="24" height="80" viewBox="0 0 24 80" className="self-center -mx-1 shrink-0" style={{ marginTop: '-4px' }}>
      <line x1="0" y1="40" x2="24" y2="8"  className={`${c} transition-colors duration-500`} strokeWidth="2" />
      <line x1="0" y1="40" x2="24" y2="40" className={`${c} transition-colors duration-500`} strokeWidth="2" />
      <line x1="0" y1="40" x2="24" y2="72" className={`${c} transition-colors duration-500`} strokeWidth="2" />
    </svg>
  );
}

function FanInArrows({ active = false }: { active?: boolean }) {
  const c = active ? 'stroke-gray-500' : 'stroke-gray-800';
  return (
    <svg width="24" height="80" viewBox="0 0 24 80" className="self-center -mx-1 shrink-0" style={{ marginTop: '-4px' }}>
      <line x1="0" y1="8"  x2="24" y2="40" className={`${c} transition-colors duration-500`} strokeWidth="2" />
      <line x1="0" y1="40" x2="24" y2="40" className={`${c} transition-colors duration-500`} strokeWidth="2" />
      <line x1="0" y1="72" x2="24" y2="40" className={`${c} transition-colors duration-500`} strokeWidth="2" />
    </svg>
  );
}

function getPrePipelineStatuses(pipeline: PipelineState): Record<string, NodeStatus> {
  const hasNameRes = !!pipeline.nameResolution;
  const hasIterations = pipeline.iterations.length > 0;
  const isRunning = pipeline.status === 'running';
  const isError = pipeline.status === 'error';

  return {
    input: hasNameRes || hasIterations ? 'completed' : (isRunning ? 'active' : (isError ? 'error' : 'idle')),
    name_res: hasNameRes ? 'completed' : (isRunning && !hasIterations ? 'active' : (isError && !hasNameRes ? 'error' : 'idle')),
    whitelist: hasIterations ? 'completed' : (hasNameRes && isRunning ? 'active' : (isError && hasNameRes ? 'error' : 'idle')),
  };
}

function getIterationNodeStatuses(
  iter: PipelineIteration,
  isCurrentIteration: boolean,
  pipelineStatus: string,
): Record<string, NodeStatus> {
  const agents = iter.agents;
  const agentStatus = (key: string): NodeStatus => {
    const a = agents[key];
    if (!a) return isCurrentIteration ? 'idle' : 'idle';
    if (a.completed) return 'completed';
    if (a.thinking.length > 0 || a.llm_invocations.length > 0 || a.tool_calls.length > 0) return 'active';
    return isCurrentIteration ? 'active' : 'idle';
  };

  const plannerStatus = agentStatus('Planner');
  const ayushStatus = agentStatus('AYUSH');
  const alloStatus = agentStatus('Allopathy');
  const researchStatus = agentStatus('Research');
  const reasoningStatus = agentStatus('Reasoning');

  const reasoningDone = agents['Reasoning']?.completed ?? false;

  const compileStatus: NodeStatus = reasoningDone ? 'completed' : (reasoningStatus === 'completed' ? 'active' : 'idle');

  const hasGaps = iter.gaps.length > 0;
  const scorerStatus: NodeStatus =
    (pipelineStatus === 'complete' && !hasGaps) ? 'completed' :
    hasGaps ? 'completed' :
    compileStatus === 'completed' ? 'active' : 'idle';

  return {
    planner: plannerStatus,
    ayush: ayushStatus,
    allopathy: alloStatus,
    research: researchStatus,
    reasoning: reasoningStatus,
    compile: compileStatus,
    scorer: scorerStatus,
  };
}

function IterationRow({
  iter,
  isCurrentIteration,
  pipelineStatus,
  isLast,
}: {
  iter: PipelineIteration;
  isCurrentIteration: boolean;
  pipelineStatus: string;
  isLast: boolean;
}) {
  const s = getIterationNodeStatuses(iter, isCurrentIteration, pipelineStatus);
  const anyActive = Object.values(s).some(v => v === 'active');
  const hasGaps = iter.gaps.length > 0;

  return (
    <div className="space-y-3">
      {/* Iteration label */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-400">Iteration {iter.number}</span>
        {isCurrentIteration && anyActive && (
          <span className="flex items-center gap-1 text-[10px] text-green-400">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Processing
          </span>
        )}
      </div>

      {/* Pipeline nodes */}
      <div className="flex items-center gap-0 overflow-x-auto pb-2">
        <PipelineNode nodeKey="planner" status={s.planner} />
        <FanOutArrows active={s.planner === 'completed'} />
        {/* Parallel agents */}
        <div className="flex flex-col gap-2">
          <PipelineNode nodeKey="ayush" status={s.ayush} />
          <PipelineNode nodeKey="allopathy" status={s.allopathy} />
          <PipelineNode nodeKey="research" status={s.research} />
        </div>
        <FanInArrows active={s.ayush === 'completed' || s.allopathy === 'completed' || s.research === 'completed'} />
        <PipelineNode nodeKey="reasoning" status={s.reasoning} />
        <Arrow active={s.reasoning === 'completed'} />
        <PipelineNode nodeKey="compile" status={s.compile} />
        <Arrow active={s.compile === 'completed'} />
        <PipelineNode nodeKey="scorer" status={s.scorer} />
        {isLast && pipelineStatus === 'complete' && (
          <>
            <Arrow active />
            <PipelineNode nodeKey="output" status="completed" />
          </>
        )}
      </div>

      {/* Gaps between iterations */}
      {hasGaps && (
        <div className="ml-2 bg-yellow-900/20 border border-yellow-800/40 rounded-lg px-3 py-2">
          <p className="text-[10px] font-semibold text-yellow-400 mb-1 uppercase tracking-wide">Information Gaps</p>
          <ul className="space-y-0.5">
            {iter.gaps.map((gap, i) => (
              <li key={i} className="text-[11px] text-yellow-200/70 flex items-start gap-1.5">
                <span className="text-yellow-500 mt-px">⚠</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function PipelineGraph({ pipeline }: Props) {
  const isRunning = pipeline.status === 'running';
  const prePipeline = getPrePipelineStatuses(pipeline);
  const anyPreActive = Object.values(prePipeline).some(v => v === 'active');

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-gray-200">Data Pipeline</h2>
          {isRunning && (
            <span className="flex items-center gap-1.5 text-[10px] text-green-400 font-medium bg-green-900/30 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              Live
            </span>
          )}
          {pipeline.status === 'complete' && (
            <span className="text-[10px] text-green-500 bg-green-900/30 px-2 py-0.5 rounded-full font-medium">
              ✓ Complete
            </span>
          )}
          {pipeline.status === 'error' && (
            <span className="text-[10px] text-red-400 bg-red-900/30 px-2 py-0.5 rounded-full font-medium">
              ✗ Error
            </span>
          )}
        </div>
      </div>

      <div className="p-4 space-y-6">
        {/* Pre-pipeline row */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Pre-Pipeline</span>
            {anyPreActive && (
              <span className="flex items-center gap-1 text-[10px] text-green-400">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              </span>
            )}
          </div>
          <div className="flex items-center gap-0">
            <PipelineNode nodeKey="input" status={prePipeline.input} />
            <Arrow active={prePipeline.input === 'completed'} />
            <PipelineNode nodeKey="name_res" status={prePipeline.name_res} />
            <Arrow active={prePipeline.name_res === 'completed'} />
            <PipelineNode nodeKey="whitelist" status={prePipeline.whitelist} />
          </div>

          {pipeline.nameResolution && (
            <div className="ml-2 text-[11px] text-gray-400">
              <span className="text-gray-600">Resolved:</span>{' '}
              <span className="text-gray-300">{pipeline.nameResolution.original}</span>
              <span className="text-gray-600"> → </span>
              <span className="text-green-300 italic">{pipeline.nameResolution.scientific}</span>
            </div>
          )}
        </div>

        {/* Iteration rows */}
        {pipeline.iterations.map((iter, idx) => (
          <IterationRow
            key={iter.number}
            iter={iter}
            isCurrentIteration={iter.number === pipeline.currentIteration}
            pipelineStatus={pipeline.status}
            isLast={idx === pipeline.iterations.length - 1}
          />
        ))}

        {/* Loading state before first iteration */}
        {isRunning && pipeline.iterations.length === 0 && prePipeline.whitelist === 'completed' && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="w-3.5 h-3.5 border-2 border-gray-700 border-t-green-400 rounded-full animate-spin" />
            Initialising iterative pipeline…
          </div>
        )}
      </div>
    </div>
  );
}
