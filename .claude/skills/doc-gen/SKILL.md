---
name: doc-gen
description: 为代码生成注释、README、变更日志、接口文档等各类文档。当用户说"帮我写注释"、"生成 README"、"写文档"、"这段代码需要文档"、"生成 CHANGELOG"、"接口文档怎么写"时触发。支持 Python / Java / Kotlin / TypeScript。
---

# Doc Gen

生成各类开发文档，覆盖代码注释、README、CHANGELOG 三大场景。

## 场景一：代码注释

### Python（Google 风格 Docstring）

```python
def calculate_discount(
    original_price: Decimal,
    member_level: str,
    coupon_code: str | None = None,
) -> tuple[Decimal, str]:
    """计算用户最终折扣价格。

    折扣来源优先级：优惠券 > 会员折扣。两者不叠加，取优惠更大者。

    Args:
        original_price: 商品原价，必须大于 0。
        member_level: 会员等级，可选值：BRONZE / SILVER / GOLD / PLATINUM。
        coupon_code: 优惠券码，为 None 时不使用优惠券。

    Returns:
        (final_price, discount_source) 元组：
        - final_price: 折后价格，保留 2 位小数。
        - discount_source: 折扣来源，"coupon" 或 "member" 或 "none"。

    Raises:
        ValueError: original_price <= 0 时。
        CouponExpiredException: 优惠券已过期时。

    Example:
        >>> price, source = calculate_discount(Decimal("100"), "GOLD", "SAVE20")
        >>> print(price, source)
        80.00 coupon
    """
```

### Kotlin（KDoc）

```kotlin
/**
 * 发送邮件验证码。
 *
 * 验证码有效期 10 分钟，同一邮箱 1 分钟内只能发送一次（防刷限制）。
 *
 * @param email 目标邮箱地址，必须是有效的 email 格式。
 * @param type 验证码用途：[VerificationCodeType.REGISTER] 注册 /
 *             [VerificationCodeType.RESET_PASSWORD] 重置密码。
 * @return 发送结果，包含发送时间和下次可发送时间。
 * @throws RateLimitException 1 分钟内重复发送时抛出。
 * @throws EmailDeliveryException 邮件服务商发送失败时抛出。
 */
fun sendVerificationCode(email: String, type: VerificationCodeType): SendResult
```

### TypeScript（JSDoc / TSDoc）

```typescript
/**
 * 格式化文件大小为人类可读的字符串。
 *
 * @param bytes - 文件大小（字节数），必须为非负整数。
 * @param decimals - 小数位数，默认 2。
 * @returns 格式化后的字符串，如 "1.5 MB"、"256 KB"。
 *
 * @example
 * formatFileSize(1536)        // "1.50 KB"
 * formatFileSize(1048576, 0)  // "1 MB"
 * formatFileSize(0)           // "0 Bytes"
 */
export function formatFileSize(bytes: number, decimals = 2): string
```

---

## 场景二：README 模板

````markdown
# [项目名称]

[一句话描述：这是什么，解决什么问题]

## 快速开始

### 前置条件

- Java 21+ 或 Python 3.12+
- Docker & Docker Compose
- Node.js 20+（前端开发）

### 本地运行

```bash
# 克隆项目
git clone https://github.com/your-org/your-repo.git
cd your-repo

# 启动依赖服务（数据库、Redis）
docker-compose up -d postgres redis

# 后端
./gradlew bootRun
# 或 Python
pip install -r requirements.txt && uvicorn main:app --reload

# 前端（新终端）
cd frontend && npm install && npm run dev
```

服务启动后访问：
- 后端 API：http://localhost:8080
- 前端：http://localhost:3000
- API 文档（Swagger）：http://localhost:8080/swagger-ui.html

### 环境变量

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DB_URL` | 数据库连接串 | `jdbc:postgresql://localhost:5432/myapp` |
| `DB_PASSWORD` | 数据库密码 | — |
| `REDIS_HOST` | Redis 地址 | `localhost` |
| `JWT_SECRET` | JWT 签名密钥 | — |

## 项目结构

```
├── backend/          # Spring Boot 后端
│   ├── src/main/
│   │   ├── controller/
│   │   ├── service/
│   │   ├── repository/
│   │   └── entity/
│   └── src/test/
├── frontend/         # React + TypeScript 前端
│   └── src/
│       ├── components/
│       ├── pages/
│       └── services/
├── docs/             # 文档
│   ├── adr/          # 架构决策记录
│   └── api/          # OpenAPI 规范
└── docker-compose.yml
```

## 开发指南

### 分支策略

- `main`：生产代码，受保护
- `feature/xxx`：新功能开发
- `bugfix/xxx`：Bug 修复

### 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)，详见 [git-workflow skill]。

### 运行测试

```bash
# 后端
./gradlew test

# 前端
npm test -- --coverage
```

## 部署

详见 [docker-deploy skill] 和 `Jenkinsfile`。

## 常见问题

**Q：启动时报 `Connection refused` 数据库错误？**
A：确认 Docker 容器已启动：`docker-compose ps`

**Q：前端调接口报 CORS 错误？**
A：确认后端 `CorsConfig` 已添加本地开发地址。

## 联系方式

- 项目负责人：@xxx
- 技术问题：提 Issue 或联系 @xxx
````

---

## 场景三：CHANGELOG 生成

基于 Git 提交记录自动生成，遵循 [Keep a Changelog](https://keepachangelog.com/) 格式：

```markdown
# Changelog

## [1.2.0] - 2024-03-15

### 新增
- 用户模块支持第三方登录（微信、钉钉）
- 订单列表新增按状态筛选功能
- 新增导出 Excel 报表功能

### 变更
- 用户头像上传改为直传 OSS，减少服务器带宽消耗

### 修复
- 修复并发下单导致库存超卖问题（#142）
- 修复 Safari 浏览器下日期选择器样式错乱问题

### 废弃
- `/api/v1/user/info` 接口已废弃，请迁移至 `/api/v1/users/{id}`

---

## [1.1.0] - 2024-02-28
...
```

**从 Git 历史生成 CHANGELOG 的命令**：

```bash
# 获取上一个 tag 到现在的所有 commit
git log v1.1.0..HEAD --pretty=format:"%s" | grep -E "^(feat|fix|refactor|perf|docs)"
```

---

## 注意事项

- 注释解释**为什么**，不重复代码说**做什么**
- README 保持最小可用状态，`新人 30 分钟内能跑起来`是衡量标准
- CHANGELOG 面向用户，避免技术术语，说清楚**用户能感受到的变化**
