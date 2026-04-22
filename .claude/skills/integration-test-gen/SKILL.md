---
name: integration-test-gen
description: 生成连接真实外部组件的集成测试，验证完整调用链，不使用 Mock，不使用内存替代。覆盖 MySQL、Redis、消息队列（RabbitMQ/Kafka）、第三方 HTTP 服务等所有外部依赖。当用户说"帮我写集成测试"、"连真实组件测试"、"端到端单元测试"、"不用 Mock 的测试"、"验证完整调用链"、"测试 Redis 缓存是否正确"、"测试消息是否正确发送"时触发。支持 Java/Kotlin（Spring Boot + Testcontainers）和 Python（pytest）。
---

# Integration Test Gen

连接真实外部组件，验证完整调用链，不用 Mock，不用任何内存替代。

## 核心理念

Mock 测试只验证"函数逻辑"，集成测试验证"组件协作"。以下问题只有集成测试能发现：

| 组件 | Mock 发现不了的问题 |
|------|-------------------|
| MySQL | SQL 写错、JPA 映射错误、事务边界不当、N+1 查询、并发冲突 |
| Redis | Key 设计错误、TTL 设置不合理、缓存穿透、序列化格式不匹配 |
| RabbitMQ/Kafka | 消息序列化错误、路由配置错误、消费者幂等性问题 |
| HTTP 服务 | 超时处理、重试逻辑、错误响应解析、认证流程 |

---

## 统一基础设施：Testcontainers

所有外部组件统一用 Testcontainers 管理，CI 环境零配置，本地也可直接运行。

### 基础配置类（所有集成测试继承）

```kotlin
// src/test/kotlin/com/example/IntegrationTestBase.kt
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@ActiveProfiles("integration-test")
@Transactional
abstract class IntegrationTestBase {

    companion object {
        // ── MySQL ──────────────────────────────────────────
        @Container @JvmStatic
        val mysql = MySQLContainer<Nothing>("mysql:8.0").apply {
            withDatabaseName("testdb")
            withUsername("test")
            withPassword("test")
            withReuse(true)
        }

        // ── Redis ──────────────────────────────────────────
        @Container @JvmStatic
        val redis = GenericContainer<Nothing>("redis:7-alpine").apply {
            withExposedPorts(6379)
            withReuse(true)
        }

        // ── RabbitMQ ───────────────────────────────────────
        @Container @JvmStatic
        val rabbitmq = RabbitMQContainer("rabbitmq:3.12-management").apply {
            withReuse(true)
        }

        // ── WireMock（模拟第三方 HTTP 服务）────────────────
        @Container @JvmStatic
        val wireMock = GenericContainer<Nothing>("wiremock/wiremock:3.3.1").apply {
            withExposedPorts(8080)
            withReuse(true)
        }

        @DynamicPropertySource @JvmStatic
        fun configureProperties(registry: DynamicPropertyRegistry) {
            // MySQL
            registry.add("spring.datasource.url", mysql::getJdbcUrl)
            registry.add("spring.datasource.username", mysql::getUsername)
            registry.add("spring.datasource.password", mysql::getPassword)
            registry.add("spring.jpa.hibernate.ddl-auto") { "create-drop" }
            // Redis
            registry.add("spring.data.redis.host", redis::getHost)
            registry.add("spring.data.redis.port") { redis.getMappedPort(6379) }
            // RabbitMQ
            registry.add("spring.rabbitmq.host", rabbitmq::getHost)
            registry.add("spring.rabbitmq.port", rabbitmq::getAmqpPort)
            registry.add("spring.rabbitmq.username", rabbitmq::getAdminUsername)
            registry.add("spring.rabbitmq.password", rabbitmq::getAdminPassword)
            // 第三方 HTTP 服务
            registry.add("external.payment.base-url") {
                "http://${wireMock.host}:${wireMock.getMappedPort(8080)}"
            }
        }
    }
}
```

Gradle 依赖：

```kotlin
// build.gradle.kts
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter:1.19.0")
    testImplementation("org.testcontainers:mysql:1.19.0")
    testImplementation("org.testcontainers:rabbitmq:1.19.0")
    testImplementation("com.github.tomakehurst:wiremock-standalone:3.3.1")
}
```

---

## MySQL 集成测试

```kotlin
class OrderMysqlIntegrationTest : IntegrationTestBase() {

    @Autowired lateinit var orderRepository: OrderRepository
    @Autowired lateinit var orderService: OrderService
    @Autowired lateinit var testEntityManager: TestEntityManager

    @Test
    fun `创建订单写入正确数据到数据库`() {
        val user = testEntityManager.persistFlushFind(
            User(email = "test@example.com", status = UserStatus.ACTIVE)
        )

        val result = orderService.createOrder(
            CreateOrderRequest(userId = user.id, items = listOf(
                OrderItem(productId = 1L, quantity = 2, price = 99.toBigDecimal())
            ))
        )

        // 直接查库验证，不依赖返回值
        val saved = orderRepository.findById(result.id).orElseThrow()
        assertThat(saved.status).isEqualTo(OrderStatus.PENDING_PAYMENT)
        assertThat(saved.totalAmount).isEqualByComparingTo("198.00")
        assertThat(saved.items).hasSize(1)
    }

    @Test
    fun `库存不足时事务回滚，订单和库存变更都撤销`() {
        val product = testEntityManager.persistFlushFind(Product(stock = 1))

        assertThrows<InsufficientStockException> {
            orderService.createOrder(CreateOrderRequest(
                userId = 1L,
                items = listOf(OrderItem(productId = product.id, quantity = 5, price = 99.toBigDecimal()))
            ))
        }

        val productAfter = testEntityManager.find(Product::class.java, product.id)
        assertThat(productAfter.stock).isEqualTo(1)   // 库存未变
        assertThat(orderRepository.count()).isEqualTo(0) // 无订单写入
    }

    @Test
    fun `并发下单不超卖`() {
        val product = testEntityManager.persistFlushFind(Product(stock = 5))
        val executor = Executors.newFixedThreadPool(10)
        val latch = CountDownLatch(10)
        val successCount = AtomicInteger(0)

        repeat(10) {
            executor.submit {
                try {
                    orderService.createOrder(CreateOrderRequest(
                        userId = 1L,
                        items = listOf(OrderItem(productId = product.id, quantity = 1, price = 99.toBigDecimal()))
                    ))
                    successCount.incrementAndGet()
                } catch (_: InsufficientStockException) {
                } finally { latch.countDown() }
            }
        }
        latch.await(30, TimeUnit.SECONDS)

        assertThat(successCount.get()).isLessThanOrEqualTo(5)
        val finalStock = testEntityManager.find(Product::class.java, product.id).stock
        assertThat(finalStock).isGreaterThanOrEqualTo(0)
    }
}
```

---

## Redis 集成测试

```kotlin
class ProductCacheIntegrationTest : IntegrationTestBase() {

    @Autowired lateinit var productService: ProductService
    @Autowired lateinit var redisTemplate: RedisTemplate<String, Any>
    @Autowired lateinit var productRepository: ProductRepository

    @BeforeEach
    fun cleanRedis() {
        // 每个测试前清空 Redis，避免缓存污染
        redisTemplate.connectionFactory?.connection?.flushDb()
    }

    @Test
    fun `首次查询写入缓存，二次查询命中缓存不访问数据库`() {
        val product = productRepository.save(Product(name = "测试商品", price = 99.toBigDecimal()))

        // 第一次查询：缓存未命中，从数据库读取
        val result1 = productService.getById(product.id)
        assertThat(result1.name).isEqualTo("测试商品")

        // 验证 Redis 中已有缓存
        val cacheKey = "product:${product.id}"
        assertThat(redisTemplate.hasKey(cacheKey)).isTrue()

        // 修改数据库数据（绕过 Service 直接改）
        productRepository.save(product.copy(name = "数据库已修改"))

        // 第二次查询：命中缓存，返回缓存中的旧数据
        val result2 = productService.getById(product.id)
        assertThat(result2.name).isEqualTo("测试商品")  // 仍是缓存值
    }

    @Test
    fun `更新商品后缓存正确失效`() {
        val product = productRepository.save(Product(name = "原始名称", price = 99.toBigDecimal()))
        productService.getById(product.id)  // 触发缓存写入

        val cacheKey = "product:${product.id}"
        assertThat(redisTemplate.hasKey(cacheKey)).isTrue()

        // 更新商品（应该清除缓存）
        productService.update(product.id, UpdateProductRequest(name = "新名称"))

        // 验证缓存已被清除
        assertThat(redisTemplate.hasKey(cacheKey)).isFalse()

        // 再次查询拿到最新数据
        val result = productService.getById(product.id)
        assertThat(result.name).isEqualTo("新名称")
    }

    @Test
    fun `缓存 TTL 设置正确`() {
        val product = productRepository.save(Product(name = "测试商品", price = 99.toBigDecimal()))
        productService.getById(product.id)

        val cacheKey = "product:${product.id}"
        val ttl = redisTemplate.getExpire(cacheKey, TimeUnit.SECONDS)

        // 验证 TTL 在合理范围内（5分钟 ± 5秒）
        assertThat(ttl).isBetween(295L, 300L)
    }

    @Test
    fun `Redis 不可用时降级从数据库读取`() {
        // 停止 Redis 容器模拟故障
        redis.stop()

        try {
            val product = productRepository.save(Product(name = "测试商品", price = 99.toBigDecimal()))
            // 服务应该降级，从数据库读取而不是抛异常
            val result = productService.getById(product.id)
            assertThat(result.name).isEqualTo("测试商品")
        } finally {
            redis.start()  // 恢复
        }
    }
}
```

---

## RabbitMQ / 消息队列集成测试

```kotlin
class OrderEventIntegrationTest : IntegrationTestBase() {

    @Autowired lateinit var orderService: OrderService
    @Autowired lateinit var rabbitTemplate: RabbitTemplate
    @Autowired lateinit var orderEventRepository: OrderEventRepository

    @Test
    fun `创建订单后发送正确的消息到队列`() {
        val latch = CountDownLatch(1)
        var receivedMessage: OrderCreatedEvent? = null

        // 注册临时消费者监听队列
        val container = SimpleMessageListenerContainer(rabbitTemplate.connectionFactory!!).apply {
            setQueueNames("order.created")
            setMessageListener(MessageListenerAdapter { msg ->
                receivedMessage = objectMapper.readValue(msg.body, OrderCreatedEvent::class.java)
                latch.countDown()
            })
            start()
        }

        try {
            val order = orderService.createOrder(CreateOrderRequest(userId = 1L, items = listOf(
                OrderItem(productId = 1L, quantity = 1, price = 99.toBigDecimal())
            )))

            // 等待消息到达（最多 5 秒）
            assertThat(latch.await(5, TimeUnit.SECONDS)).isTrue()

            assertThat(receivedMessage).isNotNull()
            assertThat(receivedMessage!!.orderId).isEqualTo(order.id)
            assertThat(receivedMessage!!.userId).isEqualTo(1L)
            assertThat(receivedMessage!!.totalAmount).isEqualByComparingTo("99.00")
        } finally {
            container.stop()
        }
    }

    @Test
    fun `消费者处理消息具有幂等性，重复消息不重复处理`() {
        val message = OrderCreatedEvent(orderId = 1L, userId = 1L, totalAmount = 99.toBigDecimal())

        // 发送同一条消息两次
        rabbitTemplate.convertAndSend("order.created", message)
        rabbitTemplate.convertAndSend("order.created", message)

        Thread.sleep(2000) // 等待消费者处理

        // 验证只处理了一次（业务数据只有一条）
        val events = orderEventRepository.findByOrderId(1L)
        assertThat(events).hasSize(1)
    }
}
```

---

## 第三方 HTTP 服务集成测试（WireMock）

```kotlin
class PaymentServiceIntegrationTest : IntegrationTestBase() {

    @Autowired lateinit var paymentService: PaymentService
    private lateinit var wireMockServer: WireMockServer

    @BeforeEach
    fun setupWireMock() {
        wireMockServer = WireMockServer(
            WireMockConfiguration.options().port(wireMock.getMappedPort(8080))
        )
        wireMockServer.start()
    }

    @AfterEach
    fun tearDownWireMock() {
        wireMockServer.stop()
    }

    @Test
    fun `支付成功时正确解析响应并更新订单状态`() {
        // 配置 WireMock 返回支付成功响应
        wireMockServer.stubFor(
            WireMock.post(WireMock.urlEqualTo("/v1/charges"))
                .willReturn(WireMock.aResponse()
                    .withStatus(200)
                    .withHeader("Content-Type", "application/json")
                    .withBody("""{"chargeId":"ch_123","status":"succeeded","amount":9900}""")
                )
        )

        val result = paymentService.charge(orderId = 1L, amount = 99.toBigDecimal())

        assertThat(result.chargeId).isEqualTo("ch_123")
        assertThat(result.success).isTrue()

        // 验证请求参数正确
        wireMockServer.verify(
            WireMock.postRequestedFor(WireMock.urlEqualTo("/v1/charges"))
                .withRequestBody(WireMock.containing("\"amount\":9900"))
        )
    }

    @Test
    fun `第三方服务超时时触发重试，超过最大次数后抛出异常`() {
        wireMockServer.stubFor(
            WireMock.post(WireMock.urlEqualTo("/v1/charges"))
                .willReturn(WireMock.aResponse().withFixedDelay(10_000)) // 模拟超时
        )

        assertThrows<PaymentTimeoutException> {
            paymentService.charge(orderId = 1L, amount = 99.toBigDecimal())
        }

        // 验证重试了 3 次
        wireMockServer.verify(3, WireMock.postRequestedFor(WireMock.urlEqualTo("/v1/charges")))
    }

    @Test
    fun `第三方服务返回 5xx 时降级处理`() {
        wireMockServer.stubFor(
            WireMock.post(WireMock.urlEqualTo("/v1/charges"))
                .willReturn(WireMock.serverError().withBody("""{"error":"Service unavailable"}"""))
        )

        assertThrows<PaymentServiceException> {
            paymentService.charge(orderId = 1L, amount = 99.toBigDecimal())
        }
    }
}
```

---

## Python（pytest + 所有组件）

```python
# tests/conftest.py
import pytest
import redis
import pika
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base

TEST_MYSQL_URL = "mysql+pymysql://test:test@localhost:3307/testdb"
TEST_REDIS_HOST = "localhost"
TEST_REDIS_PORT = 6380

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_MYSQL_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    conn = db_engine.connect()
    tx = conn.begin()
    session = sessionmaker(bind=conn)()
    yield session
    session.close()
    tx.rollback()
    conn.close()

@pytest.fixture
def redis_client():
    client = redis.Redis(host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, decode_responses=True)
    client.flushdb()  # 每次测试前清空
    yield client
    client.flushdb()  # 测试后清空

@pytest.fixture
def rabbitmq_channel():
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost", 5673))
    channel = conn.channel()
    yield channel
    conn.close()


# tests/integration/test_cache_integration.py
class TestRedisCacheIntegration:

    def test_cache_hit_does_not_query_database(self, db_session, redis_client):
        from app.services.product_service import ProductService
        service = ProductService(db=db_session, redis=redis_client)

        product = Product(name="测试商品", price=99.0)
        db_session.add(product)
        db_session.flush()

        # 第一次查询，写入缓存
        service.get_by_id(product.id)
        assert redis_client.exists(f"product:{product.id}")

        # 修改数据库
        product.name = "数据库已修改"
        db_session.flush()

        # 第二次查询，命中缓存，返回旧值
        result = service.get_by_id(product.id)
        assert result.name == "测试商品"

    def test_update_invalidates_cache(self, db_session, redis_client):
        from app.services.product_service import ProductService
        service = ProductService(db=db_session, redis=redis_client)

        product = Product(name="原始名称", price=99.0)
        db_session.add(product)
        db_session.flush()

        service.get_by_id(product.id)  # 触发缓存
        assert redis_client.exists(f"product:{product.id}")

        service.update(product.id, {"name": "新名称"})  # 应清除缓存
        assert not redis_client.exists(f"product:{product.id}")

        result = service.get_by_id(product.id)
        assert result.name == "新名称"
```

---

## Jenkins 集成

```groovy
stage('Integration Test') {
    steps {
        // 启动所有依赖组件
        sh 'docker-compose -f docker-compose.test.yml up -d'
        sh 'sleep 15'  // 等待组件就绪

        sh './gradlew integrationTest'
    }
    post {
        always {
            junit 'build/test-results/integrationTest/**/*.xml'
            sh 'docker-compose -f docker-compose.test.yml down'
        }
    }
}
```

`docker-compose.test.yml`：

```yaml
version: '3.9'
services:
  mysql:
    image: mysql:8.0
    ports: ["3307:3306"]
    environment:
      MYSQL_DATABASE: testdb
      MYSQL_USER: test
      MYSQL_PASSWORD: test
      MYSQL_ROOT_PASSWORD: root
  redis:
    image: redis:7-alpine
    ports: ["6380:6379"]
  rabbitmq:
    image: rabbitmq:3.12-management
    ports: ["5673:5672"]
  wiremock:
    image: wiremock/wiremock:3.3.1
    ports: ["9090:8080"]
```

---

## 测试分层建议

```
每次提交（< 1 分钟）
  └── unit-test-gen：纯逻辑，全 Mock

PR 合并前（5–15 分钟）
  └── integration-test-gen：真实 MySQL + Redis + MQ + HTTP

发布前回归（15–30 分钟）
  └── 单元 + 集成 + e2e-test-gen（完整用户流程）
```

需要测试哪个组件，在 `IntegrationTestBase` 里启动对应的容器即可，不需要全部启动。
