"use client";

import UploadPanel from "../../components/UploadPanel";

export default function WorkbookPage() {
  return (
    <UploadPanel
      docType="workbook"
      title="练习册上传解析"
      description="上传练习册 PDF，解析后进行题目切分与章节绑定。"
    />
  );
}
