---
name: release-mgr
description: 管理版本发布全流程，包括版本号规划、发布分支创建、Release Notes 生成、回滚方案制定。当用户说"准备发布"、"写发布说明"、"版本怎么打"、"上线前检查"、"需要回滚"、"发布计划"、"生成 Release Notes"时触发。
---

# Release Manager

规范版本发布流程，降低发布风险。

## 版本号规范（语义化版本）

```
v{MAJOR}.{MINOR}.{PATCH}

MAJOR：不兼容的 API 变更（如删除接口、修改字段含义）
MINOR：向后兼容的新功能
PATCH：向后兼容的 Bug 修复
```

**示例**：
- `v1.3.0` → 新增了用户导出功能
- `v1.3.1` → 修复导出时的乱码 Bug
- `v2.0.0` → 重构了认证模块，JWT 格式变更，旧 token 失效

---

## 发布流程

### 第一步：创建发布分支

```bash
# 从 main 拉发布分支
git checkout main && git pull origin main
git checkout -b release/v1.3.0

# 更新版本号
# Java/Kotlin（build.gradle.kts）
sed -i 's/version = ".*"/version = "1.3.0"/' build.gradle.kts

# Python（pyproject.toml）
sed -i 's/^version = ".*"/version = "1.3.0"/' pyproject.toml

# Node.js
npm version 1.3.0 --no-git-tag-version

git add -A
git commit -m "chore: bump version to v1.3.0"
git push origin release/v1.3.0
```

### 第二步：发布前检查清单

```markdown
## 发布前检查 v1.3.0

### 代码质量
- [ ] 所有 feature 分支已合并到 release 分支
- [ ] CI/CD 流水线全部通过（Jenkins 绿色）
- [ ] 测试覆盖率 ≥ 80%
- [ ] 无 P0 安全漏洞

### 功能验证
- [ ] Staging 环境冒烟测试通过
- [ ] 新功能已由产品验收
- [ ] 相关接口文档已更新

### 数据库
- [ ] 数据库迁移脚本已准备（Flyway/Alembic）
- [ ] 迁移脚本已在 Staging 验证
- [ ] 确认迁移是否需要停机或可在线执行

### 依赖与配置
- [ ] 新增环境变量已在生产环境配置
- [ ] 第三方依赖更新已评估（有无 Breaking Change）

### 回滚准备
- [ ] 上一版本镜像仍在仓库中（v1.2.x）
- [ ] 数据库迁移是否可回滚？若不可回滚，记录处理方案
- [ ] 回滚操作手册已准备

### 通知
- [ ] 已通知相关团队发布时间窗口
- [ ] 如有停机，已通知用户
```

### 第三步：生成 Release Notes

```markdown
# Release Notes — v1.3.0

**发布日期**：2024-03-15
**发布类型**：Minor Release（向后兼容）
**发布人**：@xxx
**变更单号**：CHANGE-2024-031

---

## 新功能

### 用户数据导出
用户现在可以将自己的数据导出为 Excel 文件，支持按时间范围筛选。
- 入口：个人中心 → 数据管理 → 导出数据
- 文件格式：Excel（.xlsx）
- 数据范围：订单记录、收货地址、消费统计

### 订单状态推送
订单状态变更时，用户将收到站内消息通知。

---

## Bug 修复

- 修复：批量操作时偶发的超时错误（#234）
- 修复：Safari 下日期选择器无法使用的问题（#241）
- 修复：商品图片在弱网环境下加载失败不重试的问题

---

## 性能优化

- 订单列表查询速度提升约 40%（优化了数据库索引）

---

## 重要注意事项

**无 Breaking Change**，本次更新可无缝升级。

**数据库变更**：
- 新增 `export_records` 表（不影响现有功能）
- `orders` 表新增 `notification_sent` 字段（有默认值，无需迁移数据）

---

## 部署信息

**镜像版本**：
- backend: `registry.example.com/backend:v1.3.0`
- frontend: `registry.example.com/frontend:v1.3.0`

**需要执行的操作**：
1. 执行数据库迁移：`flyway migrate`（约 30 秒，不停机）
2. 滚动更新后端服务
3. 更新前端静态资源

**预计停机时间**：无（滚动更新）
```

### 第四步：打 Tag 并合并

```bash
# 发布成功后打 tag
git tag -a v1.3.0 -m "Release v1.3.0: 用户数据导出、订单通知推送"
git push origin v1.3.0

# 合并回 main
git checkout main
git merge release/v1.3.0 --no-ff -m "Merge release/v1.3.0"
git push origin main

# 同步到 develop（如有长期开发分支）
git checkout develop
git merge release/v1.3.0 --no-ff
git push origin develop
```

---

## 回滚方案

### 快速回滚（服务层，不涉及数据库）

```bash
# 在服务器上执行
# 方案1：回滚到上一版本镜像（最快，< 2 分钟）
docker stop backend
docker run -d \
    --name backend \
    -p 8080:8080 \
    registry.example.com/backend:v1.2.3  # 上一版本

# 验证回滚成功
curl http://localhost:8080/actuator/health
```

### 数据库迁移回滚

```bash
# Flyway 回滚（需要提前写 undo 脚本）
./flyway undo

# Alembic 回滚（Python）
alembic downgrade -1  # 回退一个版本
alembic downgrade base  # 回退到初始状态
```

> ⚠️ **原则**：数据库迁移尽量只做加法（加列、加表），不做减法（删列删表需要多版本过渡）。删列操作分两次发布：第一次停止写入，第二次再删除。

### 回滚决策标准

| 情况 | 处理方式 |
|------|----------|
| 错误率 > 1% 且持续上升 | 立即回滚 |
| P99 响应时间 > 正常 3 倍 | 立即回滚 |
| 核心功能（登录/下单）不可用 | 立即回滚 |
| 非核心功能 Bug，可临时关闭 | 发 hotfix，不回滚 |

---

## 发布后监控（30 分钟观察期）

发布后观察以下指标：

```bash
# 查看应用日志（有无新的 ERROR）
docker logs -f backend --since 5m | grep -E "ERROR|WARN"

# 接口错误率（如有监控系统）
# 正常：< 0.1%，告警：> 1%

# 数据库连接（如有突增说明有连接泄漏）
# 响应时间 P99（对比发布前）
```
