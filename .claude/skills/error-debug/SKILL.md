---
name: error-debug
description: 根据报错信息、日志、堆栈追踪定位根因并给出修复方案。当用户贴出报错、说"报错了"、"跑不起来"、"这个异常怎么解决"、"帮我看看这个 bug"时立即触发。支持 Python / Java / Kotlin / TypeScript 运行时错误、Spring Boot 启动失败、Docker 容器异常、Jenkins 构建失败等场景。
---

# Error Debug

系统化排查错误，快速定位根因。

## 诊断流程

```
收到报错
  │
  ▼
1. 识别错误类型（运行时 / 编译 / 配置 / 环境）
  │
  ▼
2. 定位错误源头（读堆栈，找第一个"自己代码"的帧）
  │
  ▼
3. 理解上下文（发生在什么操作、什么环境）
  │
  ▼
4. 提出假设 → 验证 → 修复
```

---

## Python 常见错误

### ImportError / ModuleNotFoundError
```
原因：依赖未安装 或 PYTHONPATH 未包含模块路径
修复：
  pip install <package>           # 缺依赖
  pip install -e .                # 本地包未安装为 editable
  export PYTHONPATH=$PYTHONPATH:src  # 路径问题
```

### AttributeError / TypeError
```
优先检查：变量是否为 None？类型是否符合预期？
调试方式：在报错行上方加 print(type(x), x) 确认类型
```

### 数据库相关
```
sqlalchemy.exc.OperationalError: 连接失败
  → 检查数据库是否启动、连接串是否正确、网络是否通

sqlalchemy.exc.IntegrityError: 违反约束
  → 检查唯一约束、外键约束、非空约束
```

---

## Java / Kotlin 常见错误

### NullPointerException（Java）
```
读堆栈：找到第一个自己包名的行
常见原因：
  - Spring Bean 未注入（@Autowired 漏掉，或 Bean 未被扫描）
  - 数据库查询返回 null 未处理
  - 配置项未配置但直接使用
```

### Spring Boot 启动失败
```
关键日志位置：APPLICATION FAILED TO START 之后的 Description 和 Action

常见原因：
  - 端口占用：Address already in use → lsof -i :8080
  - Bean 循环依赖：A → B → A → 用 @Lazy 或重构
  - 配置项缺失：Could not resolve placeholder → 检查 application.yml
  - 数据库连接失败 → 检查 datasource 配置
```

### ClassCastException
```
原因：泛型擦除、反序列化类型不匹配
修复：检查泛型声明，确认反序列化目标类型
```

---

## TypeScript / JavaScript 常见错误

### Cannot read properties of undefined/null
```javascript
// 调试：确认数据链路
console.log('data:', data)  // 是否拿到了数据？
console.log('data.user:', data?.user)  // 中间层是否存在？

// 修复：可选链 + 默认值
const name = data?.user?.name ?? '未知'
```

### Type '...' is not assignable to type '...'
```
读错误信息：TypeScript 会指出期望类型和实际类型
常见原因：
  - API 返回类型与接口定义不一致 → 更新类型定义
  - null/undefined 未处理 → 加类型守卫
  - 类型断言滥用 → 用类型守卫代替 as
```

### 异步问题
```javascript
// 症状：拿到 Promise 而非数据，或异步结果为 undefined
// 原因：忘记 await，或在非 async 函数里用 await

// 检查：
async function fetchData() {
  const result = await api.get('/xxx')  // 必须 await
  return result.data
}
```

---

## Docker 常见错误

```bash
# 容器启动失败
docker logs <container_id>  # 查看启动日志

# 常见原因
Exit code 1：应用报错退出 → 看日志
Exit code 137：OOM → 增加内存限制
port already in use → docker ps 查看端口占用，停止冲突容器

# 镜像构建失败
docker build --no-cache .   # 清除缓存重试
# 读 RUN 步骤的错误输出，通常是包安装失败或文件不存在
```

---

## Jenkins 构建失败

```
排查顺序：
1. 点击失败的 Stage，查看 Console Output
2. 找到第一个 ERROR 或 FAILED 关键字
3. 常见原因：
   - 测试失败：看具体测试用例输出
   - 编译失败：看编译器错误信息
   - 依赖拉不到：网络问题或私有仓库认证失败
   - 环境变量未配置：在 Jenkins 节点上检查 env
```

---

## 输出格式

分析完成后，按以下结构回复：

```
## 根因
[一句话说清楚是什么问题]

## 原因分析
[为什么会出现这个问题，附关键证据]

## 修复方案
[具体代码或命令]

## 预防建议（可选）
[如何避免同类问题再次出现]
```
