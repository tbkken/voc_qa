---
name: e2e-test-gen
description: 基于用户故事和业务流程生成端到端测试脚本，覆盖完整的用户操作路径。当用户说"写 E2E 测试"、"集成测试"、"接口联调测试"、"写 Playwright 测试"、"测试完整流程"、"冒烟测试"时触发。支持前端 Playwright 和后端 API 集成测试。
---

# E2E Test Gen

生成覆盖完整业务流程的端到端测试。

## 两种 E2E 测试类型

| 类型 | 工具 | 场景 |
|------|------|------|
| **前端 E2E** | Playwright | 测试用户界面操作流程 |
| **后端 API E2E** | pytest + httpx / RestAssured | 测试完整 API 调用链路 |

---

## 前端 E2E（Playwright + TypeScript）

### 项目配置

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html'], ['list']],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 5'] } },
  ],
})
```

### Page Object 模式（推荐结构）

```typescript
// e2e/pages/LoginPage.ts
import { Page, Locator } from '@playwright/test'

export class LoginPage {
  readonly emailInput: Locator
  readonly passwordInput: Locator
  readonly submitButton: Locator
  readonly errorMessage: Locator

  constructor(private page: Page) {
    this.emailInput = page.getByLabel('邮箱')
    this.passwordInput = page.getByLabel('密码')
    this.submitButton = page.getByRole('button', { name: '登录' })
    this.errorMessage = page.getByTestId('error-message')
  }

  async goto() {
    await this.page.goto('/login')
  }

  async login(email: string, password: string) {
    await this.emailInput.fill(email)
    await this.passwordInput.fill(password)
    await this.submitButton.click()
  }
}

// e2e/pages/OrderPage.ts
export class OrderPage {
  constructor(private page: Page) {}

  async placeOrder(productId: string, quantity: number) {
    await this.page.goto(`/products/${productId}`)
    await this.page.getByLabel('数量').fill(String(quantity))
    await this.page.getByRole('button', { name: '加入购物车' }).click()
    await this.page.getByRole('link', { name: '去结算' }).click()
    await this.page.getByRole('button', { name: '提交订单' }).click()
  }
}
```

### 完整业务流程测试

```typescript
// e2e/tests/checkout.spec.ts
import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { OrderPage } from '../pages/OrderPage'

test.describe('下单完整流程', () => {
  // 测试前登录，避免每个测试都重复登录
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('test@example.com', 'Test1234!')
    await expect(page).toHaveURL('/dashboard')
  })

  test('用户可以成功下单并看到订单确认页', async ({ page }) => {
    const orderPage = new OrderPage(page)
    await orderPage.placeOrder('product-001', 2)

    // 验证跳转到订单确认页
    await expect(page).toHaveURL(/\/orders\/\d+\/confirm/)
    await expect(page.getByText('订单提交成功')).toBeVisible()
    await expect(page.getByTestId('order-total')).toContainText('¥')
  })

  test('购物车为空时无法结算', async ({ page }) => {
    await page.goto('/cart')
    await expect(page.getByRole('button', { name: '去结算' })).toBeDisabled()
    await expect(page.getByText('购物车是空的')).toBeVisible()
  })

  test('库存不足时提示用户', async ({ page }) => {
    const orderPage = new OrderPage(page)
    // out-of-stock-product 是测试数据中库存为 0 的商品
    await page.goto('/products/out-of-stock-product')
    await expect(page.getByRole('button', { name: '加入购物车' })).toBeDisabled()
    await expect(page.getByText('库存不足')).toBeVisible()
  })
})

test.describe('登录功能', () => {
  test('邮箱或密码错误时显示错误信息', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('wrong@example.com', 'wrongpassword')

    await expect(loginPage.errorMessage).toContainText('邮箱或密码不正确')
    await expect(page).toHaveURL('/login')
  })

  test('未登录用户访问受保护页面跳转登录', async ({ page }) => {
    await page.goto('/orders')
    await expect(page).toHaveURL(/\/login\?redirect=/)
  })
})
```

### 测试数据与 Fixture 管理

```typescript
// e2e/fixtures/testData.ts
export const TEST_USERS = {
  standard: { email: 'test@example.com', password: 'Test1234!' },
  admin: { email: 'admin@example.com', password: 'Admin1234!' },
}

export const TEST_PRODUCTS = {
  inStock: 'product-001',
  outOfStock: 'out-of-stock-product',
}

// 通过 API 创建测试数据的 fixture
// e2e/fixtures/index.ts
import { test as base } from '@playwright/test'

export const test = base.extend({
  // 每个测试前创建独立订单数据，避免测试间互相污染
  testOrder: async ({ request }, use) => {
    const response = await request.post('/api/v1/test/orders', {
      data: { productId: 'product-001', quantity: 1 }
    })
    const order = await response.json()
    await use(order.data)
    // 测试后清理
    await request.delete(`/api/v1/test/orders/${order.data.id}`)
  },
})
```

---

## 后端 API 集成测试（Python + pytest + httpx）

```python
# tests/integration/test_user_api.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

@pytest.fixture
async def auth_headers(client):
    """获取登录 token"""
    response = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "Test1234!"
    })
    token = response.json()["data"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}

class TestUserRegistrationFlow:
    async def test_register_then_login_success(self, client):
        """注册后可以正常登录"""
        email = "newuser_integration@example.com"

        # 1. 注册
        reg_resp = await client.post("/api/v1/users", json={
            "email": email, "password": "Test1234!", "name": "测试用户"
        })
        assert reg_resp.status_code == 201
        user_id = reg_resp.json()["data"]["id"]

        # 2. 登录
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": email, "password": "Test1234!"
        })
        assert login_resp.status_code == 200
        assert "accessToken" in login_resp.json()["data"]

    async def test_duplicate_email_returns_409(self, client):
        """重复邮箱注册返回 409"""
        payload = {"email": "dup@example.com", "password": "Test1234!"}
        await client.post("/api/v1/users", json=payload)

        resp = await client.post("/api/v1/users", json=payload)
        assert resp.status_code == 409
        assert resp.json()["code"] == 40901

class TestOrderFlow:
    async def test_place_order_reduces_inventory(self, client, auth_headers):
        """下单后库存减少"""
        # 查询下单前库存
        before = await client.get("/api/v1/products/product-001")
        stock_before = before.json()["data"]["stock"]

        # 下单
        order_resp = await client.post("/api/v1/orders", json={
            "items": [{"productId": "product-001", "quantity": 1}]
        }, headers=auth_headers)
        assert order_resp.status_code == 201

        # 验证库存减少
        after = await client.get("/api/v1/products/product-001")
        assert after.json()["data"]["stock"] == stock_before - 1
```

---

## E2E 测试原则

1. **测行为，不测实现**：只关心用户可见的结果
2. **测试数据隔离**：每个测试用独立数据，测后清理，避免相互污染
3. **Page Object 模式**：UI 选择器集中管理，一改全改
4. **优先用语义选择器**：`getByRole`、`getByLabel` 优于 CSS 选择器，更抗 UI 变化
5. **失败截图**：CI 中自动截图，便于排查
6. **E2E 不替代单元测试**：E2E 测核心流程（20%），单元测试测细节（80%）
