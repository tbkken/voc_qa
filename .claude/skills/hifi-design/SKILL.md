---
name: hifi-design
description: 直接输出可点击交互的单一 HTML 高保真原型文件，内含 Vue3 + Element Plus（CDN 引入），浏览器双击即可运行，无需任何环境配置。接口数据缺失时自动根据页面语义伪造完整 Mock 数据。当用户说"帮我做高保真"、"输出可交互原型"、"生成可以点击的页面"、"高保真交互稿"、"把低保真变成可以演示的"时触发。
---

# Hifi Design

输出单一 HTML 文件，浏览器双击直接运行，无需任何安装或配置。

## 核心原则

1. **单文件输出**：所有内容（HTML + CSS + JS + Mock 数据）在一个 `.html` 文件里
2. **CDN 引入**：Vue3 + Element Plus + Element Icons 全部走 CDN，无需 npm
3. **双击即开**：生成后直接用浏览器打开，零配置
4. **Mock 数据内置**：根据页面语义自动伪造，涵盖所有状态和边界数据
5. **强制完整状态**：空状态 / 加载态 / 报错态 / 表单校验态 缺一不可

---

## 固定 HTML 壳子结构

每次生成必须使用以下结构，CDN 地址固定不变：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[页面名称] · 高保真原型</title>
  <!-- Element Plus 样式 -->
  <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f7fa; }
    /* 页面级样式写在这里 */
  </style>
</head>
<body>
  <div id="app"></div>

  <!-- Vue3 -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
  <!-- Element Plus 组件 -->
  <script src="https://unpkg.com/element-plus/dist/index.full.min.js"></script>
  <!-- Element Plus 图标 -->
  <script src="https://unpkg.com/@element-plus/icons-vue/dist/index.iife.min.js"></script>

  <script>
    const { createApp, ref, reactive, computed, onMounted, watch } = Vue
    const { ElMessage, ElMessageBox } = ElementPlus

    // ── Mock 数据层 ──────────────────────────────────────────
    // [在此定义 Mock 数据和模拟接口函数]

    // ── 页面组件 ─────────────────────────────────────────────
    const App = {
      template: `[页面模板]`,
      setup() {
        // [响应式状态 + 业务逻辑]
        return { /* 暴露给模板的变量和方法 */ }
      }
    }

    // ── 挂载 ─────────────────────────────────────────────────
    const app = createApp(App)
    app.use(ElementPlus, { locale: ElementPlus.lang.zhCn })
    // 注册图标
    for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
      app.component(name, comp)
    }
    app.mount('#app')
  </script>
</body>
</html>
```

---

## Mock 数据伪造规则

没有接口文档时，按以下规则自动推断并生成：

| 字段类型 | 伪造规则 |
|----------|----------|
| ID | 带业务前缀：`ORD-20240315-001`，不用纯数字 |
| 名称 | 真实业务词汇，必须包含一条超长文本（验证截断） |
| 金额 | 包含整数、小数、大额（9999.99）各一条 |
| 状态 | 所有枚举值各至少 1 条 |
| 时间 | `YYYY-MM-DD HH:mm`，最近 30 天内 |
| 布尔 | true 和 false 各至少 1 条 |
| 列表 | 至少 8 条，足够展示分页效果 |

Mock 接口函数统一模拟 **600ms 网络延迟**，体现真实加载效果。

---

## 完整示例：订单列表页

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>订单管理 · 高保真原型</title>
  <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, 'PingFang SC', sans-serif; background: #f5f7fa; }
    .layout { display: flex; height: 100vh; }
    .aside { width: 220px; background: #001529; flex-shrink: 0; }
    .logo { height: 56px; display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: 15px; font-weight: 600; border-bottom: 1px solid #ffffff1a; }
    .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    .header { height: 56px; background: #fff; border-bottom: 1px solid #f0f0f0;
              display: flex; align-items: center; padding: 0 24px; flex-shrink: 0; }
    .header-tip { font-size: 12px; color: #999; }
    .content { flex: 1; overflow: auto; }
    .page { padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .page-title { font-size: 20px; font-weight: 600; color: #1d2129; }
    .filter-card { margin-bottom: 16px; }
    .amount { font-weight: 600; color: #e6a23c; }
    .pagination-wrapper { display: flex; justify-content: flex-end; padding: 16px 24px; }
  </style>
</head>
<body>
<div id="app"></div>

<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
<script src="https://unpkg.com/element-plus/dist/index.full.min.js"></script>
<script src="https://unpkg.com/@element-plus/icons-vue/dist/index.iife.min.js"></script>

<script>
const { createApp, ref, reactive, computed, onMounted } = Vue
const { ElMessage, ElMessageBox } = ElementPlus

// ══════════════════════════════════════════════════════════════
// Mock 数据层（接口就绪后替换此区块）
// ══════════════════════════════════════════════════════════════
const MOCK_ORDERS = [
  { id: 'ORD-20240315-001', summary: '春季新款连衣裙 × 2，男士休闲裤 × 1', amount: 598.00, status: 'PENDING_PAYMENT', createdAt: '2024-03-15 10:23' },
  { id: 'ORD-20240314-008', summary: '超长商品名称用于验证文字省略效果在不同分辨率屏幕下均能正确截断并显示省略号 × 3', amount: 9999.99, status: 'COMPLETED', createdAt: '2024-03-14 16:05' },
  { id: 'ORD-20240314-006', summary: '无线蓝牙耳机 Pro Max × 1', amount: 299.00, status: 'CANCELLED', createdAt: '2024-03-14 09:30' },
  { id: 'ORD-20240313-015', summary: '有机棉T恤 × 5，休闲短裤 × 2', amount: 456.50, status: 'COMPLETED', createdAt: '2024-03-13 14:22' },
  { id: 'ORD-20240313-009', summary: '智能手表运动版 × 1', amount: 1299.00, status: 'PENDING_PAYMENT', createdAt: '2024-03-13 11:08' },
  { id: 'ORD-20240312-022', summary: '护肤套装礼盒 × 2', amount: 688.00, status: 'COMPLETED', createdAt: '2024-03-12 20:15' },
  { id: 'ORD-20240311-003', summary: '儿童玩具积木套装豪华版 × 1', amount: 199.00, status: 'CANCELLED', createdAt: '2024-03-11 08:44' },
  { id: 'ORD-20240310-017', summary: '手冲咖啡精选礼包 × 3，手冲壶 × 1', amount: 348.00, status: 'COMPLETED', createdAt: '2024-03-10 19:30' },
]

const mockFetch = ({ page, pageSize, status, keyword }) =>
  new Promise(resolve => setTimeout(() => {
    let data = MOCK_ORDERS
      .filter(d => !status  || d.status === status)
      .filter(d => !keyword || d.id.includes(keyword) || d.summary.includes(keyword))
    resolve({ items: data.slice((page - 1) * pageSize, page * pageSize), total: data.length })
  }, 600))

const mockCancel = () => new Promise(r => setTimeout(r, 800))

// ══════════════════════════════════════════════════════════════
// 枚举映射
// ══════════════════════════════════════════════════════════════
const STATUS_LABEL = { PENDING_PAYMENT: '待支付', COMPLETED: '已完成', CANCELLED: '已取消' }
const STATUS_TYPE  = { PENDING_PAYMENT: 'warning', COMPLETED: 'success', CANCELLED: 'info' }

// ══════════════════════════════════════════════════════════════
// 页面组件
// ══════════════════════════════════════════════════════════════
const OrderList = {
  template: `
    <div class="page">
      <!-- 页头 -->
      <div class="page-header">
        <span class="page-title">订单管理</span>
        <el-button type="primary" :icon="Plus" @click="msg('跳转新建订单页')">新建订单</el-button>
      </div>

      <!-- 筛选栏 -->
      <el-card class="filter-card" shadow="never">
        <el-form :model="filter" inline>
          <el-form-item label="状态">
            <el-select v-model="filter.status" placeholder="全部" clearable style="width:130px" @change="onFilter">
              <el-option label="待支付" value="PENDING_PAYMENT" />
              <el-option label="已完成" value="COMPLETED" />
              <el-option label="已取消" value="CANCELLED" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input v-model="filter.keyword" placeholder="搜索订单号/商品名"
              :prefix-icon="Search" clearable style="width:240px" @input="onSearch" />
          </el-form-item>
          <el-form-item>
            <el-button @click="onReset">重置</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 表格 -->
      <el-card shadow="never">
        <el-table v-loading="loading" :data="rows" stripe style="width:100%">
          <el-table-column prop="id" label="订单号" width="190" />
          <el-table-column prop="summary" label="商品摘要" min-width="200" show-overflow-tooltip />
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              <span class="amount">¥ {{ row.amount.toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="STATUS_TYPE[row.status]" size="small">{{ STATUS_LABEL[row.status] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="创建时间" width="160" />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="msg('查看订单：' + row.id)">详情</el-button>
              <el-button v-if="row.status === 'PENDING_PAYMENT'"
                link type="danger" size="small" @click="openCancel(row)">取消</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="filter.keyword ? '未找到相关订单，换个关键词试试' : '暂无订单数据'">
              <el-button v-if="!filter.keyword" type="primary" @click="msg('跳转新建订单页')">立即创建</el-button>
            </el-empty>
          </template>
        </el-table>

        <!-- 分页 -->
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="page" v-model:page-size="pageSize"
            :total="total" :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @change="fetchList" />
        </div>
      </el-card>

      <!-- 取消确认弹窗 -->
      <el-dialog v-model="cancelVisible" title="确认取消订单" width="420px">
        <p style="color:#606266">取消后订单将无法恢复，已扣库存将自动归还。</p>
        <template #footer>
          <el-button @click="cancelVisible = false">再想想</el-button>
          <el-button type="danger" :loading="cancelling" @click="confirmCancel">确认取消</el-button>
        </template>
      </el-dialog>
    </div>
  `,
  setup() {
    const loading = ref(false)
    const rows    = ref([])
    const total   = ref(0)
    const page    = ref(1)
    const pageSize = ref(10)
    const filter  = reactive({ status: '', keyword: '' })
    const cancelVisible = ref(false)
    const cancelling    = ref(false)
    let cancelTarget    = null
    let searchTimer     = null

    const fetchList = async () => {
      loading.value = true
      try {
        const res = await mockFetch({ page: page.value, pageSize: pageSize.value, ...filter })
        rows.value  = res.items
        total.value = res.total
      } catch { ElMessage.error('加载失败，请稍后重试') }
      finally { loading.value = false }
    }

    const onFilter = () => { page.value = 1; fetchList() }
    const onSearch = () => { clearTimeout(searchTimer); searchTimer = setTimeout(onFilter, 300) }
    const onReset  = () => { Object.assign(filter, { status: '', keyword: '' }); onFilter() }

    const openCancel = (row) => { cancelTarget = row; cancelVisible.value = true }
    const confirmCancel = async () => {
      cancelling.value = true
      try {
        await mockCancel()
        const item = rows.value.find(d => d.id === cancelTarget.id)
        if (item) item.status = 'CANCELLED'
        cancelVisible.value = false
        ElMessage.success('订单已取消')
      } catch { ElMessage.error('操作失败，请重试') }
      finally { cancelling.value = false }
    }

    const msg = (text) => ElMessage.info(text + '（原型演示）')

    onMounted(fetchList)

    return {
      loading, rows, total, page, pageSize, filter,
      cancelVisible, cancelling,
      STATUS_LABEL, STATUS_TYPE,
      Plus: ElementPlusIconsVue.Plus,
      Search: ElementPlusIconsVue.Search,
      openCancel, confirmCancel, fetchList, onFilter, onSearch, onReset, msg,
    }
  }
}

// ══════════════════════════════════════════════════════════════
// 根应用（带侧边导航壳子）
// ══════════════════════════════════════════════════════════════
const App = {
  components: { OrderList },
  template: `
    <div class="layout">
      <!-- 侧边栏 -->
      <div class="aside">
        <div class="logo">🎨 高保真原型</div>
        <el-menu background-color="#001529" text-color="#ffffffa6"
          active-text-color="#ffffff" default-active="order-list">
          <el-menu-item index="order-list" @click="current = 'order-list'">
            <el-icon><List /></el-icon>订单管理
          </el-menu-item>
          <el-menu-item index="order-create" @click="current = 'order-create'">
            <el-icon><Plus /></el-icon>新建订单
          </el-menu-item>
        </el-menu>
      </div>
      <!-- 主区域 -->
      <div class="main">
        <div class="header">
          <span class="header-tip">🧪 原型演示模式 · Mock 数据 · 接口未连接</span>
        </div>
        <div class="content">
          <order-list v-if="current === 'order-list'" />
          <div v-else style="padding:40px;text-align:center">
            <el-empty description="该页面原型开发中" />
          </div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const current = ref('order-list')
    return { current }
  }
}

// ══════════════════════════════════════════════════════════════
// 挂载
// ══════════════════════════════════════════════════════════════
const app = createApp(App)
app.use(ElementPlus, { locale: ElementPlus.lang.zhCn })
for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, comp)
}
app.mount('#app')
</script>
</body>
</html>
```

---

## 多页面处理方式

所有页面**在同一个 HTML 文件里**，通过 `current` 变量切换显示：

```javascript
// 侧边菜单切换 current 值
// 主内容区用 v-if 判断显示哪个组件
const current = ref('order-list')

// template 里
// <order-list    v-if="current === 'order-list'" />
// <order-form    v-if="current === 'order-form'" />
// <order-detail  v-if="current === 'order-detail'" />
```

每个页面是一个独立的 `setup()` 对象，注册为局部组件，互不干扰。

---

## 强制状态覆盖清单

生成 HTML 后，确认代码中包含：

- [ ] **空状态**：`<el-empty>` 含文案，搜索空态与默认空态文案不同
- [ ] **加载态**：表格 `v-loading`，按钮操作 `:loading`
- [ ] **报错态**：`catch` 块内 `ElMessage.error()`
- [ ] **表单校验**：`:rules` 定义，`formRef.validate()` 提交前执行
- [ ] **按钮防重**：提交中 `:loading="submitting"` 阻止重复点击
- [ ] **危险操作二次确认**：`el-dialog` 确认弹窗
- [ ] **Mock 数据**：含超长文本、含金额极值、覆盖所有枚举状态

---

## 运行方式

生成 HTML 文件后，**浏览器直接双击打开**即可，无需任何安装或配置。

```
OrderList.html   ← 双击，浏览器打开，即可点击交互
```

如需在多设备演示：
```bash
# 用 Python 起一个简单的本地服务（任何机器都有 Python）
python3 -m http.server 8080
# 访问 http://localhost:8080/OrderList.html
```
