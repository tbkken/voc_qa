---
name: test-coverage
description: 分析测试覆盖率报告，找出未覆盖的关键路径并补充测试。当用户说"覆盖率太低"、"哪些代码没有测试"、"分析覆盖率报告"、"提高测试覆盖率"、"coverage 报告怎么看"时触发。
---

# Test Coverage

分析覆盖率报告，找出关键未覆盖路径，补充高价值测试。

## 覆盖率目标

| 层级 | 目标 | 说明 |
|------|------|------|
| 核心业务逻辑（Service 层） | ≥ 80% | 最重要，必须达到 |
| 工具函数 / 公共组件 | ≥ 90% | 被复用的代码更需要覆盖 |
| Controller / API 层 | ≥ 70% | 集成测试补充 |
| 配置类 / 常量 | 不强求 | 意义不大 |

> **覆盖率不是目标**，找到真正的风险点才是目标。80% 的平均覆盖率不代表关键路径被覆盖。

---

## 各语言覆盖率工具

### Python（pytest-cov）

```bash
# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html --cov-report=term-missing

# 查看未覆盖的具体行（term-missing 输出示例）
# Name                      Stmts   Miss  Cover   Missing
# src/services/user.py         45      8    82%   23-28, 67, 89-92

# 设置覆盖率门槛（低于则失败）
pytest --cov=src --cov-fail-under=80
```

**pyproject.toml 配置**：
```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=html:coverage_report --cov-report=term-missing"

[tool.coverage.run]
omit = [
    "*/migrations/*",
    "*/tests/*",
    "*/config/*",
    "main.py",
]
```

### Java / Kotlin（JaCoCo）

```groovy
// build.gradle.kts
plugins {
    id("jacoco")
}

tasks.jacocoTestReport {
    reports {
        xml.required = true
        html.required = true
    }
    // 排除不需要覆盖的类
    classDirectories.setFrom(
        files(classDirectories.files.map {
            fileTree(it) {
                exclude(
                    "**/dto/**",
                    "**/entity/**",
                    "**/config/**",
                    "**/*Application*",
                )
            }
        })
    )
}

tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                minimum = "0.80".toBigDecimal()
            }
        }
        // Service 层单独要求更高
        rule {
            element = "PACKAGE"
            includes = listOf("**/service/**")
            limit {
                minimum = "0.85".toBigDecimal()
            }
        }
    }
}

// 测试后自动生成报告
tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}
```

```bash
./gradlew test jacocoTestReport
# 报告位置：build/reports/jacoco/test/html/index.html
```

### TypeScript（Vitest / Jest）

```typescript
// vitest.config.ts
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: ['**/*.d.ts', '**/types/**', '**/*.config.*'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
      },
    },
  },
})
```

```bash
npm run test -- --coverage
# 报告位置：coverage/index.html
```

---

## 覆盖率报告分析方法

### 第一步：找出低覆盖的核心文件

优先关注这些文件低覆盖时的风险：
- `*Service*` / `*service*` — 业务逻辑，风险最高
- `*Repository*` / `*repository*` — 数据访问
- 工具函数文件（`utils.py`、`helpers.ts` 等）

### 第二步：识别未覆盖的路径类型

读覆盖率报告时，未覆盖代码通常属于以下几类：

| 类型 | 示例 | 补测优先级 |
|------|------|------------|
| 异常处理分支 | `catch` 块、`if error` 分支 | 🔴 高 |
| 边界条件 | 空列表、零值、最大值 | 🔴 高 |
| 权限校验 | 无权限时的拒绝逻辑 | 🔴 高 |
| 正常路径变体 | 不同输入组合 | 🟡 中 |
| 日志/打印行 | `log.info(...)` | 🟢 低，通常不需要 |

### 第三步：生成补充测试

分析报告后，针对未覆盖的高优先级路径，调用 `unit-test-gen` skill 补充测试。

**示例：从覆盖率报告到补充测试**

```
覆盖率报告显示 src/services/payment.py 第 45-52 行未覆盖：

45:  except PaymentGatewayException as e:
46:      log.error("支付网关异常", exc_info=True)
47:      raise PaymentFailedException(f"支付失败: {e.code}") from e
48:
49:  if response.status == "PENDING":
50:      # 异步支付，等待回调
51:      return PaymentResult.pending(response.transaction_id)
```

→ 需要补充：
1. `PaymentGatewayException` 被抛出时的测试
2. 支付状态为 `PENDING` 时的测试
```

---

## Jenkins 中的覆盖率门禁

在 `Jenkinsfile` 的 Build & Test stage 中添加：

```groovy
stage('Test & Coverage Check') {
    steps {
        // Python
        sh 'pytest --cov=src --cov-fail-under=80'

        // Java
        sh './gradlew test jacocoTestCoverageVerification'
    }
    post {
        always {
            // 发布覆盖率报告到 Jenkins
            publishHTML(target: [
                reportDir: 'coverage_report',  // Python
                reportFiles: 'index.html',
                reportName: 'Coverage Report',
            ])
        }
    }
}
```
