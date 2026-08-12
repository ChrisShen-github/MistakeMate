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

## 本地 OCR

上传图片、PDF、HEIC 或 HEIF 后，MistakeMate 会在后台使用 PaddleOCR 3.7 和 PP-OCRv6 进行本地识别。题图不会发送到第三方 OCR 服务。

- 首次识别需要下载约数百 MB 的模型，耗时取决于网络速度；后续会直接复用缓存。
- JPG、PNG 和 WebP 图片可在上传前手动截取识别范围；系统只裁剪临时 OCR 输入，完整原图仍会保留。
- 模型保存在项目的 `models/` 目录，原图保存在 `storage/`，数据库保存在 `postgres-data/`。这三个运行目录都不会提交到 Git。
- CPU 识别时应用容器通常需要约 1 GB 内存。手写、公式和图形题仍应结合原图人工核对；当前 OCR 文本是可继续编辑和拆题的初稿。
- 识别完成后会自动生成一张可编辑的题目初稿。请核对题干、选项和答案，再补充知识点、难度与错因；确认后才进入后续错题集和复练安排。
- 多问计算题或综合题可识别 `(1)`、`(2)`、`①`、`②` 等结构：公共题干只保存一次；答案、解析和关键得分点均为可选，不填写答案也能确认完整题目，为后续练习版打印保留每个小问的答题空间。
- 识别失败时，可在错题详情页直接重试；识别成功后也可主动“重新识别”。重新识别会先确认，再覆盖题干、选项和 OCR 答案初稿并清空旧的小问拆分，但会保留难度、知识点和错因。

## 错题打印

“错题集”只读取已确认题目，并提供可实时分页的打印模板编辑器：

- 内置 A3、A4、A5、A6、B4、B5、JIS B5、Letter、Legal、16K，也可输入自定义毫米尺寸；
- 支持横版、竖版、单栏、双栏、四边页距、字号、行距和题间距；
- 内置标准练习、计算题宽松、省纸双栏、大字护眼、A5 小册和答案校对模板；当前设置也可保存为自定义模板；
- 题目可调整顺序、强制题前分页和单题答题行；结构化复合题可分别调整每个小问的答题空间；
- 练习版不要求录入答案；含答案版会对未录答案的题目明确标注“暂未录入”；
- 点击打印后可选择实体打印机，也可使用浏览器的“另存为 PDF”。浏览器会请求当前纸张尺寸，但仍需在系统打印窗口中确认打印机纸盒与纸张一致。

## 自动发布到 Docker Hub

仓库已配置 GitHub Actions：每次推送到 `main` 都会自动发布以下镜像标签：

- `docker.io/<你的 Docker Hub 用户名>/mistakemate:latest`

首次启用前，在 Docker Hub 创建一个名为 `mistakemate` 的仓库，并在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| 类型 | 名称 | 值 |
| --- | --- | --- |
| Variable | `DOCKERHUB_USERNAME` | 你的 Docker Hub 用户名或组织名 |
| Secret | `DOCKERHUB_TOKEN` | Docker Hub 的 Read & Write Personal Access Token |

令牌只能放在 `Secret`，不要写入 `.env`、代码或 Git 提交。设置完成后，推送一次 `main`，在 GitHub 的 **Actions** 页面查看发布结果。
