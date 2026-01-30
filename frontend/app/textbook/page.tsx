"use client";

import UploadPanel from "../../components/UploadPanel";

export default function TextbookPage() {
  return (
    <UploadPanel
      docType="textbook"
      title="教辅上传解析"
      description="上传教辅 PDF，自动进入 MinerU 解析与后续知识树构建流程。"
    />
  );
}
