---
name: docker-deploy
description: 生成和优化 Dockerfile、docker-compose.yml，解决容器化部署问题。当用户说"写 Dockerfile"、"容器化这个服务"、"docker-compose 怎么配"、"镜像太大了"、"容器启动失败"时触发。支持 Python / Java/Kotlin / TypeScript 服务的容器化。
---

# Docker Deploy

生产级容器化配置，覆盖镜像构建和多服务编排。

## Dockerfile 模板

### Java / Kotlin（Spring Boot）

```dockerfile
# 多阶段构建：构建阶段
FROM gradle:8.5-jdk21 AS builder
WORKDIR /app
# 先复制依赖文件，利用层缓存
COPY build.gradle.kts settings.gradle.kts ./
COPY gradle/ gradle/
RUN gradle dependencies --no-daemon || true
# 再复制源码构建
COPY src/ src/
RUN gradle bootJar --no-daemon -x test

# 运行阶段：使用精简镜像
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

# 安全：非 root 用户运行
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

# 复制构建产物
COPY --from=builder /app/build/libs/*.jar app.jar

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

EXPOSE 8080
ENTRYPOINT ["java", "-XX:+UseContainerSupport", "-XX:MaxRAMPercentage=75.0", "-jar", "app.jar"]
```

### Python（FastAPI / Django）

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
# 依赖层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appgroup . .

ENV PATH=/home/appuser/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 前端（TypeScript / React）

```dockerfile
# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline
COPY . .
RUN npm run build

# Nginx 运行阶段
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**nginx.conf（前端 SPA 路由支持）**：
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源长缓存
    location ~* \.(js|css|png|jpg|ico|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://backend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## docker-compose.yml（本地开发 / Staging 环境）

```yaml
version: '3.9'

services:
  backend:
    image: your-registry.com/backend:${IMAGE_TAG:-latest}
    container_name: backend
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: ${ENV:-staging}
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/${DB_NAME}
      SPRING_DATASOURCE_USERNAME: ${DB_USER}
      SPRING_DATASOURCE_PASSWORD: ${DB_PASSWORD}
      SPRING_REDIS_HOST: redis
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs/backend:/app/logs
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  frontend:
    image: your-registry.com/frontend:${IMAGE_TAG:-latest}
    container_name: frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - app-network

  postgres:
    image: postgres:16-alpine
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    networks:
      - app-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: redis
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      retries: 5

volumes:
  postgres_data:
  redis_data:

networks:
  app-network:
    driver: bridge
```

**配套的 `.env.example`**：
```bash
ENV=staging
IMAGE_TAG=latest
DB_NAME=myapp
DB_USER=myapp_user
DB_PASSWORD=change_me_in_production
REDIS_PASSWORD=change_me_in_production
```

---

## 常见问题排查

```bash
# 查看容器日志
docker logs -f --tail=100 <container_name>

# 进入容器调试
docker exec -it <container_name> sh

# 查看容器资源使用
docker stats

# 镜像大小分析
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# 清理无用资源
docker system prune -f
```

## 镜像优化原则

1. 多阶段构建，运行阶段只包含必要文件
2. 依赖文件先 COPY，利用层缓存加速重复构建
3. 使用 `-alpine` 或 `-slim` 基础镜像
4. 非 root 用户运行，提升安全性
5. 合理设置 JVM 内存参数（`-XX:MaxRAMPercentage`）
