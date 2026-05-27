'use client';

import { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import * as THREE from 'three';
import { fetchGraphData } from '@/lib/api';

interface NodeData {
  id: string;
  title: string;
  x: number;
  y: number;
  z: number;
}

interface EdgeData {
  source: string;
  target: string;
}

function GraphNode({ node, onClick }: { node: NodeData; onClick: (id: string) => void }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.scale.setScalar(hovered ? 1.3 : 1);
    }
  });

  return (
    <group position={[node.x, node.y, node.z]}>
      <mesh
        ref={meshRef}
        onClick={() => onClick(node.id)}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <sphereGeometry args={[0.3, 16, 16]} />
        <meshStandardMaterial color={hovered ? '#0ea5e9' : '#64748b'} />
      </mesh>
      <Text
        fontSize={0.15}
        color="#1e293b"
        anchorX="center"
        anchorY="middle"
        position={[0, 0.5, 0]}
        maxWidth={2}
      >
        {node.title}
      </Text>
    </group>
  );
}

function GraphEdge({ start, end }: { start: THREE.Vector3; end: THREE.Vector3 }) {
  const points = useMemo(() => [start, end], [start, end]);
  return (
    <line>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[new Float32Array(points.flatMap((p) => [p.x, p.y, p.z])), 3]}
        />
      </bufferGeometry>
      <lineBasicMaterial color="#94a3b8" linewidth={1} />
    </line>
  );
}

function GraphScene({ nodes, edges, onNodeClick }: { nodes: NodeData[]; edges: EdgeData[]; onNodeClick: (id: string) => void }) {
  const nodeMap = useMemo(() => {
    const map = new Map<string, THREE.Vector3>();
    nodes.forEach((n) => map.set(n.id, new THREE.Vector3(n.x, n.y, n.z)));
    return map;
  }, [nodes]);

  return (
    <>
      <ambientLight intensity={0.8} />
      <pointLight position={[10, 10, 10]} />
      {nodes.map((node) => (
        <GraphNode key={node.id} node={node} onClick={onNodeClick} />
      ))}
      {edges.map((edge, idx) => {
        const start = nodeMap.get(edge.source);
        const end = nodeMap.get(edge.target);
        if (!start || !end) return null;
        return <GraphEdge key={idx} start={start} end={end} />;
      })}
      <OrbitControls enablePan enableZoom enableRotate />
    </>
  );
}

export default function GraphPage() {
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [edges, setEdges] = useState<EdgeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const data = await fetchGraphData('demo');
        if (!cancelled) {
          setNodes(data.nodes as NodeData[]);
          setEdges(data.edges as EdgeData[]);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load graph');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleNodeClick = (id: string) => {
    window.location.href = `/paper/${id}`;
  };

  return (
    <main className="h-screen w-screen">
      <div className="absolute left-4 top-4 z-10 rounded-lg bg-white/90 p-3 shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">Citation Graph</h1>
        <p className="text-sm text-gray-600">Click a node to view the paper</p>
      </div>

      {loading && (
        <div className="flex h-full items-center justify-center">
          <div className="text-gray-500">Loading graph...</div>
        </div>
      )}

      {error && (
        <div className="flex h-full items-center justify-center">
          <div className="rounded-lg bg-red-50 p-4 text-red-700">{error}</div>
        </div>
      )}

      {!loading && !error && (
        <Canvas camera={{ position: [5, 5, 5], fov: 50 }}>
          <GraphScene nodes={nodes} edges={edges} onNodeClick={handleNodeClick} />
        </Canvas>
      )}
    </main>
  );
}
