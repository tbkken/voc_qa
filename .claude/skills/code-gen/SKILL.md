---
name: code-gen
description: 基于需求描述、接口契约或数据模型生成符合团队规范的代码，包括 Controller、Service、Repository、DTO 等各层代码。当用户说"帮我写代码"、"生成这个功能的代码"、"按接口契约实现"、"生成 CRUD"、"写这个 API 的实现"时触发。生成前先加载 lang-style skill 确保符合规范。
---

# Code Gen

基于需求或接口定义，生成各层代码骨架与实现。

## 执行前置

1. 先读取 `lang-style` skill 确认语言规范
2. 先读取 `repo-context` skill 了解项目结构（如未了解）
3. 确认目标语言和框架

---

## Java / Kotlin（Spring Boot）全层代码模板

以"用户模块"为例，展示标准分层结构。

### Entity（数据库映射）

```kotlin
@Entity
@Table(name = "users")
data class UserEntity(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @Column(unique = true, nullable = false, length = 255)
    val email: String,

    @Column(nullable = false)
    val passwordHash: String,

    @Column(length = 100)
    val name: String? = null,

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    val status: UserStatus = UserStatus.ACTIVE,

    @CreationTimestamp
    @Column(updatable = false)
    val createdAt: LocalDateTime = LocalDateTime.now(),

    @UpdateTimestamp
    val updatedAt: LocalDateTime = LocalDateTime.now(),
)

enum class UserStatus { ACTIVE, INACTIVE }
```

### DTO（请求/响应对象）

```kotlin
data class CreateUserRequest(
    @field:NotBlank(message = "邮箱不能为空")
    @field:Email(message = "邮箱格式不正确")
    val email: String,

    @field:NotBlank
    @field:Size(min = 8, message = "密码至少 8 位")
    val password: String,

    @field:Size(max = 50)
    val name: String? = null,
)

data class UserDto(
    val id: Long,
    val email: String,
    val name: String?,
    val status: String,
    val createdAt: LocalDateTime,
)

// 扩展函数：Entity → DTO
fun UserEntity.toDto() = UserDto(
    id = id,
    email = email,
    name = name,
    status = status.name,
    createdAt = createdAt,
)
```

### Repository

```kotlin
@Repository
interface UserRepository : JpaRepository<UserEntity, Long> {
    fun findByEmail(email: String): Optional<UserEntity>
    fun existsByEmail(email: String): Boolean

    @Query("SELECT u FROM UserEntity u WHERE u.status = :status")
    fun findAllByStatus(
        @Param("status") status: UserStatus,
        pageable: Pageable,
    ): Page<UserEntity>
}
```

### Service

```kotlin
@Service
@Transactional(readOnly = true)
class UserService(
    private val userRepository: UserRepository,
    private val passwordEncoder: PasswordEncoder,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Transactional
    fun createUser(request: CreateUserRequest): UserDto {
        if (userRepository.existsByEmail(request.email)) {
            throw ConflictException("邮箱 ${request.email} 已被注册")
        }

        val user = UserEntity(
            email = request.email,
            passwordHash = passwordEncoder.encode(request.password),
            name = request.name,
        )

        return userRepository.save(user).toDto().also {
            log.info("用户创建成功: id={}, email={}", it.id, it.email)
        }
    }

    fun getUserById(id: Long): UserDto {
        return userRepository.findById(id)
            .map { it.toDto() }
            .orElseThrow { NotFoundException("用户 $id 不存在") }
    }

    fun listUsers(page: Int, pageSize: Int): Page<UserDto> {
        val pageable = PageRequest.of(page - 1, pageSize, Sort.by("createdAt").descending())
        return userRepository.findAll(pageable).map { it.toDto() }
    }
}
```

### Controller

```kotlin
@RestController
@RequestMapping("/api/v1/users")
@Validated
class UserController(
    private val userService: UserService,
) {
    @GetMapping
    fun listUsers(
        @RequestParam(defaultValue = "1") page: Int,
        @RequestParam(defaultValue = "20") @Max(100) pageSize: Int,
    ): ApiResponse<PageResult<UserDto>> {
        val result = userService.listUsers(page, pageSize)
        return ApiResponse.success(PageResult.of(result))
    }

    @GetMapping("/{id}")
    fun getUser(@PathVariable id: Long): ApiResponse<UserDto> {
        return ApiResponse.success(userService.getUserById(id))
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun createUser(@RequestBody @Valid request: CreateUserRequest): ApiResponse<UserDto> {
        return ApiResponse.success(userService.createUser(request))
    }
}
```

### 统一异常处理

```kotlin
@RestControllerAdvice
class GlobalExceptionHandler {

    private val log = LoggerFactory.getLogger(javaClass)

    @ExceptionHandler(NotFoundException::class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    fun handleNotFound(ex: NotFoundException) =
        ApiResponse.error(40401, ex.message ?: "资源不存在")

    @ExceptionHandler(ConflictException::class)
    @ResponseStatus(HttpStatus.CONFLICT)
    fun handleConflict(ex: ConflictException) =
        ApiResponse.error(40901, ex.message ?: "资源冲突")

    @ExceptionHandler(MethodArgumentNotValidException::class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    fun handleValidation(ex: MethodArgumentNotValidException): ApiResponse<Nothing> {
        val message = ex.bindingResult.fieldErrors
            .joinToString("; ") { "${it.field}: ${it.defaultMessage}" }
        return ApiResponse.error(40001, message)
    }

    @ExceptionHandler(Exception::class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    fun handleUnexpected(ex: Exception): ApiResponse<Nothing> {
        log.error("未处理异常", ex)
        return ApiResponse.error(50001, "服务器内部错误")
    }
}
```

---

## Python（FastAPI）全层代码模板

```python
# schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum

class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = Field(None, max_length=50)

class UserDto(BaseModel):
    id: int
    email: str
    name: str | None
    status: UserStatus
    created_at: datetime

    model_config = {"from_attributes": True}

# services/user_service.py
from sqlalchemy.orm import Session
from app.models.user import UserModel
from app.schemas.user import CreateUserRequest, UserDto
from app.core.exceptions import NotFoundException, ConflictException
from app.core.security import hash_password
import logging

log = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, request: CreateUserRequest) -> UserDto:
        if self.db.query(UserModel).filter_by(email=request.email).first():
            raise ConflictException(f"邮箱 {request.email} 已被注册")

        user = UserModel(
            email=request.email,
            password_hash=hash_password(request.password),
            name=request.name,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        log.info("用户创建成功: id=%s, email=%s", user.id, user.email)
        return UserDto.model_validate(user)

    def get_user_by_id(self, user_id: int) -> UserDto:
        user = self.db.query(UserModel).filter_by(id=user_id).first()
        if not user:
            raise NotFoundException(f"用户 {user_id} 不存在")
        return UserDto.model_validate(user)

# api/users.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.user import CreateUserRequest, UserDto
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])

@router.post("", response_model=UserDto, status_code=status.HTTP_201_CREATED)
def create_user(request: CreateUserRequest, db: Session = Depends(get_db)):
    return UserService(db).create_user(request)

@router.get("/{user_id}", response_model=UserDto)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return UserService(db).get_user_by_id(user_id)
```

---

## TypeScript（React + API 调用层）

```typescript
// types/user.ts
export interface UserDto {
  id: string
  email: string
  name: string | null
  status: 'ACTIVE' | 'INACTIVE'
  createdAt: string
}

export interface CreateUserRequest {
  email: string
  password: string
  name?: string
}

// services/userService.ts
import { apiClient } from '@/lib/apiClient'
import type { UserDto, CreateUserRequest } from '@/types/user'

export const userService = {
  async getById(id: string): Promise<UserDto> {
    const { data } = await apiClient.get<{ data: UserDto }>(`/api/v1/users/${id}`)
    return data.data
  },

  async create(request: CreateUserRequest): Promise<UserDto> {
    const { data } = await apiClient.post<{ data: UserDto }>('/api/v1/users', request)
    return data.data
  },
}

// hooks/useUser.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userService } from '@/services/userService'

export function useUser(id: string) {
  return useQuery({
    queryKey: ['users', id],
    queryFn: () => userService.getById(id),
    enabled: !!id,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: userService.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}
```

---

## 代码生成原则

1. 生成后立即指出需要**手动填充**的部分（如业务规则、字段含义）
2. 所有生成代码符合 `lang-style` skill 中的规范
3. 包含必要的**日志埋点**和**错误处理**
4. 不生成测试代码（由 `unit-test-gen` skill 负责）
