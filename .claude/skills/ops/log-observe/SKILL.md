---
name: log-observe
description: 分析应用日志、定位线上问题根因。当用户说"看一下日志"、"日志里有什么错误"、"线上报错了"、"分析这段日志"、"帮我看看这个异常"、"日志怎么查"时触发。支持 Docker 日志、Spring Boot 日志、Python 应用日志分析。
---

# Log Observe

快速从日志中定位问题根因。

## 日志采集命令（Docker 环境）

```bash
# 实时跟踪
docker logs -f <container_name>

# 只看最近 100 行
docker logs --tail=100 <container_name>

# 最近 30 分钟
docker logs --since 30m backend

# 过滤错误
docker logs --since 1h backend 2>&1 | grep -E "ERROR|Exception|WARN"

# 按时间段
docker logs --since "2024-03-15T10:00:00" --until "2024-03-15T10:30:00" backend

# 多容器
docker-compose logs -f --tail=50 backend frontend
```

---

## 读堆栈的正确方式

### Spring Boot

```
2024-03-15 10:23:45 ERROR c.e.service.OrderService : 创建订单失败
com.example.exception.PaymentException: 支付网关超时
    at com.example.service.PaymentService.charge(PaymentService.kt:67)   ← 自己代码第一帧
    at com.example.service.OrderService.placeOrder(OrderService.kt:45)
Caused by: java.net.SocketTimeoutException: Read timed out               ← 根本原因在这里
```

1. 先看最后一个 `Caused by`，这是根本原因
2. 找第一个属于自己包名的行，这是问题位置
3. 忽略框架的行（Spring、Tomcat）

### Python

```
File "app/services/user.py", line 87, in create_user    ← 自己代码
    db.commit()
sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: users.email    ← 根本原因
```

---

## 常见错误速查

| 日志关键字 | 含义 | 排查方向 |
|-----------|------|----------|
| `Connection refused` | 数据库/Redis 连不上 | 检查容器是否运行、连接串 |
| `Too many connections` | 连接池耗尽 | 检查连接泄漏，调大连接池 |
| `UNIQUE constraint failed` | 唯一键冲突 | 检查并发写入逻辑 |
| `Lock wait timeout` | 数据库锁超时 | 查找长事务、死锁 |
| `OutOfMemoryError` | JVM 内存溢出 | 分析堆，检查内存泄漏 |
| `SocketTimeoutException` | 外部调用超时 | 检查被调用方，考虑熔断 |
| `Connection pool exhausted` | 连接池用完 | 检查连接未释放 |

---

## 快速统计命令

```bash
# 1 小时内 ERROR 数量
docker logs --since 1h backend 2>&1 | grep -c "ERROR"

# 各类异常频率排行
docker logs --since 1h backend 2>&1 | grep "Exception" \
  | grep -oP '\w+Exception' | sort | uniq -c | sort -rn | head -10

# 查找某接口相关日志
docker logs --since 30m backend 2>&1 | grep "placeOrder\|createOrder"

# 查找某用户相关日志
docker logs --since 1h backend 2>&1 | grep "userId=12345"
```

---

## 输出格式

```
## 日志分析结果

**根本原因**：[一句话]

**关键证据**：
[最关键的几行日志]

**影响范围**：[影响功能、开始时间]

**建议处理步骤**：
1. [立即行动]
2. [排查步骤]
3. [修复方向]
```
