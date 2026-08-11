# MistakeMate

MistakeMate 是一个面向家长与孩子的错题整理、复练和打印工具。

## 本地启动

复制环境变量示例并设置 PostgreSQL 密码：

```powershell
Copy-Item .env.example .env
```

随后启动：

```powershell
docker compose up -d --build
```

打开 `http://localhost:8080`。

## 自动发布到 Docker Hub

仓库已配置 GitHub Actions：每次推送到 `main` 都会自动发布以下镜像标签：

- `docker.io/<你的 Docker Hub 用户名>/mistakemate:latest`
- `docker.io/<你的 Docker Hub 用户名>/mistakemate:sha-<短提交号>`

首次启用前，在 Docker Hub 创建一个名为 `mistakemate` 的仓库，并在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| 类型 | 名称 | 值 |
| --- | --- | --- |
| Variable | `DOCKERHUB_USERNAME` | 你的 Docker Hub 用户名或组织名 |
| Secret | `DOCKERHUB_TOKEN` | Docker Hub 的 Read & Write Personal Access Token |

令牌只能放在 `Secret`，不要写入 `.env`、代码或 Git 提交。设置完成后，推送一次 `main`，在 GitHub 的 **Actions** 页面查看发布结果。
