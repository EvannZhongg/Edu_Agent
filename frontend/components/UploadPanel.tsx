"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { uploadPdf, fetchTaskStatus, fetchDocStatus, listDocs } from "../lib/api";
import { loadAppConfig } from "../lib/config";

type Props = {
  docType: "textbook" | "workbook";
  title: string;
  description?: string;
};

export default function UploadPanel({ docType, title, description }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [targetDocId, setTargetDocId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const [docStatus, setDocStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const pollingRef = useRef<any>(null);
  const listRef = useRef<any>(null);

  const [apiBase, setApiBase] = useState("http://localhost:8000");
  const apiBaseMemo = useMemo(() => apiBase, [apiBase]);

  useEffect(() => {
    loadAppConfig().then((cfg) => {
      if (cfg.apiBase) setApiBase(cfg.apiBase);
    });
  }, []);

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }, []);

  const onPick = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  }, []);

  const startPolling = useCallback((taskId: string, docId: string) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const [t, d] = await Promise.all([
          fetchTaskStatus(apiBaseMemo, taskId),
          fetchDocStatus(apiBaseMemo, docId),
        ]);
        setTaskStatus(t);
        setDocStatus(d);
        if (d?.status === "completed" || d?.status === "failed") {
          clearInterval(pollingRef.current);
        }
      } catch (err: any) {
        setError(err.message || "轮询失败");
      }
    }, 3000);
  }, [apiBaseMemo]);

  const refreshDocs = useCallback(async () => {
    try {
      const data = await listDocs(apiBaseMemo);
      setDocs(data.filter((d: any) => d.doc_type === docType));
    } catch (err: any) {
      setError(err.message || "文档列表加载失败");
    }
  }, [apiBaseMemo, docType]);

  useEffect(() => {
    refreshDocs();
    if (listRef.current) clearInterval(listRef.current);
    listRef.current = setInterval(refreshDocs, 5000);
    return () => {
      if (listRef.current) clearInterval(listRef.current);
    };
  }, [refreshDocs]);

  const onUpload = useCallback(async () => {
    if (!file) {
      setError("请先选择 PDF");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await uploadPdf(apiBaseMemo, file, docType, targetDocId || undefined);
      setResult(res);
      if (res?.task_id && res?.doc_id) {
        startPolling(res.task_id, res.doc_id);
      }
      refreshDocs();
    } catch (err: any) {
      setError(err.message || "上传失败");
    } finally {
      setBusy(false);
    }
  }, [apiBaseMemo, file, docType, targetDocId, startPolling]);

  const progressOf = (status: string) => {
    if (!status) return 0;
    if (status === "uploaded") return 5;
    if (status === "parsing") return 30;
    if (status === "parsed") return 50;
    if (status === "analyzing") return 75;
    if (status === "binding") return 85;
    if (status === "completed") return 100;
    if (status === "failed") return 100;
    return 10;
  };

  return (
    <div className="panel">
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      <div className="meta">后端地址：{apiBaseMemo}</div>
      <div
        className="dropzone"
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {file ? (
          <div>已选择：{file.name}</div>
        ) : (
          <div>拖拽 PDF 到此处，或点击选择文件</div>
        )}
        <input type="file" accept="application/pdf" onChange={onPick} />
      </div>

      {docType === "workbook" && (
        <div style={{ marginTop: 12 }}>
          <input
            placeholder="绑定的教辅 doc_id（可选）"
            value={targetDocId}
            onChange={(e) => setTargetDocId(e.target.value)}
            style={{ width: 360 }}
          />
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <button onClick={onUpload} disabled={busy}>
          {busy ? "上传中..." : "开始解析"}
        </button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 12 }}>
          <h4>上传结果</h4>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}

      {taskStatus && (
        <div style={{ marginTop: 12 }}>
          <h4>任务状态</h4>
          <pre>{JSON.stringify(taskStatus, null, 2)}</pre>
        </div>
      )}

      {docStatus && (
        <div style={{ marginTop: 12 }}>
          <h4>文档状态</h4>
          <pre>{JSON.stringify(docStatus, null, 2)}</pre>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <h4>当前任务列表</h4>
        {docs.length === 0 && <div>暂无文档</div>}
        {docs.map((d) => (
          <div
            key={d.doc_id}
            className="panel"
            style={{ marginTop: 10, background: "#0b1220" }}
          >
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div style={{ flex: 1 }}>
                <div><b>{d.filename}</b></div>
                <div className="meta">doc_id: {d.doc_id}</div>
                <div className="meta">状态: {d.status} | 步骤: {d.last_step || "-"}</div>
                {d.error_message && (
                  <div style={{ color: "#f87171" }}>错误: {d.error_message}</div>
                )}
              </div>
              <div style={{ minWidth: 120, textAlign: "right" }}>
                <div className="badge">{d.status}</div>
                <div className="meta">{progressOf(d.status)}%</div>
              </div>
            </div>
            <div className="progress">
              <div
                className="progress-bar"
                style={{ width: `${progressOf(d.status)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
