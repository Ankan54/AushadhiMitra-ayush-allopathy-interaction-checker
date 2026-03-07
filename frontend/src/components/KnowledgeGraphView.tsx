import { useEffect, useRef } from 'react';
import type { KnowledgeGraph } from '../types';

interface Props {
  graph: KnowledgeGraph;
}

const NODE_COLORS: Record<string, string> = {
  ayush_plant: '#16a34a',
  allopathy_drug: '#2563eb',
  admet_property: '#8b5cf6',
  cyp_enzyme: '#d97706',
  cyp_enzyme_overlap: '#ef4444',
  phytochemical: '#7c3aed',
  mechanism: '#0891b2',
  clinical_effect: '#dc2626',
};

const NODE_LABELS: Record<string, string> = {
  ayush_plant: 'AYUSH Drug',
  allopathy_drug: 'Allopathy Drug',
  admet_property: 'ADMET Property',
  cyp_enzyme: 'CYP Enzyme',
  cyp_enzyme_overlap: 'CYP Overlap',
  phytochemical: 'Phytochemical',
  mechanism: 'Mechanism',
  clinical_effect: 'Clinical Effect',
};

export default function KnowledgeGraphView({ graph }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || !graph?.nodes?.length) return;

    let cy: any;

    const initCy = async () => {
      const cytoscape = (await import('cytoscape')).default;

      const elements = [
        ...graph.nodes.map((n) => ({
          data: {
            id: n.data.id,
            label: n.data.label,
            nodeType: n.data.type,
          },
        })),
        ...graph.edges.map((e, i) => ({
          data: {
            id: `e${i}`,
            source: e.data.source,
            target: e.data.target,
            label: e.data.label,
          },
        })),
      ];

      cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': (ele: any) =>
                NODE_COLORS[ele.data('nodeType')] ?? '#4b5563',
              label: 'data(label)',
              color: '#e5e7eb',
              'font-size': 10,
              'text-valign': 'bottom',
              'text-margin-y': 4,
              width: 36,
              height: 36,
              'text-max-width': 100,
              'text-wrap': 'wrap',
            },
          },
          {
            selector: 'node[nodeType = "ayush_plant"], node[nodeType = "allopathy_drug"]',
            style: {
              width: 48,
              height: 48,
              'font-size': 12,
              'font-weight': 'bold',
              'text-max-width': 120,
            },
          },
          {
            selector: 'node[nodeType = "admet_property"]',
            style: {
              shape: 'round-rectangle',
              width: 40,
              height: 28,
              'font-size': 9,
              'text-max-width': 90,
            },
          },
          {
            selector: 'node[nodeType = "cyp_enzyme_overlap"]',
            style: {
              'border-width': 3,
              'border-color': '#fbbf24',
              width: 42,
              height: 42,
              'font-size': 11,
              'font-weight': 'bold',
            },
          },
          {
            selector: 'edge',
            style: {
              'line-color': '#4b5563',
              'target-arrow-color': '#4b5563',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              label: 'data(label)',
              color: '#9ca3af',
              'font-size': 8,
              'text-rotation': 'autorotate',
              width: 1.5,
            },
          },
        ],
        layout: {
          name: 'cose',
          animate: false,
          padding: 30,
          nodeRepulsion: 10000,
          idealEdgeLength: 100,
          nodeOverlap: 20,
        } as any,
        userZoomingEnabled: true,
        userPanningEnabled: true,
      });

      cyRef.current = cy;
    };

    initCy();

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [graph]);

  if (!graph?.nodes?.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
        No graph data available
      </div>
    );
  }

  // Only show legend items for node types present in the graph
  const presentTypes = new Set(graph.nodes.map((n) => n.data.type));

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-3">
        {Object.entries(NODE_COLORS)
          .filter(([type]) => presentTypes.has(type))
          .map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{
                  backgroundColor: color,
                  ...(type === 'cyp_enzyme_overlap'
                    ? { border: '2px solid #fbbf24' }
                    : {}),
                }}
              />
              {NODE_LABELS[type] ?? type.replace(/_/g, ' ')}
            </div>
          ))}
      </div>
      <div
        ref={containerRef}
        className="bg-gray-950 rounded-lg border border-gray-800"
        style={{ height: 420 }}
      />
    </div>
  );
}
