---
name: unit-test-gen
description: 为纯业务逻辑函数生成单元测试，使用 Mock 隔离所有外部依赖，专注验证函数自身的逻辑分支。当用户说"帮我写单元测试"、"生成 unit test"、"测试这个函数的逻辑"时触发。注意：需要连接真实数据库验证完整调用链时，请用 integration-test-gen skill。支持 Python（pytest）、Java/Kotlin（JUnit5 + Mockito）、TypeScript（Jest/Vitest）。
---

# Unit Test Gen

验证函数自身的业务逻辑，Mock 隔离一切外部依赖，运行极快适合每次提交都跑。

## 适用范围

**适合**：纯计算函数、业务规则分支、异常处理逻辑

**不适合**（请用 integration-test-gen）：
- 验证数据库查询是否正确
- 验证 SQL 事务、外键约束
- 验证接口到数据库的完整调用链

## 测试用例设计原则

每个被测函数/方法，必须覆盖：

1. **Happy Path**：正常输入，期望的正常输出
2. **边界条件**：空值、零值、最大值、最小值、空列表
3. **异常路径**：无效输入、依赖抛出异常时的处理
4. **业务规则分支**：每个 if/when/switch 分支至少一个用例

命名规范：`test_[被测函数]_[场景]_[期望结果]`

---

## Python（pytest）

```python
# 被测代码示例
class UserService:
    def create_user(self, email: str, password: str) -> User:
        if not email or "@" not in email:
            raise ValueError("Invalid email")
        if len(password) < 8:
            raise ValueError("Password too short")
        return self.repo.save(User(email=email, password=hash(password)))
```

```python
# 生成的测试
import pytest
from unittest.mock import MagicMock, patch

class TestUserService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = UserService(repo=self.mock_repo)

    # Happy Path
    def test_create_user_valid_input_returns_user(self):
        email, password = "test@example.com", "securepass123"
        mock_user = User(email=email)
        self.mock_repo.save.return_value = mock_user

        result = self.service.create_user(email, password)

        assert result == mock_user
        self.mock_repo.save.assert_called_once()

    # 边界条件
    def test_create_user_empty_email_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid email"):
            self.service.create_user("", "securepass123")

    def test_create_user_invalid_email_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid email"):
            self.service.create_user("notanemail", "securepass123")

    def test_create_user_short_password_raises_value_error(self):
        with pytest.raises(ValueError, match="Password too short"):
            self.service.create_user("test@example.com", "short")

    # 边界值：密码恰好 8 位（合法）
    def test_create_user_password_exactly_8_chars_succeeds(self):
        self.mock_repo.save.return_value = MagicMock()
        result = self.service.create_user("test@example.com", "12345678")
        assert result is not None

    # 异常路径：repo 抛出异常
    def test_create_user_repo_failure_propagates_exception(self):
        self.mock_repo.save.side_effect = DatabaseException("DB down")
        with pytest.raises(DatabaseException):
            self.service.create_user("test@example.com", "securepass123")
```

**pytest 配置（conftest.py）**：
```python
import pytest
from sqlalchemy import create_engine
from app.core.database import Base

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
        session.rollback()
```

---

## Java / Kotlin（JUnit5 + Mockito）

```kotlin
// 被测 Service
@Service
class OrderService(
    private val orderRepository: OrderRepository,
    private val paymentClient: PaymentClient,
) {
    fun placeOrder(userId: Long, items: List<OrderItem>): Order {
        if (items.isEmpty()) throw IllegalArgumentException("Order must have items")
        val order = orderRepository.save(Order(userId = userId, items = items))
        paymentClient.charge(order.id, order.totalAmount)
        return order
    }
}
```

```kotlin
// 生成的测试
@ExtendWith(MockitoExtension::class)
class OrderServiceTest {

    @Mock lateinit var orderRepository: OrderRepository
    @Mock lateinit var paymentClient: PaymentClient
    @InjectMocks lateinit var orderService: OrderService

    private val userId = 1L
    private val items = listOf(OrderItem(productId = 1, quantity = 2, price = 100.0))

    @Test
    fun `placeOrder with valid items saves order and charges payment`() {
        val savedOrder = Order(id = 1L, userId = userId, items = items, totalAmount = 200.0)
        whenever(orderRepository.save(any())).thenReturn(savedOrder)

        val result = orderService.placeOrder(userId, items)

        assertThat(result.id).isEqualTo(1L)
        verify(orderRepository).save(any())
        verify(paymentClient).charge(savedOrder.id, savedOrder.totalAmount)
    }

    @Test
    fun `placeOrder with empty items throws IllegalArgumentException`() {
        assertThrows<IllegalArgumentException> {
            orderService.placeOrder(userId, emptyList())
        }.also {
            assertThat(it.message).contains("items")
        }
    }

    @Test
    fun `placeOrder when payment fails propagates exception`() {
        whenever(orderRepository.save(any())).thenReturn(Order(id = 1L, userId = userId, items = items))
        whenever(paymentClient.charge(any(), any())).thenThrow(PaymentException("Card declined"))

        assertThrows<PaymentException> {
            orderService.placeOrder(userId, items)
        }
    }

    @ParameterizedTest
    @ValueSource(ints = [0, -1, -100])
    fun `placeOrder with non-positive quantity throws exception`(quantity: Int) {
        val invalidItems = listOf(OrderItem(productId = 1, quantity = quantity, price = 100.0))
        assertThrows<IllegalArgumentException> {
            orderService.placeOrder(userId, invalidItems)
        }
    }
}
```

---

## TypeScript（Jest / Vitest）

```typescript
// 被测函数
export async function getUserById(
  id: string,
  userRepo: UserRepository,
): Promise<UserDto> {
  if (!id) throw new Error('User ID is required')
  const user = await userRepo.findById(id)
  if (!user) throw new NotFoundError(`User ${id} not found`)
  return mapToDto(user)
}
```

```typescript
// 生成的测试
import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('getUserById', () => {
  const mockRepo = {
    findById: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns user DTO when user exists', async () => {
    const mockUser = { id: '1', email: 'test@example.com', name: 'Test' }
    mockRepo.findById.mockResolvedValue(mockUser)

    const result = await getUserById('1', mockRepo)

    expect(result).toEqual({ id: '1', email: 'test@example.com', name: 'Test' })
    expect(mockRepo.findById).toHaveBeenCalledWith('1')
  })

  it('throws Error when id is empty string', async () => {
    await expect(getUserById('', mockRepo))
      .rejects.toThrow('User ID is required')
    expect(mockRepo.findById).not.toHaveBeenCalled()
  })

  it('throws NotFoundError when user does not exist', async () => {
    mockRepo.findById.mockResolvedValue(null)

    await expect(getUserById('999', mockRepo))
      .rejects.toBeInstanceOf(NotFoundError)
  })

  it('propagates repository errors', async () => {
    mockRepo.findById.mockRejectedValue(new Error('DB connection failed'))

    await expect(getUserById('1', mockRepo))
      .rejects.toThrow('DB connection failed')
  })
})
```

---

## 生成测试时的原则

1. 先理解被测代码的**职责边界**，不测实现细节，测行为
2. Mock 所有**外部依赖**（数据库、HTTP 调用、消息队列）
3. 每个测试只断言**一件事**，失败时立即知道哪里出了问题
4. 测试代码也是代码，需要可读性，禁止魔法数字
5. 需要验证真实数据库行为时，使用 `integration-test-gen` 而不是内存数据库替代
