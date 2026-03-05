import { useState } from 'react';
import type { InteractionResult, ReasoningStep, Source, Mechanism } from '../types';
import KnowledgeGraphView from './KnowledgeGraphView';

const URL_REGEX = /https?:\/\/[^\s"',<>)\]]+/g;

function TextWithLinks({ text, className }: { text: string; className?: string }) {
  if (!text) return <span className={className}>{text ?? ''}</span>;
  const parts = text.split(URL_REGEX);
  const urls = text.match(URL_REGEX) || [];
  if (urls.length === 0) return <span className={className}>{text}</span>;

  const elements: React.ReactNode[] = [];
  parts.forEach((part, i) => {
    elements.push(<span key={`t${i}`}>{part}</span>);
    if (i < urls.length) {
      elements.push(
        <a
          key={`u${i}`}
          href={urls[i]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 underline break-all"
        >
          {urls[i]}
        </a>
      );
    }
  });
  return <span className={className}>{elements}</span>;
}

const SEVERITY_CLASSES: Record<string, string> = {
  NONE: 'severity-none',
  MINOR: 'severity-minor',
  MODERATE: 'severity-moderate',
  MAJOR: 'severity-major',
};

const EVIDENCE_COLORS: Record<string, string> = {
  HIGH: 'text-green-400',
  MODERATE: 'text-yellow-400',
  LOW: 'text-red-400',
};

interface Props {
  result: InteractionResult;
}

export default function ResultPanel({ result }: Props) {
  const [activeTab, setActiveTab] = useState<'summary' | 'drugs' | 'mechanisms' | 'reasoning' | 'graph' | 'sources'>(
    'summary'
  );

  if (result.status !== 'Success' || !result.interaction_data) {
    return (
      <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-yellow-300 mb-1">Pipeline did not produce a valid result</h3>
        <p className="text-sm text-gray-400">
          {result.failure_reason ?? 'The analysis may have been incomplete. Please try again.'}
        </p>
      </div>
    );
  }

  const d = result.interaction_data;
  const severityClass = SEVERITY_CLASSES[d.severity] ?? 'severity-none';

  const tabs = [
    { key: 'summary', label: 'Summary' },
    { key: 'drugs', label: 'Drug Info' },
    { key: 'mechanisms', label: 'Mechanisms' },
    { key: 'reasoning', label: 'Reasoning' },
    { key: 'graph', label: 'Knowledge Graph' },
    { key: 'sources', label: `Sources (${d.sources?.length ?? 0})` },
  ] as const;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-base font-semibold text-white mb-1">Interaction Analysis</h2>
            <p className="text-sm text-gray-400">
              <span className="text-green-300 italic">{d.ayush_name}</span>
              <span className="text-gray-600 mx-2">+</span>
              <span className="text-blue-300">{d.allopathy_name}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`severity-badge ${severityClass}`}>
              {d.severity} ({d.severity_score}/100)
            </span>
            <span className={`text-xs font-medium ${EVIDENCE_COLORS[d.evidence_quality] ?? 'text-gray-400'}`}>
              {d.evidence_quality} confidence
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800 overflow-x-auto">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-2.5 text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === key
                ? 'text-white border-b-2 border-green-500 bg-gray-800/50'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-6">
        {/* Summary */}
        {activeTab === 'summary' && (
          <div className="space-y-4">
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-1">Interaction Summary</p>
              <p className="text-sm text-gray-200 leading-relaxed">{d.interaction_summary || 'No summary available.'}</p>
            </div>
            {d.interaction_exists !== undefined && (
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${d.interaction_exists ? 'bg-red-400' : 'bg-green-400'}`}
                />
                <span className="text-sm text-gray-300">
                  {d.interaction_exists ? 'Interaction detected' : 'No significant interaction detected'}
                </span>
              </div>
            )}
            {d.clinical_effects?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-2">Clinical Effects</p>
                <ul className="space-y-1">
                  {d.clinical_effects.map((e, i) => (
                    <li key={i} className="text-sm text-gray-300 flex gap-2">
                      <span className="text-orange-400">•</span> {e}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {d.recommendations?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-2">Recommendations</p>
                <ul className="space-y-1.5">
                  {d.recommendations.map((r, i) => (
                    <li key={i} className="text-sm text-gray-300 flex gap-2">
                      <span className="text-blue-400 mt-0.5">→</span> {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-gray-600 italic border-t border-gray-800 pt-3">{d.disclaimer}</p>
          </div>
        )}

        {/* Drug Info */}
        {activeTab === 'drugs' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* AYUSH */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-green-400">🌿</span>
                <h3 className="text-sm font-semibold text-green-300">AYUSH Drug</h3>
              </div>
              <p className="text-sm text-gray-200 italic mb-3">{d.ayush_name}</p>
              {d.imppat_url && (
                <a
                  href={d.imppat_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 underline"
                >
                  IMPPAT Phytochemical Database ↗
                </a>
              )}
              {d.phytochemicals_involved?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">Key Phytochemicals Involved:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.phytochemicals_involved.slice(0, 10).map((p, i) => {
                      const name = typeof p === 'string' ? p : p.name;
                      return (
                        <span key={i} className="text-xs bg-green-900/40 text-green-300 px-2 py-0.5 rounded">
                          {name}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Allopathy */}
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-blue-400">💊</span>
                <h3 className="text-sm font-semibold text-blue-300">Allopathy Drug</h3>
              </div>
              <p className="text-sm text-gray-200 mb-3">{d.allopathy_name}</p>
              {d.drugbank_url && (
                <a
                  href={d.drugbank_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 underline"
                >
                  DrugBank Entry ↗
                </a>
              )}
              {d.is_nti && (
                <div className="mt-3 bg-red-900/30 text-red-300 text-xs rounded px-2 py-1.5">
                  ⚠ Narrow Therapeutic Index (NTI) drug — requires close monitoring
                </div>
              )}
              {d.scoring_factors?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">Severity Factors:</p>
                  <ul className="space-y-0.5">
                    {d.scoring_factors.map((f, i) => (
                      <li key={i} className="text-xs text-gray-400">• {f}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Mechanisms */}
        {activeTab === 'mechanisms' && (
          <div className="space-y-5">
            {d.mechanisms?.pharmacokinetic?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-purple-400 mb-3">Pharmacokinetic Mechanisms</h3>
                <ul className="space-y-2">
                  {d.mechanisms.pharmacokinetic.map((m, i) => {
                    const mech = m as any;
                    const desc = typeof m === 'string' ? m : mech.description ?? mech.mechanism ?? '';
                    const evidence = typeof m !== 'string' ? mech.evidence : '';
                    const confidence = typeof m !== 'string' ? mech.confidence : '';
                    return (
                      <li key={i} className="text-sm text-gray-300 bg-purple-900/20 rounded p-3">
                        <TextWithLinks text={desc || JSON.stringify(m)} />
                        {evidence && (
                          <p className="text-xs text-gray-500 italic mt-1">
                            Evidence: <TextWithLinks text={evidence} />
                          </p>
                        )}
                        {confidence && (
                          <span className="text-xs text-gray-600 mt-1 inline-block">
                            Confidence: {confidence}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {d.mechanisms?.pharmacodynamic?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-cyan-400 mb-3">Pharmacodynamic Mechanisms</h3>
                <ul className="space-y-2">
                  {d.mechanisms.pharmacodynamic.map((m, i) => {
                    const mech = m as any;
                    const desc = typeof m === 'string' ? m : mech.description ?? mech.mechanism ?? '';
                    const evidence = typeof m !== 'string' ? mech.evidence : '';
                    const confidence = typeof m !== 'string' ? mech.confidence : '';
                    return (
                      <li key={i} className="text-sm text-gray-300 bg-cyan-900/20 rounded p-3">
                        <TextWithLinks text={desc || JSON.stringify(m)} />
                        {evidence && (
                          <p className="text-xs text-gray-500 italic mt-1">
                            Evidence: <TextWithLinks text={evidence} />
                          </p>
                        )}
                        {confidence && (
                          <span className="text-xs text-gray-600 mt-1 inline-block">
                            Confidence: {confidence}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {!d.mechanisms?.pharmacokinetic?.length && !d.mechanisms?.pharmacodynamic?.length && (
              <p className="text-sm text-gray-500">No mechanism data available.</p>
            )}
          </div>
        )}

        {/* Reasoning chain */}
        {activeTab === 'reasoning' && (
          <div className="space-y-4">
            {d.reasoning_chain?.length > 0 ? (
              d.reasoning_chain.map((step: ReasoningStep, i) => (
                <div key={i} className="bg-gray-800/50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-bold text-orange-400 bg-orange-900/30 px-2 py-0.5 rounded">
                      Step {step.step ?? i + 1}
                    </span>
                  </div>
                  <p className="text-sm text-gray-200 leading-relaxed mb-2">
                    <TextWithLinks text={step.reasoning} />
                  </p>
                  {step.evidence && (
                    <p className="text-xs text-gray-500 italic">
                      Evidence: <TextWithLinks text={step.evidence} />
                    </p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-gray-500">No reasoning chain available.</p>
            )}
          </div>
        )}

        {/* Knowledge graph */}
        {activeTab === 'graph' && (
          <KnowledgeGraphView graph={d.knowledge_graph} />
        )}

        {/* Sources */}
        {activeTab === 'sources' && (
          <div className="space-y-3">
            {d.sources?.length > 0 ? (
              d.sources.map((src: Source, i) => (
                <div key={i} className="bg-gray-800/50 rounded-lg p-3">
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-400 hover:text-blue-300 underline font-medium"
                  >
                    {src.title || src.url}
                  </a>
                  {src.source_type && (
                    <span className="ml-2 text-xs text-gray-500 bg-gray-700 px-1.5 py-0.5 rounded">
                      {src.source_type}
                    </span>
                  )}
                  {src.snippet && (
                    <p className="text-xs text-gray-400 mt-1 leading-relaxed">{src.snippet}</p>
                  )}
                  {src.score !== undefined && (
                    <p className="text-xs text-gray-600 mt-0.5">Relevance: {(src.score * 100).toFixed(0)}%</p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-sm text-gray-500">No sources cited.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
