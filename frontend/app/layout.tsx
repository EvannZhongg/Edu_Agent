import "./globals.css";
import "reactflow/dist/style.css";

export const metadata = {
  title: "Edu Agent",
  description: "知识树可视化",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>
        <div className="app">
          <main className="content">{children}</main>
          <aside className="sidebar">
            <div className="sidebar-title">功能栏</div>
            <a href="/" className="sidebar-link">知识树</a>
            <a href="/textbook" className="sidebar-link">教辅解析</a>
            <a href="/workbook" className="sidebar-link">练习册解析</a>
            <a href="/manage" className="sidebar-link">资料管理</a>
          </aside>
        </div>
      </body>
    </html>
  );
}
