import React from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import { FlowNode, FlowEdge } from "../lib/tree";

type Props = {
  nodes: FlowNode[];
  edges: FlowEdge[];
};

export default function KnowledgeGraph({ nodes, edges }: Props) {
  return (
    <div style={{ height: 600 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView nodeOrigin={[0, 0]}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
