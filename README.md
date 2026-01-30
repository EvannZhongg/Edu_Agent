# Edu Agent

智能教辅解析与知识图谱构建系统（当前为可运行骨架与流水线框架）。

## 目录结构

- `config/`：系统配置（YAML/JSON）
- `services/`：微服务代码（gateway / parser / analyzer）
- `scripts/`：安装与运行脚本（MinerU 与依赖）
- `data/`：运行时数据（共享卷、LanceDB、SQLite）

## 快速开始（Windows / PowerShell）

1) 安装 Python 依赖到项目内 `.venv`

```
.\scripts\install_deps.ps1
```

2) 安装 MinerU 到 `F:\Model\mineru`（可改参数）

```
.\scripts\install_mineru.ps1 -InstallPath "F:\Model\mineru"
```

3) 启动网关服务

```
.\scripts\run_gateway.ps1
```

4) 启动 MinerU 解析 Worker

```
.\scripts\run_parser_worker.ps1
```

5) 启动 LLM 分析 Worker

## MinerU 服务模式

当前默认使用 MinerU API 服务（例如你已启动在 `http://localhost:8002`）。  
如需切换 CLI，修改 `config/config.yaml` 中 `mineru.mode` 为 `cli`。

## 前端（Next.js + React Flow）

前端已提供基础可视化页面，位于 `frontend/`：

```
cd frontend
npm install
npm run dev
```

默认请求后端 `http://localhost:8000`，可通过 `frontend/.env.example` 配置。
也可以统一用 `frontend/public/app-config.json` 配置后端地址（前端运行时读取）。

后端端口可在 `config/config.yaml` 的 `gateway.port` 中配置，`scripts/run_gateway.ps1` 会读取该端口启动。

## 一键启动

在项目根目录执行：
```
.\eduagent-server.cmd
```
将同时启动后端、解析/分析 Worker 与前端。

如遇到 `TypeError: fetch failed`（Next.js 版本检查/遥测无法联网），可在 `frontend/.env.local` 中设置：
```
NEXT_TELEMETRY_DISABLED=1
```

```
.\scripts\run_analyzer_worker.ps1
```

## 功能范围（当前已搭建）

- 上传 PDF -> 进入解析队列
- MinerU 输出 middle_json -> 目录树重建（标题/段落/表格/图片）
- VLM/LLM 目录页纠偏（可配置）
- 自动生成 `knowledge_tree.json` 与 `knowledge_tree.md`
- 题库切分与绑定（LLM + 回退规则）
- RAG 入库与检索接口

## 配置说明

核心配置在 `config/config.yaml`，MinerU 支持本地安装路径和 Docker 方式两种模式，并支持自动分析开关。
