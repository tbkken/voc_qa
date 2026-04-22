---
name: refactor
description: 识别代码坏味道并提供重构方案，保证外部行为不变。当用户说"重构这段代码"、"代码太乱了"、"这个函数太长了"、"有没有更好的写法"、"消除重复代码"、"这里耦合太严重"时触发。支持 Python / Java / Kotlin / TypeScript。
---

# Refactor

识别坏味道，给出具体重构方案，保证行为不变。

## 常见坏味道识别

| 坏味道 | 信号 | 重构手法 |
|--------|------|----------|
| 函数过长 | > 40 行 | 提取函数（Extract Method） |
| 参数过多 | > 4 个参数 | 引入参数对象 |
| 重复代码 | 相似逻辑出现 2+ 次 | 提取公共函数 / 模板方法 |
| 深度嵌套 | if/for 嵌套 > 3 层 | 提前返回 / 卫语句 |
| 上帝类 | 一个类做太多事 | 拆分职责 |
| 魔法数字 | 代码里裸数字 | 提取命名常量 |
| 过长的条件链 | 多个 if-else if | 策略模式 / 映射表 |
| 特性依恋 | A 类频繁访问 B 类的字段 | 移动方法到 B 类 |

---

## 重构模式速查

### 提前返回（消除嵌套）

```kotlin
// 重构前：嵌套地狱
fun processOrder(order: Order?): Result {
    if (order != null) {
        if (order.status == OrderStatus.PENDING) {
            if (order.items.isNotEmpty()) {
                // 真正的业务逻辑在第 4 层缩进
                return doProcess(order)
            } else {
                return Result.error("订单无商品")
            }
        } else {
            return Result.error("订单状态不正确")
        }
    } else {
        return Result.error("订单不存在")
    }
}

// 重构后：卫语句，逻辑一目了然
fun processOrder(order: Order?): Result {
    order ?: return Result.error("订单不存在")
    if (order.status != OrderStatus.PENDING) return Result.error("订单状态不正确")
    if (order.items.isEmpty()) return Result.error("订单无商品")

    return doProcess(order)
}
```

### 提取函数（消除过长函数）

```python
# 重构前：一个函数做了太多事
def handle_checkout(cart_id: int, user_id: int):
    # 校验购物车
    cart = db.query(Cart).filter_by(id=cart_id, user_id=user_id).first()
    if not cart:
        raise NotFoundException("购物车不存在")
    if not cart.items:
        raise ValueError("购物车为空")

    # 计算价格
    subtotal = sum(item.price * item.quantity for item in cart.items)
    discount = 0
    if subtotal > 500:
        discount = subtotal * 0.1
    total = subtotal - discount

    # 创建订单
    order = Order(user_id=user_id, total=total)
    db.add(order)
    for item in cart.items:
        db.add(OrderItem(order=order, product_id=item.product_id, ...))

    # 清空购物车
    db.delete(cart)
    db.commit()
    return order

# 重构后：每个函数只做一件事
def handle_checkout(cart_id: int, user_id: int) -> Order:
    cart = _get_validated_cart(cart_id, user_id)
    total = _calculate_total(cart.items)
    order = _create_order(user_id, cart.items, total)
    _clear_cart(cart)
    db.commit()
    return order

def _get_validated_cart(cart_id: int, user_id: int) -> Cart:
    cart = db.query(Cart).filter_by(id=cart_id, user_id=user_id).first()
    if not cart:
        raise NotFoundException("购物车不存在")
    if not cart.items:
        raise ValueError("购物车为空")
    return cart

def _calculate_total(items: list[CartItem]) -> Decimal:
    subtotal = sum(item.price * item.quantity for item in items)
    discount = subtotal * Decimal("0.1") if subtotal > 500 else Decimal(0)
    return subtotal - discount
```

### 引入参数对象（消除过多参数）

```typescript
// 重构前：5 个参数，调用时很难记顺序
function createReport(
  title: string,
  startDate: Date,
  endDate: Date,
  format: string,
  includeCharts: boolean
): Report { ... }

// 重构后：参数对象
interface ReportOptions {
  title: string
  dateRange: { start: Date; end: Date }
  format: 'pdf' | 'excel' | 'csv'
  includeCharts?: boolean
}

function createReport(options: ReportOptions): Report { ... }
```

### 用映射表替换 if-else 链

```kotlin
// 重构前：随业务增长会无限膨胀
fun getDiscount(memberLevel: String): Double {
    return if (memberLevel == "BRONZE") 0.0
    else if (memberLevel == "SILVER") 0.05
    else if (memberLevel == "GOLD") 0.10
    else if (memberLevel == "PLATINUM") 0.15
    else 0.0
}

// 重构后：映射表，新增等级只需加一行
private val DISCOUNT_BY_LEVEL = mapOf(
    "BRONZE" to 0.0,
    "SILVER" to 0.05,
    "GOLD" to 0.10,
    "PLATINUM" to 0.15,
)

fun getDiscount(memberLevel: String): Double =
    DISCOUNT_BY_LEVEL[memberLevel] ?: 0.0
```

### 策略模式（消除复杂分支）

```python
# 重构前：每加一种支付方式就改这个函数
def process_payment(order: Order, method: str):
    if method == "alipay":
        # 50 行支付宝逻辑
        ...
    elif method == "wechat":
        # 50 行微信支付逻辑
        ...
    elif method == "card":
        # 50 行银行卡逻辑
        ...

# 重构后：策略模式，新增支付方式不改现有代码
from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def process(self, order: Order) -> PaymentResult: ...

class AlipayStrategy(PaymentStrategy):
    def process(self, order: Order) -> PaymentResult:
        # 支付宝逻辑
        ...

class WechatPayStrategy(PaymentStrategy):
    def process(self, order: Order) -> PaymentResult:
        ...

PAYMENT_STRATEGIES: dict[str, PaymentStrategy] = {
    "alipay": AlipayStrategy(),
    "wechat": WechatPayStrategy(),
    "card": CardPayStrategy(),
}

def process_payment(order: Order, method: str) -> PaymentResult:
    strategy = PAYMENT_STRATEGIES.get(method)
    if not strategy:
        raise ValueError(f"不支持的支付方式: {method}")
    return strategy.process(order)
```

---

## 输出格式

```
## 识别到的问题

1. **[坏味道名称]** — [文件名:行号]
   [一句话说明问题]

## 重构方案

### 重构1：[手法名称]

**重构前**：
[原始代码]

**重构后**：
[改善后代码]

**说明**：[为什么这样更好]

## 注意事项
- 重构后需要运行哪些测试验证行为未变
- 是否涉及数据库 schema 变更（需要迁移脚本）
```

## 重构原则

1. **小步前进**：每次只做一种重构，重构后立即运行测试
2. **先有测试再重构**：没有测试的代码先用 `unit-test-gen` 补测试
3. **不改行为**：重构不等于加功能，输入输出保持不变
4. **提交粒度**：每个重构手法单独一个 commit，便于 review 和回滚
