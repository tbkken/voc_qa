---
name: perf-diagnose
description: 诊断和优化应用性能问题，包括接口响应慢、数据库查询慢、内存占用高、CPU 使用率高等。当用户说"接口很慢"、"性能问题"、"响应时间太长"、"数据库慢查询"、"内存泄漏"、"CPU 飙高"时触发。
---

# Perf Diagnose

系统化定位和解决性能瓶颈。

## 性能问题排查流程

```
性能问题
  │
  ├── 接口响应慢 → 先看 DB 查询 → 再看代码逻辑 → 再看外部调用
  ├── CPU 高 → 看线程 / 找热点代码
  ├── 内存高 → 找内存泄漏 / 大对象
  └── 并发量一上来就崩 → 连接池 / 锁竞争
```

---

## 数据库慢查询（最常见瓶颈）

### 找慢查询

```sql
-- PostgreSQL：找执行时间 > 1 秒的查询
SELECT query, mean_exec_time, calls, total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 1000
ORDER BY mean_exec_time DESC
LIMIT 20;

-- 查看当前正在执行的慢查询
SELECT pid, now() - query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle' AND query_start < now() - interval '5 seconds'
ORDER BY duration DESC;
```

### 分析执行计划

```sql
-- EXPLAIN ANALYZE 看实际执行情况
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.*, u.name
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'PENDING'
  AND o.created_at > NOW() - INTERVAL '7 days';
```

**读执行计划的关键点**：
- `Seq Scan` on 大表 = 缺索引，通常是问题所在
- `Rows=10000 Actual Rows=1` = 统计信息过时，执行 `ANALYZE <table>`
- `Nested Loop` + 大表 = N+1 问题，考虑改为 Hash Join

### 常见优化方案

```sql
-- 加索引（最常用）
CREATE INDEX CONCURRENTLY idx_orders_status_created
ON orders(status, created_at DESC)
WHERE status = 'PENDING';  -- 部分索引，只索引常查询的值

-- 避免在索引列上用函数（会导致全表扫描）
-- ❌ WHERE DATE(created_at) = '2024-03-15'
-- ✅ WHERE created_at >= '2024-03-15' AND created_at < '2024-03-16'
```

### JPA / Hibernate N+1 问题

```kotlin
// ❌ N+1：查 100 个订单 = 1次查询 + 100次查用户
val orders = orderRepository.findAll()
orders.forEach { println(it.user.name) }  // 每次访问 user 都触发查询

// ✅ 方案1：fetch join
@Query("SELECT o FROM Order o JOIN FETCH o.user WHERE o.status = :status")
fun findByStatusWithUser(@Param("status") status: OrderStatus): List<Order>

// ✅ 方案2：EntityGraph
@EntityGraph(attributePaths = ["user"])
fun findByStatus(status: OrderStatus): List<Order>

// ✅ 方案3：批量加载（批量大小在配置中设置）
// spring.jpa.properties.hibernate.default_batch_fetch_size=20
```

---

## Redis 缓存优化

```kotlin
// 缓存热点数据（Cache-Aside 模式）
@Service
class ProductService(
    private val productRepository: ProductRepository,
    private val redisTemplate: StringRedisTemplate,
) {
    fun getProduct(id: Long): ProductDto {
        val cacheKey = "product:$id"

        // 先查缓存
        val cached = redisTemplate.opsForValue().get(cacheKey)
        if (cached != null) return objectMapper.readValue(cached)

        // 缓存未命中，查数据库
        val product = productRepository.findById(id)
            .orElseThrow { NotFoundException("商品不存在") }
            .toDto()

        // 写入缓存，TTL 10 分钟
        redisTemplate.opsForValue().set(
            cacheKey,
            objectMapper.writeValueAsString(product),
            Duration.ofMinutes(10)
        )
        return product
    }
}
```

**缓存常见问题**：

| 问题 | 症状 | 解决方案 |
|------|------|----------|
| 缓存穿透 | 查不存在的数据，每次都打到 DB | 缓存空结果（TTL 短一点，如 1 分钟） |
| 缓存雪崩 | 大量缓存同时过期，DB 被打垮 | TTL 加随机抖动（基础 TTL ± 随机秒数） |
| 缓存击穿 | 热点 key 过期瞬间大量请求 | 互斥锁重建缓存，或不设过期时间 |

---

## JVM 内存问题（Java / Kotlin）

```bash
# 查看 JVM 内存使用（在容器内执行）
docker exec -it backend jcmd 1 VM.flags
docker exec -it backend jcmd 1 GC.heap_info

# 触发 GC 日志（添加到启动参数）
-XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:/app/logs/gc.log

# 生成堆 dump（OOM 时自动生成）
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/logs/heap.hprof
```

**常见内存泄漏模式**：
```kotlin
// ❌ 静态集合不断增长
companion object {
    val cache = HashMap<String, Any>()  // 永远不清理
}

// ❌ 事件监听器未注销（Spring Bean 的 destroy 方法需要清理）
@Component
class MyListener : ApplicationListener<SomeEvent> {
    // 如果动态注册，需要在 @PreDestroy 时注销
}

// ✅ 使用有界缓存
val cache = Caffeine.newBuilder()
    .maximumSize(1000)
    .expireAfterWrite(Duration.ofMinutes(10))
    .build<String, Any>()
```

---

## Docker 容器资源监控

```bash
# 实时资源使用
docker stats

# 单容器详情
docker stats backend --no-stream --format \
  "CPU: {{.CPUPerc}}\nMEM: {{.MemUsage}}\nNET: {{.NetIO}}"

# 容器内进程
docker exec -it backend top
docker exec -it backend ps aux

# 检查 OOM（是否因内存被 Kill）
docker inspect backend | grep -A5 "OOMKilled"
dmesg | grep -i "oom\|killed"
```

---

## 性能问题输出格式

```
## 性能诊断报告

**问题现象**：[接口 /api/xxx P99 > 3s]
**影响时段**：[起始时间 ~ 结束时间]

### 根本原因
[具体原因，如：orders 表 status 字段缺少索引，导致全表扫描]

### 证据
[慢查询日志片段 / EXPLAIN 结果]

### 优化方案
**立即可做（不需要发版）**：
- [如：加索引，执行 CREATE INDEX CONCURRENTLY...]

**下次迭代（需要代码变更）**：
- [如：修复 N+1 查询]

### 预期效果
[优化后预计响应时间从 3s 降到 200ms]
```
