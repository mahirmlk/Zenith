'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchGraphData } from '@/lib/api';

interface NodeData {
  id: string;
  title: string;
  x: number;
  y: number;
  connections: number;
}

interface EdgeData {
  source: string;
  target: string;
}

interface GraphData {
  nodes: NodeData[];
  edges: EdgeData[];
}

function forceDirectedLayout(nodes: NodeData[], edges: EdgeData[], width: number, height: number) {
  const positions = new Map<string, { x: number; y: number; vx: number; vy: number }>();

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.35;

  nodes.forEach((node, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    positions.set(node.id, {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
    });
  });

  for (let iter = 0; iter < 200; iter++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = positions.get(nodes[i].id)!;
        const b = positions.get(nodes[j].id)!;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = 8000 / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }

    edges.forEach((edge) => {
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = dist * 0.008;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    });

    nodes.forEach((node) => {
      const p = positions.get(node.id)!;
      p.vx += (centerX - p.x) * 0.01;
      p.vy += (centerY - p.y) * 0.01;
    });

    nodes.forEach((node) => {
      const p = positions.get(node.id)!;
      p.vx *= 0.7;
      p.vy *= 0.7;
      p.x += p.vx;
      p.y += p.vy;
      const pad = 60;
      p.x = Math.max(pad, Math.min(width - pad, p.x));
      p.y = Math.max(pad, Math.min(height - pad, p.y));
    });
  }

  return positions;
}

export default function GraphPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [paperId, setPaperId] = useState('2301.00001');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  const loadGraph = useCallback(async (id: string) => {
    if (!id.trim()) return;
    try {
      setLoading(true);
      setError(null);
      const rawData = await fetchGraphData(id.trim());
      const nodes: NodeData[] = (rawData.nodes || []).map((n: unknown) => {
        const node = n as Record<string, string>;
        return {
          id: node.id,
          title: node.title || node.id,
          x: 0,
          y: 0,
          connections: 0,
        };
      });
      const edges: EdgeData[] = (rawData.edges || []).map((e: unknown) => {
        const edge = e as Record<string, string>;
        return {
          source: edge.source,
          target: edge.target,
        };
      });

      edges.forEach((e) => {
        const s = nodes.find((n) => n.id === e.source);
        const t = nodes.find((n) => n.id === e.target);
        if (s) s.connections++;
        if (t) t.connections++;
      });

      setData({ nodes, edges });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraph('2301.00001');
  }, [loadGraph]);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: rect.width,
          height: Math.max(400, window.innerHeight - 200),
        });
      }
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const positions = data
    ? forceDirectedLayout(data.nodes, data.edges, dimensions.width, dimensions.height)
    : new Map();

  const maxConnections = Math.max(...(data?.nodes.map((n) => n.connections) || [1]), 1);

  const getNodeRadius = (node: NodeData) => {
    const base = 6;
    const scale = (node.connections / maxConnections) * 14;
    return base + scale;
  };

  const getNodeColor = (node: NodeData) => {
    if (hoveredNode === node.id) return '#4CA9FF';
    if (node.connections === maxConnections) return '#0A1633';
    return '#4E5D78';
  };

  return (
    <main className="flex h-[calc(100vh-64px)] flex-col">
      {/* Header bar */}
      <div className="border-b border-zenith-border bg-white px-6 py-4">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-serif text-[22px] font-normal text-ink-900">Citation Graph</h1>
            <p className="text-[13px] text-zenith-muted">Visualise paper relationships and citations</p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              loadGraph(paperId);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={paperId}
              onChange={(e) => setPaperId(e.target.value)}
              placeholder="Enter ArXiv paper ID"
              className="rounded-lg border border-zenith-border bg-white px-3 py-2 text-[13px] text-ink-900 focus:border-zenith-secondary focus:outline-none focus:ring-1 focus:ring-zenith-secondary/30"
            />
            <button
              type="submit"
              className="rounded-lg bg-ink-900 px-4 py-2 text-[13px] font-medium text-white transition duration-200 hover:bg-ink-800"
            >
              Load
            </button>
          </form>
        </div>
      </div>

      {/* Graph area */}
      <div ref={containerRef} className="relative flex-1 bg-zenith-bg">
        {loading && (
          <div className="flex h-full items-center justify-center">
            <div className="text-zenith-muted">Loading graph...</div>
          </div>
        )}

        {error && (
          <div className="flex h-full items-center justify-center">
            <div className="rounded-lg border border-red-200 bg-red-50/80 p-4 text-[13px] text-red-700">{error}</div>
          </div>
        )}

        {!loading && !error && data && (
          <svg
            width={dimensions.width}
            height={dimensions.height}
            className="absolute inset-0"
          >
            {/* Grid background */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#E3E8EF" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />

            {/* Edges */}
            {data.edges.map((edge, idx) => {
              const start = positions.get(edge.source);
              const end = positions.get(edge.target);
              if (!start || !end) return null;
              const isHighlighted = hoveredNode && (edge.source === hoveredNode || edge.target === hoveredNode);
              return (
                <line
                  key={`edge-${idx}`}
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  stroke={isHighlighted ? '#4CA9FF' : '#E3E8EF'}
                  strokeWidth={isHighlighted ? 2.5 : 1}
                  strokeOpacity={isHighlighted ? 1 : 0.6}
                  strokeLinecap="round"
                />
              );
            })}

            {/* Nodes */}
            {data.nodes.map((node) => {
              const pos = positions.get(node.id);
              if (!pos) return null;
              const r = getNodeRadius(node);
              const isHovered = hoveredNode === node.id;
              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => window.open(`/paper/${node.id}`, '_blank')}
                >
                  {isHovered && (
                    <circle r={r + 8} fill="#4CA9FF" opacity="0.15">
                      <animate attributeName="r" values={`${r + 4};${r + 10};${r + 4}`} dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <circle
                    r={r}
                    fill={getNodeColor(node)}
                    stroke="white"
                    strokeWidth={isHovered ? 3 : 2}
                    className="transition-all duration-200"
                  />
                  <text
                    y={r + 16}
                    textAnchor="middle"
                    className="pointer-events-none select-none"
                    fill={isHovered ? '#0A1633' : '#4E5D78'}
                    style={{ fontSize: '11px', fontWeight: 500 }}
                  >
                    {node.title.length > 30 ? node.title.slice(0, 27) + '...' : node.title}
                  </text>
                  {node.connections > 1 && (
                    <g transform={`translate(${r - 2}, ${-r + 2})`}>
                      <circle r={8} fill="#4CA9FF" />
                      <text
                        textAnchor="middle"
                        dy="3"
                        fill="white"
                        className="pointer-events-none select-none"
                        style={{ fontSize: '9px', fontWeight: 600 }}
                      >
                        {node.connections}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        )}

        {/* Legend */}
        {!loading && !error && data && (
          <div className="absolute bottom-4 left-4 rounded-lg border border-zenith-border bg-white/90 p-3 shadow-soft backdrop-blur-sm">
            <div className="mb-1 text-[12px] font-semibold text-ink-900">Legend</div>
            <div className="flex items-center gap-2 text-[11px] text-zenith-muted">
              <span className="inline-block h-3 w-3 rounded-full bg-ink-900" /> Central paper
            </div>
            <div className="flex items-center gap-2 text-[11px] text-zenith-muted">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-zenith-body" /> Citation
            </div>
            <div className="mt-1 text-[10px] text-zenith-muted-light">
              {data.nodes.length} papers · {data.edges.length} connections
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
