---
name: security-scan
description: 识别代码中的安全漏洞，包括注入攻击、越权访问、敏感信息泄露、依赖漏洞等。当用户说"安全扫描"、"代码有没有安全问题"、"SQL 注入"、"XSS 漏洞"、"权限校验"、"敏感信息泄露"、"依赖有没有漏洞"时触发。
---

# Security Scan

识别常见安全漏洞，给出修复方案。

## 安全检查清单（按风险等级）

### 🔴 P0：必须修复

#### 1. SQL 注入

```python
# ❌ 危险：字符串拼接 SQL
def get_user(username: str):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    db.execute(query)

# ✅ 安全：参数化查询
def get_user(username: str):
    db.execute("SELECT * FROM users WHERE username = :username",
               {"username": username})

# ✅ 安全：ORM
User.query.filter_by(username=username).first()
```

```kotlin
// ❌ 危险
val query = "SELECT * FROM users WHERE email = '$email'"
entityManager.createNativeQuery(query)

// ✅ 安全：JPA 参数绑定
@Query("SELECT u FROM User u WHERE u.email = :email")
fun findByEmail(@Param("email") email: String): Optional<User>
```

#### 2. 越权访问（IDOR）

```kotlin
// ❌ 危险：只用路径参数，不校验归属
@GetMapping("/orders/{orderId}")
fun getOrder(@PathVariable orderId: Long): OrderDto {
    return orderService.getById(orderId)  // 任何用户都能看任何订单
}

// ✅ 安全：校验当前用户是否有权访问
@GetMapping("/orders/{orderId}")
fun getOrder(
    @PathVariable orderId: Long,
    @AuthenticationPrincipal user: UserPrincipal,
): OrderDto {
    val order = orderService.getById(orderId)
    if (order.userId != user.id && !user.hasRole("ADMIN")) {
        throw ForbiddenException("无权访问此订单")
    }
    return order
}
```

#### 3. 敏感信息泄露

```python
# ❌ 危险：密码出现在日志
log.info(f"用户登录: email={email}, password={password}")

# ❌ 危险：API 响应返回密码 hash
return {"id": user.id, "email": user.email, "password_hash": user.password_hash}

# ❌ 危险：token 存储在 localStorage（易受 XSS 攻击）
# 前端：localStorage.setItem('token', accessToken)

# ✅ 安全：日志脱敏
log.info(f"用户登录: email={email}")  # 不记录密码

# ✅ 安全：DTO 明确排除敏感字段
class UserDto(BaseModel):
    id: int
    email: str
    name: str | None
    # 不包含 password_hash

# ✅ 安全：token 用 httpOnly cookie
response.set_cookie("access_token", token, httponly=True, secure=True, samesite="lax")
```

#### 4. 硬编码密钥

```python
# ❌ 危险
JWT_SECRET = "my-super-secret-key-123"
DB_PASSWORD = "admin123"

# ✅ 安全：从环境变量读取
import os
JWT_SECRET = os.environ["JWT_SECRET"]  # 启动时若缺少环境变量直接报错

# ✅ 安全：使用 pydantic settings
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    jwt_secret: str
    db_password: str
    class Config:
        env_file = ".env"
```

---

### 🟡 P1：建议修复

#### 5. 不安全的反序列化

```kotlin
// ❌ 危险：直接反序列化用户输入
@PostMapping("/import")
fun importData(@RequestBody data: String) {
    val obj = ObjectMapper().readValue(data, Any::class.java)  // 有风险
}

// ✅ 安全：指定明确的目标类型
@PostMapping("/import")
fun importData(@RequestBody @Valid request: ImportRequest) {
    // 使用强类型，不用 Any
}
```

#### 6. 缺少接口限流

```kotlin
// ✅ 使用 Bucket4j 或 Spring Cloud Gateway 限流
@PostMapping("/auth/login")
@RateLimiter(name = "login", fallbackMethod = "loginRateLimitFallback")
fun login(@RequestBody request: LoginRequest): TokenDto { ... }

// 或在 Nginx 层配置
// limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
```

#### 7. 不安全的文件上传

```python
# ❌ 危险：不校验文件类型
@router.post("/upload")
async def upload(file: UploadFile):
    with open(f"uploads/{file.filename}", "wb") as f:  # 路径穿越风险
        f.write(await file.read())

# ✅ 安全：校验类型 + 随机文件名 + 大小限制
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB

@router.post("/upload")
async def upload(file: UploadFile):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "不支持的文件类型")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "文件超过大小限制")
    filename = f"{uuid4()}{Path(file.filename).suffix}"
    # 存到 OSS，不存本地
    oss_client.upload(filename, content)
```

#### 8. 前端 XSS

```typescript
// ❌ 危险：直接注入 HTML
element.innerHTML = userInput

// ❌ 危险：React 中
<div dangerouslySetInnerHTML={{ __html: userContent }} />

// ✅ 安全：用 textContent 或 React 的自动转义
element.textContent = userInput
// React 默认对 {} 内容转义，不需要额外处理
<div>{userContent}</div>

// 如果必须渲染富文本，使用 DOMPurify 消毒
import DOMPurify from 'dompurify'
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userContent) }} />
```

---

### 🟢 P2：优化项

#### 9. 依赖漏洞扫描

```bash
# Python
pip install safety
safety check -r requirements.txt

# Node.js
npm audit
npm audit fix  # 自动修复

# Java（OWASP Dependency Check）
./gradlew dependencyCheckAnalyze
# 报告：build/reports/dependency-check-report.html
```

#### 10. 密码存储

```kotlin
// ❌ 危险：明文存储或 MD5
val hash = MessageDigest.getInstance("MD5").digest(password.toByteArray())

// ✅ 安全：BCrypt（Spring Security 内置）
@Bean
fun passwordEncoder(): PasswordEncoder = BCryptPasswordEncoder(12)

// 使用
val hash = passwordEncoder.encode(rawPassword)
val isValid = passwordEncoder.matches(rawPassword, storedHash)
```

---

## 安全扫描输出格式

```
## 安全扫描结果

**扫描范围**：[文件或模块]
**发现问题**：P0 x 个，P1 x 个，P2 x 个

### 🔴 P0（必须修复）

**[文件:行号]** SQL 注入风险
问题代码：[代码片段]
修复方案：[具体代码]

### 🟡 P1（建议修复）
...

### 🟢 P2（可选优化）
...
```

## 注意事项

- P0 问题发现后**立即通知**安全/负责人，不等 code review 流程
- 修复安全问题的 commit 不要在 commit message 里暴露漏洞细节
- 生产环境的安全问题修复后，检查日志确认是否已被利用
