---
name: git-workflow
description: 规范 Git 操作全流程，包括分支命名、commit message 格式、PR 描述生成、合并策略。当用户说"帮我写 commit"、"创建分支"、"写 PR 描述"、"怎么合并"、"提交代码"时触发。也适用于解决 merge conflict、cherry-pick、rebase 等 Git 操作问题。
---

# Git Workflow

本团队 Git 规范，确保代码历史清晰、可追溯。

## 分支命名规范

```
<type>/<ticket-id>-<short-description>

示例：
feature/PROJ-123-user-login
bugfix/PROJ-456-fix-payment-null
hotfix/PROJ-789-security-patch
refactor/PROJ-101-cleanup-auth-module
chore/update-dependencies
```

| 前缀 | 用途 |
|------|------|
| `feature/` | 新功能开发 |
| `bugfix/` | 非紧急 bug 修复 |
| `hotfix/` | 生产环境紧急修复 |
| `refactor/` | 重构，不改变功能 |
| `chore/` | 依赖更新、配置变更 |
| `docs/` | 文档更新 |

## Commit Message 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

[可选 body]

[可选 footer]
```

**type 列表**：

| type | 含义 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 重构 |
| `test` | 测试相关 |
| `docs` | 文档 |
| `chore` | 构建/工具/依赖 |
| `perf` | 性能优化 |
| `ci` | CI/CD 配置 |

**示例**：
```
feat(auth): add JWT refresh token support

Implements sliding session via refresh tokens.
Access token TTL: 15min, Refresh token TTL: 7d.

Closes PROJ-123
```

**生成 commit message 时的原则**：
1. subject 不超过 72 字符，动词开头，不加句号
2. body 解释"为什么"而非"做了什么"
3. 关联 ticket 用 `Closes #xxx` 或 `Refs #xxx`

## PR 描述模板

```markdown
## 变更说明
<!-- 一句话说清楚这个 PR 做了什么 -->

## 背景 & 动机
<!-- 为什么要做这个变更，关联需求或 bug -->
Closes #[ticket-id]

## 变更内容
- [ ] xxx
- [ ] xxx

## 测试说明
<!-- 如何验证这个变更是正确的 -->
- 单元测试：已添加/已覆盖
- 手动测试步骤：xxx

## 截图（如有 UI 变更）

## 注意事项 & 风险点
<!-- 需要 reviewer 重点关注的地方 -->
```

## 常用操作指南

### 从主干创建新分支
```bash
git checkout main && git pull origin main
git checkout -b feature/PROJ-xxx-description
```

### 保持分支最新（推荐 rebase 而非 merge）
```bash
git fetch origin
git rebase origin/main
# 有冲突时：解决后 git rebase --continue
```

### 整理 commit（提 PR 前）
```bash
# 合并最近 N 个 commit 为一个
git rebase -i HEAD~N
# 将多余的 commit 标记为 squash 或 fixup
```

### 解决 Merge Conflict
```bash
# 查看冲突文件
git status

# 解决后标记为已解决
git add <file>
git rebase --continue   # 或 git merge --continue
```

### Hotfix 流程
```bash
# 从 main 拉 hotfix 分支
git checkout main && git pull
git checkout -b hotfix/PROJ-xxx-description

# 修复完成后合并回 main 和 develop
git checkout main && git merge hotfix/xxx
git checkout develop && git merge hotfix/xxx
git tag -a v1.x.x -m "hotfix: xxx"
```

## 注意事项

- **禁止** 直接 push 到 `main` / `master` 分支
- **禁止** force push 到共享分支
- 每个 PR 关联至少一个 ticket
- PR 合并前需至少 1 位同事 review
