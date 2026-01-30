"use client";

import { useEffect, useMemo, useState } from "react";
import { deleteDoc, listDocs, resumeDoc, fetchTree } from "../../lib/api";
import { loadAppConfig } from "../../lib/config";
import KnowledgeGraph from "../../components/KnowledgeGraph";
import { treeToFlow } from "../../lib/tree";

export default function ManagePage() {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Record<string, any>>({});
  const [apiBase, setApiBase] = useState("http://localhost:8000");
  const apiBaseMemo = useMemo(() => apiBase, [apiBase]);

  useEffect(() => {
    loadAppConfig().then((cfg) => {
      if (cfg.apiBase) setApiBase(cfg.apiBase);
    });
  }, []);

  const refresh = async () => {
    setError(null);
    try {
      const data = await listDocs(apiBaseMemo);
      setItems(data);
    } catch (err: any) {
      setError(err.message || "加载失败");
    }
  };

  useEffect(() => {
    refresh();
  }, [apiBaseMemo]);

  const onDelete = async (docId: string) => {
    if (!confirm("确认删除该文档及其本地数据？")) return;
    await deleteDoc(apiBaseMemo, docId);
    await refresh();
  };

  const onResume = async (docId: string) => {
    await resumeDoc(apiBaseMemo, docId);
    await refresh();
  };

  const onPreview = async (docId: string) => {
    const data = await fetchTree(apiBaseMemo, docId);
    setPreview((prev) => ({ ...prev, [docId]: data.tree }));
  };

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>资料管理</h3>
        <button onClick={refresh}>刷新</button>
      </div>
      <div className="meta">后端地址：{apiBaseMemo}</div>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <div style={{ marginTop: 12 }}>
        {items.length === 0 && <div>暂无文档</div>}
        {items.map((d) => (
          <div
            key={d.doc_id}
            className="panel"
            style={{ marginTop: 12, background: "#0b1220" }}
          >
            <div className="row">
              <div style={{ flex: 1 }}>
                <div><b>{d.filename}</b></div>
                <div className="meta">doc_id: {d.doc_id}</div>
                <div className="meta">状态: {d.status} | 类型: {d.doc_type}</div>
              </div>
              <div className="row">
                {d.has_tree && (
                  <button onClick={() => onPreview(d.doc_id)}>预览</button>
                )}
                {d.status !== "completed" && (
                  <button onClick={() => onResume(d.doc_id)}>继续</button>
                )}
                <button onClick={() => onDelete(d.doc_id)}>删除</button>
              </div>
            </div>
            {preview[d.doc_id] && (
              <div style={{ marginTop: 12 }}>
                <KnowledgeGraph
                  nodes={treeToFlow(preview[d.doc_id], d.filename).nodes}
                  edges={treeToFlow(preview[d.doc_id], d.filename).edges}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
