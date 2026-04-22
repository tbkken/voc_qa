---
name: knowledge-base
description: 加载团队技术规范、最佳实践和历史决策，作为所有其他 Skill 的背景上下文。当用户说"按我们团队的规范"、"我们团队是怎么做的"、"有没有最佳实践"、"我们的技术栈是什么"时触发。也在其他 Skill 需要团队约定时自动提供上下文。
---

# Knowledge Base

团队技术规范的统一入口，其他 Skill 的背景上下文。

## 技术栈总览

| 层次 | 技术选择 | 备注 |
|------|----------|------|
| 后端（主力） | Kotlin + Spring Boot 3.x | Java 21 |
| 后端（数据/脚本类） | Python 3.12 + FastAPI | 部分遗留 Django |
| 前端 | React 18 + TypeScript | Next.js 或 CRA |
| 数据库 | PostgreSQL 16 | 主存储 |
| 缓存 | Redis 7 | Session + 热点数据 |
| CI/CD | Jenkins | 内部自建 |
| 容器 | Docker + docker-compose | 无 K8s |
| 代码托管 | 内部 Git 服务 | - |

---

## 团队核心约定

### 分支与发布

- `main` 分支保护，禁止直接 push
- PR 合并要求：至少 1 人 Review + Jenkins CI 全绿
- 分支命名：`feature/PROJ-xxx-描述`、`bugfix/`、`hotfix/`
- 版本号：语义化版本（semver），`MAJOR.MINOR.PATCH`
- 每次发布打 Git tag，Jenkins 从 tag 触发生产部署

### 质量门禁（CI 强制检查）

| 检查项 | 标准 |
|--------|------|
| 单元测试 | 全部通过 |
| 测试覆盖率 | 整体 ≥ 70% |
| 代码风格 | checkstyle / ktlint / eslint 零警告 |
| 依赖安全 | 无高危漏洞（npm audit / dependency-check） |

### 错误码规范

```
格式：[HTTP状态前缀][模块码][序号]

40001 = 400通用参数错误
40401 = 404资源不存在
40900 = 409资源冲突
50000 = 500服务器错误

模块码（两位）：
00 = 通用
01 = 用户
02 = 订单
03 = 支付
04 = 商品
```

### 日志规范

```
级别：
ERROR  → 需立即处理，触发告警
WARN   → 需关注，不紧急
INFO   → 关键业务操作（登录、下单、支付成功/失败）
DEBUG  → 调试，生产环境关闭

必须带上：traceId、关键业务 ID（userId/orderId）
禁止打印：密码、token、完整手机号/身份证
```

### 环境划分

| 环境 | 用途 | 触发方式 |
|------|------|----------|
| local | 本地开发 | docker-compose 手动启动 |
| staging | 功能验证 | main 分支合并自动部署 |
| production | 生产 | Jenkins 手动确认发布 |

---

## 文档规范

- **ADR**：架构决策记录 → `docs/adr/ADR-NNN-title.md`
- **API 文档**：OpenAPI 3.0 → `docs/api/openapi.yaml`
- **README**：每个仓库必须有，包含本地启动步骤
- **CHANGELOG**：跟随版本更新，Keep a Changelog 格式
- **复盘报告**：P0/P1 故障 → `docs/postmortem/INC-YYYY-NNN.md`

---

## 详细规范入口

| 主题 | 对应 Skill |
|------|-----------|
| 编码风格（Python/Kotlin/TS） | `lang-style` |
| Git 操作规范 | `git-workflow` |
| API 接口设计 | `api-contract` |
| 架构设计方法 | `arch-designer` |
| CI/CD 流水线 | `cicd-pipeline` |
| Docker 部署 | `docker-deploy` |
| 错误排查 | `error-debug` |
| 线上故障处理 | `incident-response` |
