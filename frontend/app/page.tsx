"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import KnowledgeGraph from "../components/KnowledgeGraph";
import { fetchTree } from "../lib/api";
import { treeToFlow, treeToMarkdown } from "../lib/tree";
import { loadAppConfig } from "../lib/config";

export default function Page() {
  const [docId, setDocId] = useState("");
  const [tree, setTree] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const searchParams = useSearchParams();

  const [apiBase, setApiBase] = useState("http://localhost:8000");
  const apiBaseMemo = useMemo(() => apiBase, [apiBase]);

  useEffect(() => {
    loadAppConfig().then((cfg) => {
      if (cfg.apiBase) setApiBase(cfg.apiBase);
    });
  }, []);

  useEffect(() => {
    const id = searchParams.get("doc_id");
    if (id) setDocId(id);
  }, [searchParams]);

  const loadTree = async () => {
    setError(null);
    if (!docId) {
      setError("请输入 doc_id");
      return;
    }
    try {
      const data = await fetchTree(apiBaseMemo, docId);
      setTree(data.tree);
    } catch (err: any) {
      setError(err.message || "加载失败");
    }
  };

  const flow = tree ? treeToFlow(tree) : { nodes: [], edges: [] };
  const markdown = tree ? treeToMarkdown(tree) : "";

  return (
    <main>
      <div className="panel">
        <div className="row">
          <input
            placeholder="输入 doc_id"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            style={{ width: 360 }}
          />
          <button onClick={loadTree}>加载知识树</button>
        </div>
        <div className="meta">后端地址：{apiBaseMemo}</div>
        {error && <p style={{ color: "red" }}>{error}</p>}
      </div>

      <div style={{ marginTop: 16 }} className="panel">
        <h3>知识树可视化</h3>
        <KnowledgeGraph nodes={flow.nodes} edges={flow.edges} />
      </div>

      <div style={{ marginTop: 16 }} className="panel">
        <h3>Markdown</h3>
        <pre>{markdown}</pre>
      </div>

      <div style={{ marginTop: 16 }} className="panel">
        <h3>JSON</h3>
        <pre>{tree ? JSON.stringify(tree, null, 2) : ""}</pre>
      </div>
    </main>
  );
}
