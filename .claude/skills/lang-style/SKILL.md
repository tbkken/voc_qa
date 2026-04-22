---
name: lang-style
description: 加载团队各语言的编码规范，确保生成的代码符合团队风格。当用户说"按我们的规范写"、"检查代码风格"、"格式不对"、"lint 报错"，或者在生成任何 Python / Java / Kotlin / TypeScript / JavaScript 代码之前，都应触发此 skill 来获取对应语言规范。
---

# Lang Style

团队三种语言的编码规范速查。生成代码前先确认语言，加载对应规范。

## Python 规范

**格式化工具**：`black` + `isort` + `flake8`

```python
# 正确示例
from typing import Optional

def get_user_by_id(user_id: int) -> Optional[dict]:
    """根据 ID 查询用户。

    Args:
        user_id: 用户唯一标识

    Returns:
        用户信息字典，不存在时返回 None
    """
    ...
```

**关键规则**：
- 所有函数和方法必须有类型注解（Python 3.10+）
- 所有公共函数必须有 docstring（Google 风格）
- 类名 `PascalCase`，函数和变量 `snake_case`，常量 `UPPER_SNAKE_CASE`
- 行长度上限 88（black 默认）
- import 顺序：标准库 → 第三方 → 本地，每组之间空行
- 使用 `dataclass` 或 `pydantic` 定义数据模型，禁止裸字典传递结构化数据
- 异常处理：捕获具体异常类型，禁止裸 `except:`

**项目结构惯例**：
```
src/
  api/          # 路由层（FastAPI router / Django view）
  services/     # 业务逻辑层
  repositories/ # 数据访问层
  models/       # 数据模型
  schemas/      # 请求/响应 schema（pydantic）
  core/         # 配置、依赖注入、中间件
tests/
  unit/
  integration/
```

---

## Java / Kotlin 规范

**格式化工具**：Checkstyle + ktlint（Kotlin）

### Kotlin（优先）

```kotlin
// 正确示例
data class UserDto(
    val id: Long,
    val email: String,
    val createdAt: LocalDateTime,
)

@Service
class UserService(
    private val userRepository: UserRepository,
) {
    fun findById(id: Long): UserDto {
        return userRepository.findById(id)
            .map { it.toDto() }
            .orElseThrow { UserNotFoundException(id) }
    }
}
```

**关键规则**：
- 优先使用 Kotlin，新代码尽量不写 Java
- 使用 `data class` 而非 POJO
- 善用 Kotlin 标准库：`let`、`apply`、`also`、`run`
- 不可为空类型与可空类型明确区分（`String` vs `String?`），禁止 `!!` 滥用
- 依赖注入通过构造器注入（不用 `@Autowired` 字段注入）
- 异常：业务异常继承 `RuntimeException`，命名以 `Exception` 结尾
- 日志使用 SLF4J：`private val log = LoggerFactory.getLogger(javaClass)`

**分层规范**：
```
controller/   # @RestController，只做参数校验和响应组装
service/      # @Service，业务逻辑，事务边界在此层
repository/   # @Repository，继承 JpaRepository
entity/       # @Entity，数据库映射
dto/          # 请求/响应对象
exception/    # 自定义异常
```

### Java（存量代码维护）

- 遵循 Google Java Style Guide
- 所有字段 `private`，通过 Lombok `@Getter`/`@Setter` 暴露
- 使用 `Optional` 代替 null 返回

---

## TypeScript / JavaScript 规范

**工具链**：ESLint + Prettier + TypeScript strict mode

```typescript
// 正确示例
interface UserProfile {
  id: string;
  email: string;
  createdAt: Date;
}

async function fetchUserProfile(userId: string): Promise<UserProfile> {
  const response = await api.get<UserProfile>(`/users/${userId}`);
  return response.data;
}
```

**关键规则**：
- 全面使用 TypeScript，禁止 `any`（用 `unknown` + 类型收窄代替）
- 组件用函数组件 + Hooks，禁用 class component
- 命名：组件 `PascalCase`，函数和变量 `camelCase`，常量 `UPPER_SNAKE_CASE`，文件名 `kebab-case`
- 异步统一用 `async/await`，禁止 `.then().catch()` 链式调用（除非链式更清晰）
- 状态管理：局部状态用 `useState`，跨组件用 Context 或 Zustand
- API 调用封装在 `services/` 目录，不在组件里直接 `fetch`
- 错误边界：关键组件添加 `ErrorBoundary`

**前端目录惯例**：
```
src/
  components/   # 通用 UI 组件
  pages/        # 页面级组件（Next.js）或路由视图
  services/     # API 调用封装
  hooks/        # 自定义 Hooks
  stores/       # 全局状态
  types/        # 全局类型定义
  utils/        # 工具函数
```

---

## 通用原则（所有语言）

1. **函数单一职责**：一个函数只做一件事，超过 40 行考虑拆分
2. **避免魔法数字**：用命名常量代替裸数字
3. **提前返回**：减少嵌套，优先处理错误/边界情况
4. **日志规范**：INFO 记录关键业务操作，ERROR 记录异常，DEBUG 记录调试信息，生产环境不打 DEBUG
5. **注释说"为什么"**：代码说"做什么"，注释解释"为什么这样做"
