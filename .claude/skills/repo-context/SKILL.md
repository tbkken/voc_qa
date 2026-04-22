---
name: repo-context
description: 快速理解一个陌生代码库的结构、核心模块、技术栈和入口点。当用户说"帮我看看这个项目"、"这个仓库是做什么的"、"我刚接手这个项目"、"先了解一下代码结构"，或者在做任何其他任务之前需要先理解代码库时，必须首先触发此 skill。这是所有其他 skill 的前置基础，只要涉及一个新的或不熟悉的代码库，都应优先使用此 skill。
---

# Repo Context

快速建立对代码库的全局认知，为后续所有任务提供上下文基础。

## 执行步骤

### 第一步：目录结构扫描

```bash
# 获取顶层结构（忽略噪音目录）
find . -maxdepth 2 -not -path '*/node_modules/*' \
  -not -path '*/.git/*' \
  -not -path '*/__pycache__/*' \
  -not -path '*/target/*' \
  -not -path '*/.gradle/*' \
  -not -path '*/dist/*' \
  -not -path '*/build/*' \
  | sort

# 查看根目录关键配置文件
ls -la | grep -E '\.(json|toml|yaml|yml|xml|gradle|properties|env)$'
```

### 第二步：识别技术栈

根据以下文件判断：

| 文件 | 说明 |
|------|------|
| `package.json` | Node.js 项目，查看 `dependencies` 和 `scripts` |
| `pom.xml` / `build.gradle` | Java/Kotlin 项目，查看依赖和模块结构 |
| `pyproject.toml` / `requirements.txt` / `setup.py` | Python 项目 |
| `Dockerfile` / `docker-compose.yml` | 容器化配置 |
| `Jenkinsfile` | CI/CD 流水线定义 |

**本团队技术栈重点**：
- 后端优先找 Java/Kotlin（Spring Boot）或 Python（FastAPI/Django/Flask）
- 前端优先找 TypeScript/JavaScript（React/Vue/Next.js）
- 部署配置找 `Dockerfile` 和 `docker-compose.yml`
- CI 配置找 `Jenkinsfile`

### 第三步：理解模块边界

```bash
# Java/Kotlin 多模块项目
cat settings.gradle 2>/dev/null || cat settings.gradle.kts 2>/dev/null

# Python 包结构
find . -name "__init__.py" -not -path '*/node_modules/*' | head -20

# 前端工作区
cat package.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('workspaces', 'N/A'), indent=2))" 2>/dev/null
```

### 第四步：找到关键入口

| 类型 | 入口文件 |
|------|----------|
| Spring Boot | `*Application.java` / `*Application.kt` |
| Python Web | `main.py` / `app.py` / `wsgi.py` / `asgi.py` |
| React/Vue | `src/main.tsx` / `src/App.tsx` / `pages/_app.tsx` |
| 通用 | `README.md`（最重要，先读） |

```bash
# 快速找 Spring Boot 入口
find . -name "*Application.kt" -o -name "*Application.java" 2>/dev/null | head -5

# 快速找 Python 入口
find . -maxdepth 3 -name "main.py" -o -name "app.py" | head -5
```

### 第五步：理解数据层

```bash
# 找数据库迁移文件（了解数据模型）
find . -path '*/migrations/*.sql' -o \
       -path '*/migrations/*.py' -o \
       -path '*/flyway/*' -o \
       -path '*/liquibase/*' | head -10

# 找 ORM 模型定义
find . -name "models.py" -o -name "entity/*.kt" -o -name "entity/*.java" | head -10
```

### 第六步：输出诊断报告

完成扫描后，用以下结构输出报告：

```
## 代码库概览

**项目名称**：xxx
**技术栈**：后端（Java Spring Boot 3.x）+ 前端（React + TypeScript）
**部署方式**：Docker Compose

### 模块结构
- `backend/` — Spring Boot 后端，负责 xxx
- `frontend/` — React 前端，负责 xxx
- `shared/` — 共享类型定义

### 关键入口
- 后端启动：`backend/src/main/.../Application.kt`
- 前端启动：`frontend/src/main.tsx`
- CI 流水线：`Jenkinsfile`

### 数据层
- 数据库：PostgreSQL（通过 Flyway 管理迁移）
- 主要模型：User, Order, Product...

### 注意事项
- [发现的特殊配置或需要关注的点]
```

## 注意事项

- 遇到超大仓库（>500 个文件）时，优先读 `README.md`，再做定向扫描
- 读完后将关键信息保存到当前对话上下文，供后续 skill 使用
- 如果发现 `CLAUDE.md` 文件，**立即读取**——这是团队为 Claude Code 专门写的项目说明
