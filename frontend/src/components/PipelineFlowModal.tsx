interface Props {
  onClose: () => void;
}

export default function PipelineFlowModal({ onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-base font-bold text-white">CO-MAS Agent Pipeline</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Cooperative Multi-Agent System for AYUSH–Allopathy Interaction Analysis
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-xl leading-none transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Diagram */}
        <div className="p-6">
          <svg
            viewBox="0 0 800 920"
            className="w-full"
            style={{ fontFamily: 'system-ui, sans-serif' }}
          >
            {/* ── Background panels ─────────────────────────────── */}
            {/* Pre-pipeline */}
            <rect x="20" y="10" width="760" height="110" rx="10" fill="#1a2e1a" stroke="#22543d" strokeWidth="1" />
            <text x="40" y="32" fontSize="11" fill="#4ade80" fontWeight="bold">PRE-PIPELINE: Name Resolution &amp; Validation</text>

            {/* Iterative loop box */}
            <rect x="20" y="135" width="760" height="650" rx="10" fill="#1a1a2e" stroke="#3730a3" strokeWidth="1.5" strokeDasharray="6 3" />
            <text x="40" y="158" fontSize="11" fill="#818cf8" fontWeight="bold">ITERATIVE CO-MAS LOOP (max 3 iterations)</text>

            {/* ── Pre-pipeline nodes ─────────────────────────────── */}
            {/* User Input */}
            <rect x="50" y="42" width="140" height="50" rx="8" fill="#064e3b" stroke="#059669" strokeWidth="1.5" />
            <text x="120" y="63" textAnchor="middle" fontSize="11" fill="#6ee7b7" fontWeight="bold">User Input</text>
            <text x="120" y="78" textAnchor="middle" fontSize="9" fill="#a7f3d0">AYUSH + Allopathy drug</text>

            {/* Name Resolution */}
            <rect x="240" y="42" width="150" height="50" rx="8" fill="#14532d" stroke="#16a34a" strokeWidth="1.5" />
            <text x="315" y="63" textAnchor="middle" fontSize="11" fill="#86efac" fontWeight="bold">Name Resolution</text>
            <text x="315" y="78" textAnchor="middle" fontSize="9" fill="#bbf7d0">brand → scientific name</text>

            {/* AYUSH Validation */}
            <rect x="440" y="42" width="150" height="50" rx="8" fill="#14532d" stroke="#16a34a" strokeWidth="1.5" />
            <text x="515" y="63" textAnchor="middle" fontSize="11" fill="#86efac" fontWeight="bold">Whitelist Check</text>
            <text x="515" y="78" textAnchor="middle" fontSize="9" fill="#bbf7d0">5 supported AYUSH drugs</text>

            {/* Error output */}
            <rect x="640" y="42" width="120" height="50" rx="8" fill="#450a0a" stroke="#dc2626" strokeWidth="1.5" />
            <text x="700" y="63" textAnchor="middle" fontSize="11" fill="#fca5a5" fontWeight="bold">Error Response</text>
            <text x="700" y="78" textAnchor="middle" fontSize="9" fill="#fecaca">unsupported drug</text>

            {/* Arrows: pre-pipeline */}
            <line x1="190" y1="67" x2="238" y2="67" stroke="#4ade80" strokeWidth="1.5" markerEnd="url(#arrow-green)" />
            <line x1="390" y1="67" x2="438" y2="67" stroke="#4ade80" strokeWidth="1.5" markerEnd="url(#arrow-green)" />
            <line x1="590" y1="67" x2="638" y2="67" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 2" markerEnd="url(#arrow-red)" />
            <text x="610" y="60" fontSize="8" fill="#f87171">invalid</text>
            <line x1="515" y1="92" x2="515" y2="122" stroke="#4ade80" strokeWidth="1.5" markerEnd="url(#arrow-green)" />
            <text x="522" y="112" fontSize="8" fill="#4ade80">valid</text>

            {/* ── Phase 1: Planner ───────────────────────────────── */}
            <rect x="365" y="168" width="200" height="60" rx="8" fill="#1e1b4b" stroke="#6366f1" strokeWidth="2" />
            <text x="465" y="191" textAnchor="middle" fontSize="12" fill="#a5b4fc" fontWeight="bold">🗺 Planner Agent</text>
            <text x="465" y="206" textAnchor="middle" fontSize="9" fill="#c7d2fe">generate_execution_plan</text>
            <text x="465" y="218" textAnchor="middle" fontSize="9" fill="#c7d2fe">+ failure feedback (on retry)</text>

            <line x1="515" y1="122" x2="465" y2="166" stroke="#818cf8" strokeWidth="1.5" markerEnd="url(#arrow-indigo)" />

            {/* ── Phase 2: Proposer ──────────────────────────────── */}
            <text x="400" y="258" textAnchor="middle" fontSize="10" fill="#818cf8">PROPOSER PHASE (parallel)</text>
            <line x1="465" y1="228" x2="400" y2="265" stroke="#6366f1" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />
            <line x1="465" y1="228" x2="540" y2="265" stroke="#6366f1" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />
            <line x1="465" y1="228" x2="680" y2="265" stroke="#6366f1" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />

            {/* AYUSH Agent */}
            <rect x="50" y="270" width="180" height="80" rx="8" fill="#14532d" stroke="#16a34a" strokeWidth="1.5" />
            <text x="140" y="292" textAnchor="middle" fontSize="11" fill="#86efac" fontWeight="bold">🌿 AYUSH Agent</text>
            <text x="140" y="308" textAnchor="middle" fontSize="8" fill="#bbf7d0">ayush_name_resolver</text>
            <text x="140" y="320" textAnchor="middle" fontSize="8" fill="#bbf7d0">imppat_lookup</text>
            <text x="140" y="332" textAnchor="middle" fontSize="8" fill="#bbf7d0">search_cyp_interactions</text>
            <line x1="400" y1="265" x2="230" y2="310" stroke="#6366f1" strokeWidth="1.2" markerEnd="url(#arrow-green)" />

            {/* Allopathy Agent */}
            <rect x="275" y="270" width="190" height="80" rx="8" fill="#1e3a5f" stroke="#2563eb" strokeWidth="1.5" />
            <text x="370" y="292" textAnchor="middle" fontSize="11" fill="#93c5fd" fontWeight="bold">💊 Allopathy Agent</text>
            <text x="370" y="308" textAnchor="middle" fontSize="8" fill="#bfdbfe">allopathy_drug_lookup</text>
            <text x="370" y="320" textAnchor="middle" fontSize="8" fill="#bfdbfe">web_search (DrugBank)</text>
            <text x="370" y="332" textAnchor="middle" fontSize="8" fill="#bfdbfe">extract drugbank_url</text>

            {/* Research Agent */}
            <rect x="510" y="270" width="180" height="80" rx="8" fill="#134e4a" stroke="#0d9488" strokeWidth="1.5" />
            <text x="600" y="292" textAnchor="middle" fontSize="11" fill="#99f6e4" fontWeight="bold">🔬 Research Agent</text>
            <text x="600" y="308" textAnchor="middle" fontSize="8" fill="#ccfbf1">web_search (PubMed)</text>
            <text x="600" y="320" textAnchor="middle" fontSize="8" fill="#ccfbf1">clinical evidence</text>
            <text x="600" y="332" textAnchor="middle" fontSize="8" fill="#ccfbf1">pharmacology studies</text>
            <line x1="540" y1="265" x2="540" y2="268" stroke="#6366f1" strokeWidth="1.2" />
            <line x1="680" y1="265" x2="600" y2="268" stroke="#6366f1" strokeWidth="1.2" markerEnd="url(#arrow-teal)" />

            {/* Merge arrows down */}
            <line x1="140" y1="350" x2="140" y2="375" stroke="#4ade80" strokeWidth="1.2" />
            <line x1="370" y1="350" x2="370" y2="375" stroke="#93c5fd" strokeWidth="1.2" />
            <line x1="600" y1="350" x2="600" y2="375" stroke="#5eead4" strokeWidth="1.2" />
            <line x1="140" y1="375" x2="465" y2="390" stroke="#818cf8" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />
            <line x1="370" y1="375" x2="465" y2="390" stroke="#818cf8" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />
            <line x1="600" y1="375" x2="465" y2="390" stroke="#818cf8" strokeWidth="1.2" markerEnd="url(#arrow-indigo)" />

            {/* ── Phase 3: Reasoning Agent ───────────────────────── */}
            <rect x="330" y="395" width="270" height="90" rx="8" fill="#431407" stroke="#ea580c" strokeWidth="2" />
            <text x="465" y="416" textAnchor="middle" fontSize="11" fill="#fdba74" fontWeight="bold">🧠 Reasoning Agent (Evaluator)</text>
            <text x="465" y="430" textAnchor="middle" fontSize="8" fill="#fed7aa">calculate_severity</text>
            <text x="465" y="442" textAnchor="middle" fontSize="8" fill="#fed7aa">build_knowledge_graph</text>
            <text x="465" y="454" textAnchor="middle" fontSize="8" fill="#fed7aa">returns short analysis JSON</text>
            <text x="465" y="466" textAnchor="middle" fontSize="8" fill="#fdba74" fontStyle="italic">↓ orchestrator calls compile Lambda directly</text>

            {/* ── Compile Lambda ─────────────────────────────────── */}
            <rect x="330" y="503" width="270" height="55" rx="8" fill="#3b1c5a" stroke="#9333ea" strokeWidth="1.5" />
            <text x="465" y="524" textAnchor="middle" fontSize="10" fill="#d8b4fe" fontWeight="bold">λ compile_and_validate_output</text>
            <text x="465" y="539" textAnchor="middle" fontSize="8" fill="#e9d5ff">programmatic JSON assembly</text>
            <text x="465" y="551" textAnchor="middle" fontSize="8" fill="#e9d5ff">injects IMPPAT + DrugBank URLs</text>

            <line x1="465" y1="485" x2="465" y2="501" stroke="#ea580c" strokeWidth="1.5" markerEnd="url(#arrow-orange)" />

            {/* ── Phase 4: Scorer ────────────────────────────────── */}
            <rect x="330" y="575" width="270" height="70" rx="8" fill="#1c1917" stroke="#78716c" strokeWidth="1.5" />
            <text x="465" y="596" textAnchor="middle" fontSize="11" fill="#d6d3d1" fontWeight="bold">📊 Scorer (deterministic)</text>
            <text x="465" y="610" textAnchor="middle" fontSize="8" fill="#a8a29e">quality checks: fields, sources,</text>
            <text x="465" y="622" textAnchor="middle" fontSize="8" fill="#a8a29e">mechanisms, reasoning_chain</text>
            <text x="465" y="634" textAnchor="middle" fontSize="8" fill="#a8a29e">score 0–100 → pass (≥60) / fail</text>

            <line x1="465" y1="558" x2="465" y2="573" stroke="#9333ea" strokeWidth="1.5" markerEnd="url(#arrow-purple)" />

            {/* ── Decision diamond ───────────────────────────────── */}
            <polygon points="465,665 515,695 465,725 415,695" fill="#292524" stroke="#78716c" strokeWidth="1.5" />
            <text x="465" y="692" textAnchor="middle" fontSize="9" fill="#d6d3d1">Score</text>
            <text x="465" y="705" textAnchor="middle" fontSize="9" fill="#d6d3d1">≥ 60?</text>

            <line x1="465" y1="645" x2="465" y2="663" stroke="#78716c" strokeWidth="1.5" markerEnd="url(#arrow-grey)" />

            {/* YES → Final Output */}
            <line x1="465" y1="725" x2="465" y2="755" stroke="#4ade80" strokeWidth="2" markerEnd="url(#arrow-green)" />
            <text x="473" y="744" fontSize="9" fill="#4ade80">YES / iter≥3</text>

            <rect x="330" y="758" width="270" height="55" rx="8" fill="#064e3b" stroke="#059669" strokeWidth="2" />
            <text x="465" y="778" textAnchor="middle" fontSize="11" fill="#6ee7b7" fontWeight="bold">✅ Final Output JSON</text>
            <text x="465" y="793" textAnchor="middle" fontSize="8" fill="#a7f3d0">interaction_data, reasoning_chain</text>
            <text x="465" y="805" textAnchor="middle" fontSize="8" fill="#a7f3d0">knowledge_graph, sources, URLs</text>

            {/* NO → retry arc */}
            <line x1="415" y1="695" x2="100" y2="695" stroke="#ef4444" strokeWidth="1.5" markerEnd="url(#arrow-red)" />
            <text x="250" y="688" textAnchor="middle" fontSize="9" fill="#f87171">NO (score {'<'} 60)</text>
            <line x1="100" y1="695" x2="100" y2="200" stroke="#ef4444" strokeWidth="1.5" />
            <line x1="100" y1="200" x2="363" y2="200" stroke="#ef4444" strokeWidth="1.5" markerEnd="url(#arrow-red)" />
            <text x="80" y="450" fontSize="9" fill="#f87171" transform="rotate(-90 80 450)">retry with gap feedback</text>

            {/* ── Arrow markers ──────────────────────────────────── */}
            <defs>
              <marker id="arrow-green" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#4ade80" />
              </marker>
              <marker id="arrow-red" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#ef4444" />
              </marker>
              <marker id="arrow-indigo" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#818cf8" />
              </marker>
              <marker id="arrow-orange" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#ea580c" />
              </marker>
              <marker id="arrow-purple" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#9333ea" />
              </marker>
              <marker id="arrow-teal" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#5eead4" />
              </marker>
              <marker id="arrow-grey" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#78716c" />
              </marker>
            </defs>

            {/* ── Legend ─────────────────────────────────────────── */}
            <rect x="20" y="840" width="760" height="70" rx="6" fill="#111827" stroke="#374151" strokeWidth="1" />
            <text x="40" y="858" fontSize="10" fill="#9ca3af" fontWeight="bold">Legend:</text>
            <circle cx="130" cy="854" r="5" fill="#1e1b4b" stroke="#6366f1" strokeWidth="1.5" />
            <text x="140" y="858" fontSize="9" fill="#c7d2fe">Bedrock Agent</text>
            <rect x="210" y="849" width="10" height="10" rx="2" fill="#3b1c5a" stroke="#9333ea" strokeWidth="1.2" />
            <text x="225" y="858" fontSize="9" fill="#d8b4fe">Lambda Function</text>
            <rect x="315" y="849" width="10" height="10" rx="2" fill="#1c1917" stroke="#78716c" strokeWidth="1.2" />
            <text x="330" y="858" fontSize="9" fill="#d6d3d1">Deterministic Logic</text>
            <line x1="430" y1="854" x2="460" y2="854" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 2" markerEnd="url(#arrow-red)" />
            <text x="465" y="858" fontSize="9" fill="#f87171">Retry path</text>
            <line x1="540" y1="854" x2="570" y2="854" stroke="#4ade80" strokeWidth="1.5" markerEnd="url(#arrow-green)" />
            <text x="575" y="858" fontSize="9" fill="#4ade80">Success path</text>

            <text x="40" y="878" fontSize="9" fill="#6b7280" fontStyle="italic">
              All agent traces (thinking, LLM prompts, tool calls) are streamed to the UI in real time via WebSocket
            </text>
          </svg>
        </div>

        {/* Description */}
        <div className="px-6 pb-6 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-gray-400">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-green-400 font-semibold mb-1">Proposer Phase</p>
            <p>Three agents run in parallel to gather data: AYUSH phytochemicals (IMPPAT), allopathy drug data (DrugBank), and clinical research evidence (PubMed).</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-orange-400 font-semibold mb-1">Evaluator Phase</p>
            <p>Reasoning Agent performs evidence-based analysis, calling tools for severity scoring and knowledge graph construction. Returns a concise analysis JSON to avoid LLM timeouts.</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-purple-400 font-semibold mb-1">Scorer Phase</p>
            <p>Deterministic quality checker validates completeness: required fields, source count, mechanisms, reasoning chain. Score {'<'} 60 triggers another iteration with targeted feedback.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
