import { useEffect, useRef } from 'react';
import type { KnowledgeGraph } from '../types';

interface Props {
  graph: KnowledgeGraph;
}

const NODE_COLORS: Record<string, string> = {
  ayush_plant: '#16a34a',
  allopathy_drug: '#2563eb',
  phytochemical: '#7c3aed',
  cyp_enzyme: '#d97706',
  mechanism: '#0891b2',
  clinical_effect: '#dc2626',
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
              'text-max-width': 80,
              'text-wrap': 'wrap',
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
          padding: 20,
          nodeRepulsion: 8000,
          idealEdgeLength: 80,
        },
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

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-3">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-xs text-gray-400">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            {type.replace('_', ' ')}
          </div>
        ))}
      </div>
      <div
        ref={containerRef}
        className="bg-gray-950 rounded-lg border border-gray-800"
        style={{ height: 400 }}
      />
    </div>
  );
}
