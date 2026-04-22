---
name: api-contract
description: 设计并生成 RESTful API 接口契约，输出 OpenAPI 3.0 规范文档。当用户说"定义接口"、"写 API 文档"、"设计 REST 接口"、"接口契约"、"前后端接口对齐"、"写 OpenAPI"、"swagger 怎么写"时触发。确保前后端在开发前对齐接口定义。
---

# API Contract

生成标准 OpenAPI 3.0 接口契约，前后端开发前对齐。

## 接口设计规范

### URL 设计

```
# 资源用名词复数，动作用 HTTP 方法表达
GET    /api/v1/users              # 列表
GET    /api/v1/users/{id}         # 详情
POST   /api/v1/users              # 创建
PUT    /api/v1/users/{id}         # 全量更新
PATCH  /api/v1/users/{id}         # 部分更新
DELETE /api/v1/users/{id}         # 删除

# 嵌套资源
GET    /api/v1/users/{id}/orders  # 用户的订单列表

# 动作型操作（无法用 CRUD 表达时）
POST   /api/v1/users/{id}/activate
POST   /api/v1/orders/{id}/cancel
```

### 统一响应结构

```json
// 成功响应
{
  "code": 0,
  "message": "success",
  "data": { ... }
}

// 分页列表
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [ ... ],
    "total": 100,
    "page": 1,
    "pageSize": 20
  }
}

// 错误响应
{
  "code": 40001,
  "message": "邮箱格式不正确",
  "data": null
}
```

### 错误码规范

| 范围 | 含义 |
|------|------|
| 0 | 成功 |
| 40001–40099 | 参数校验错误 |
| 40101–40199 | 认证/鉴权错误 |
| 40401–40499 | 资源不存在 |
| 50001–50099 | 服务器内部错误 |

---

## OpenAPI 3.0 模板

```yaml
openapi: 3.0.3
info:
  title: [服务名] API
  version: v1.0.0
  description: [服务描述]

servers:
  - url: https://api.staging.example.com
    description: Staging 环境
  - url: https://api.example.com
    description: 生产环境

tags:
  - name: users
    description: 用户管理

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    # 通用响应包装
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          example: 0
        message:
          type: string
          example: success
        data:
          type: object

    # 分页信息
    PageInfo:
      type: object
      properties:
        total:
          type: integer
        page:
          type: integer
        pageSize:
          type: integer

    # 错误响应
    ErrorResponse:
      type: object
      properties:
        code:
          type: integer
          example: 40001
        message:
          type: string
          example: 邮箱格式不正确
        data:
          type: object
          nullable: true

    # 业务模型示例
    UserDto:
      type: object
      required: [id, email, createdAt]
      properties:
        id:
          type: integer
          format: int64
          example: 1001
        email:
          type: string
          format: email
          example: user@example.com
        name:
          type: string
          example: 张三
        status:
          type: string
          enum: [ACTIVE, INACTIVE]
        createdAt:
          type: string
          format: date-time

    CreateUserRequest:
      type: object
      required: [email, password, name]
      properties:
        email:
          type: string
          format: email
        password:
          type: string
          minLength: 8
          description: 至少 8 位，需包含字母和数字
        name:
          type: string
          maxLength: 50

security:
  - BearerAuth: []

paths:
  /api/v1/users:
    get:
      tags: [users]
      summary: 获取用户列表
      operationId: listUsers
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            default: 1
        - name: pageSize
          in: query
          schema:
            type: integer
            default: 20
            maximum: 100
        - name: keyword
          in: query
          description: 按姓名/邮箱搜索
          schema:
            type: string
      responses:
        '200':
          description: 成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
                  - type: object
                    properties:
                      data:
                        allOf:
                          - $ref: '#/components/schemas/PageInfo'
                          - type: object
                            properties:
                              items:
                                type: array
                                items:
                                  $ref: '#/components/schemas/UserDto'
        '401':
          description: 未认证
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

    post:
      tags: [users]
      summary: 创建用户
      operationId: createUser
      security: []  # 注册接口不需要登录
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
            example:
              email: user@example.com
              password: Pass1234
              name: 张三
      responses:
        '201':
          description: 创建成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
                  - type: object
                    properties:
                      data:
                        $ref: '#/components/schemas/UserDto'
        '400':
          description: 参数错误
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
              example:
                code: 40001
                message: 邮箱格式不正确
                data: null
        '409':
          description: 邮箱已存在
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

  /api/v1/users/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: integer
          format: int64
    get:
      tags: [users]
      summary: 获取用户详情
      operationId: getUserById
      responses:
        '200':
          description: 成功
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
                  - type: object
                    properties:
                      data:
                        $ref: '#/components/schemas/UserDto'
        '404':
          description: 用户不存在
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
```

---

## 输出说明

1. 将生成的 YAML 保存为 `docs/api/openapi.yaml`
2. 标注所有需要前后端确认的字段（用注释 `# TODO: 确认`）
3. 列出接口变更对已有客户端的影响（Breaking Change 标红）
4. 建议使用 Swagger UI 或 Apifox 预览文档
