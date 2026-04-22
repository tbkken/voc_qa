---
name: cicd-pipeline
description: 生成和优化 Jenkins 流水线配置，包括构建、测试、Docker 镜像打包、部署到服务器的完整流程。当用户说"配置 Jenkins"、"写 Jenkinsfile"、"流水线怎么写"、"自动化构建部署"、"CI/CD 配置"时触发。
---

# CI/CD Pipeline

基于 Jenkins + Docker 的完整交付流水线。

## 标准 Jenkinsfile 模板

### 后端服务（Java/Kotlin Spring Boot）

```groovy
pipeline {
    agent any

    environment {
        APP_NAME    = 'your-service-name'
        DOCKER_REGISTRY = 'your-registry.com'
        IMAGE_NAME  = "${DOCKER_REGISTRY}/${APP_NAME}"
        // Jenkins Credentials 中配置
        DOCKER_CREDS = credentials('docker-registry-credentials')
        DEPLOY_HOST  = credentials('deploy-host')
        DEPLOY_KEY   = credentials('deploy-ssh-key')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_COMMIT_SHORT = sh(
                        script: 'git rev-parse --short HEAD',
                        returnStdout: true
                    ).trim()
                    env.IMAGE_TAG = "${env.BRANCH_NAME}-${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        stage('Build & Test') {
            steps {
                sh './gradlew clean test'
            }
            post {
                always {
                    // 发布测试报告
                    junit 'build/test-results/**/*.xml'
                    // 发布覆盖率报告（需 JaCoCo 插件）
                    jacoco execPattern: 'build/jacoco/*.exec'
                }
            }
        }

        stage('Code Quality') {
            steps {
                // SonarQube 扫描（可选，有 SonarQube 时启用）
                // withSonarQubeEnv('sonarqube') {
                //     sh './gradlew sonarqube'
                // }
                sh './gradlew checkstyleMain'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh """
                    docker build \
                        --build-arg BUILD_VERSION=${env.IMAGE_TAG} \
                        -t ${IMAGE_NAME}:${env.IMAGE_TAG} \
                        -t ${IMAGE_NAME}:latest \
                        .
                """
            }
        }

        stage('Push Image') {
            when {
                anyOf {
                    branch 'main'
                    branch 'release/*'
                }
            }
            steps {
                sh """
                    echo ${DOCKER_CREDS_PSW} | docker login ${DOCKER_REGISTRY} \
                        -u ${DOCKER_CREDS_USR} --password-stdin
                    docker push ${IMAGE_NAME}:${env.IMAGE_TAG}
                    docker push ${IMAGE_NAME}:latest
                """
            }
        }

        stage('Deploy to Staging') {
            when { branch 'main' }
            steps {
                sshagent([DEPLOY_KEY]) {
                    sh """
                        ssh -o StrictHostKeyChecking=no deploy@${DEPLOY_HOST} '
                            docker pull ${IMAGE_NAME}:${env.IMAGE_TAG}
                            docker stop ${APP_NAME} || true
                            docker rm ${APP_NAME} || true
                            docker run -d \
                                --name ${APP_NAME} \
                                --restart unless-stopped \
                                -p 8080:8080 \
                                -e SPRING_PROFILES_ACTIVE=staging \
                                -v /data/${APP_NAME}/logs:/app/logs \
                                ${IMAGE_NAME}:${env.IMAGE_TAG}
                        '
                    """
                }
            }
        }

        stage('Deploy to Production') {
            when { branch 'release/*' }
            input {
                message "确认发布到生产环境？"
                ok "发布"
                parameters {
                    string(name: 'CHANGE_ID', description: '变更单号')
                }
            }
            steps {
                sshagent([DEPLOY_KEY]) {
                    sh """
                        ssh deploy@${DEPLOY_HOST} '
                            docker pull ${IMAGE_NAME}:${env.IMAGE_TAG}
                            # 滚动更新：先启动新容器，健康检查通过后停旧容器
                            docker run -d \
                                --name ${APP_NAME}-new \
                                -p 8081:8080 \
                                -e SPRING_PROFILES_ACTIVE=production \
                                ${IMAGE_NAME}:${env.IMAGE_TAG}

                            # 等待健康检查
                            sleep 30
                            curl -f http://localhost:8081/actuator/health || exit 1

                            # 切换
                            docker stop ${APP_NAME} || true
                            docker rename ${APP_NAME}-new ${APP_NAME}
                        '
                    """
                }
            }
        }
    }

    post {
        success {
            echo "✅ 流水线成功：${env.IMAGE_TAG}"
            // 钉钉/企微通知（可选）
        }
        failure {
            echo "❌ 流水线失败，请检查日志"
            // 发送失败通知
        }
        always {
            // 清理本地 Docker 镜像，避免磁盘积累
            sh "docker image prune -f --filter 'until=24h'"
        }
    }
}
```

---

### 前端服务（TypeScript/React）

```groovy
pipeline {
    agent any

    environment {
        APP_NAME = 'frontend-app'
        DOCKER_REGISTRY = 'your-registry.com'
        IMAGE_NAME = "${DOCKER_REGISTRY}/${APP_NAME}"
    }

    stages {
        stage('Install Dependencies') {
            steps {
                // 使用缓存加速
                sh 'npm ci --prefer-offline'
            }
        }

        stage('Lint & Type Check') {
            parallel {
                stage('ESLint') {
                    steps { sh 'npm run lint' }
                }
                stage('TypeScript') {
                    steps { sh 'npm run type-check' }
                }
            }
        }

        stage('Test') {
            steps {
                sh 'npm run test -- --coverage --ci'
            }
            post {
                always {
                    publishHTML(target: [
                        allowMissing: false,
                        reportDir: 'coverage/lcov-report',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }

        stage('Build') {
            steps {
                sh 'npm run build'
            }
        }

        stage('Docker Build & Push') {
            when { branch 'main' }
            steps {
                sh """
                    docker build -t ${IMAGE_NAME}:${env.GIT_COMMIT_SHORT} .
                    docker push ${IMAGE_NAME}:${env.GIT_COMMIT_SHORT}
                """
            }
        }
    }
}
```

---

## 关键配置说明

### Jenkins Credentials 配置

| Credential ID | 类型 | 用途 |
|--------------|------|------|
| `docker-registry-credentials` | Username/Password | Docker 仓库登录 |
| `deploy-ssh-key` | SSH Private Key | 部署服务器 SSH 密钥 |
| `deploy-host` | Secret text | 部署服务器地址 |

### 分支策略

| 分支 | 触发行为 |
|------|----------|
| `feature/*` | 构建 + 测试 |
| `main` | 构建 + 测试 + 推送镜像 + 部署 Staging |
| `release/*` | 构建 + 测试 + 推送镜像 + 人工确认 + 部署 Production |
| `hotfix/*` | 构建 + 测试 + 人工确认 + 直接部署 Production |

### 加速构建的技巧

```groovy
// Gradle 构建缓存
sh './gradlew --build-cache --parallel test'

// Docker 层缓存（在 Dockerfile 里先 COPY 依赖文件）
// 详见 docker-deploy skill

// npm 依赖缓存（Jenkins pipeline cache plugin）
cache(maxCacheSize: 500, defaultBranch: 'main', caches: [
    arbitraryFileCache(path: 'node_modules')
]) {
    sh 'npm ci'
}
```
