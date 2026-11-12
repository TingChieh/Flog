# Flog

一个基于 Flask 的个人博客与轻量内容管理系统：写文章、发布页面、收评论、做播客，后台一处管理。没有前端构建步骤，Python 加原生 JavaScript 和 CSS 就能跑。

线上站点：[flog.aisaka.cc](https://flog.aisaka.cc)

## 功能

**写作与内容**

- 文章：Markdown / HTML、分类、浏览量、表情回应（读者给文章选一个 emoji）、草稿自动保存与修订历史、预览和发布状态控制
- 编辑器：Typora 式即时渲染的 Markdown 编辑器（Vditor，自托管，无外部请求）
- 渲染：表格（保留列对齐）、任务列表 `- [ ]`、行内公式 `$…$`、块级公式 `$$…$$` 和 ` ```mermaid ` 流程图；公式和图表只在发布后的页面渲染，页面真的含有时才加载对应脚本
- 独立页面：可配置标题、slug、摘要、是否进导航；导航顺序可在后台列表里用 ↑ ↓ 直接调整；改 slug 后旧地址自动 301
- 图片库：记录每张图的名称、备注、大小和上传者，可搜索，显示被哪些文章和页面引用，编辑器里可直接选图；支持 HEIC 与 Live Photo
- 播客：可开关（后台“网站管理 → 播客”），开启后菜单出现“播客”，有节目页、单集页（播放器、点时间轴跳转）、评论和 RSS；外观、导航和页脚沿用博客，旧播客域名可重定向过来，见 [docs/podcast.md](docs/podcast.md)

**互动**

- 评论：两层回复、首次评论审核、受限 Markdown，可按文章或页面开关；新评论、回复和审核结果可邮件通知，评论者自愿勾选并可退订
- 搜索：SQLite 上用 FTS5，其他数据库用 `LIKE`
- 用户：注册登录、密码重置（登录失败和重置邮件按网络地址与邮箱限频）；角色只有普通用户和管理员

**后台**（`/admin`）

- 文章、页面、分类、评论、图片、用户（新建、编辑、删除并转交文章）、站点文案与设置、播客、邮件
- 邮件页：通过 Resend 查看收发的邮件，并直接写信、回信；“已收到”默认只列出发给 `MAIL_FROM` 和 `MAIL_SENDERS` 地址的邮件，其余（多半是垃圾邮件）折叠，可一键展开

**其他**

- 界面仅提供简体中文，文案由 Flask-Babel 管理
- 文章字体按用到的字切成子集并按页预加载
- 部署与备份脚本：`scripts/deploy.sh`、`scripts/backup_r2.sh`，以及 `deploy/systemd/` 下的 systemd 单元模板

## 技术栈

- Python 3.14、Flask 3
- SQLAlchemy 2、Flask-Migrate / Alembic
- SQLite（本地默认）或 MySQL / MariaDB（生产）
- Jinja2、原生 JavaScript、CSS
- Vditor 4.0.1（Markdown 编辑器，位于 `app/static/vendor/vditor/`，只保留必需文件，见其中的 README）
- Bootstrap 5.3.3 CSS、KaTeX 0.19.0 与 Mermaid 12.2.0（位于 `app/static/vendor/`，自托管）
- mutagen（读取 MP3 / M4A 的时长）
- Gunicorn；Pytest 与 Node.js Test Runner

## 项目结构

```text
Flog/
├── app/
│   ├── admin/              # 后台蓝图：每个管理区域一个模块
│   ├── static/             # 样式、脚本、图片、字体与前端依赖
│   ├── templates/          # 公共页面、后台与邮件模板
│   ├── translations/       # Babel 翻译资源（.po 与编译后的 .mo 都提交）
│   ├── __init__.py         # Flask 应用与扩展初始化，末尾导入各模块以注册路由和钩子
│   ├── models.py           # 数据模型
│   ├── routes.py           # 公共路由
│   ├── pages.py            # 独立页面与导航顺序
│   ├── podcast.py          # 播客：音频、单集与 RSS
│   └── post_drafts.py      # 草稿与修订
├── deploy/systemd/         # systemd 单元模板：应用服务、每日 R2 备份的 service 与 timer
├── docs/                   # 迁移、播客、Caddy 配置等文档
├── migrations/             # Alembic 数据库迁移
├── scripts/
│   ├── bootstrap.sh        # 一键搭建开发环境并启动
│   ├── deploy.sh           # 部署公开仓库的 main 到生产服务器
│   ├── backup_r2.sh        # 把数据库、上传目录和 .env 备份到 Cloudflare R2
│   ├── e2e_live_photo.py   # 用真实浏览器验证 Live Photo 与图片交付
│   └── generate_article_fonts.py  # 生成文章字体子集
├── tests/                  # Python 与 JavaScript 测试
├── config.py               # 环境变量与应用配置
├── flog.py                 # 应用入口及 Flask shell 上下文
└── requirements*.txt       # 运行及开发依赖
```

业务逻辑放在 `app/` 下的普通模块里（草稿、评论、图片、搜索、点赞等），视图只负责接请求；`AGENTS.md` 里有给 AI 助手的补充说明。

## 本地开发

### 一键启动（推荐）

```bash
git clone git@github.com:TingChieh/Flog.git
cd Flog
./scripts/bootstrap.sh
```

脚本依次：

1. 创建 Python 3.14 虚拟环境 `.venv`（有 [uv](https://docs.astral.sh/uv/) 时用 uv，否则需要本机有 `python3.14`；版本不符时自动重建）
2. 安装 `requirements-dev.txt`
3. 没有 `.env` 时从 `.env.example` 复制并生成随机 `SECRET_KEY`，数据库回退到本地 SQLite
4. 编译翻译、执行数据库迁移
5. 启动开发服务器 <http://127.0.0.1:5000>

| 参数 | 作用 |
| --- | --- |
| `--upgrade` | 先用 uv 把 `requirements.in` 重新解析为最新版本并写入 `requirements.txt` |
| `--no-run` | 只配置环境，不启动服务器 |
| `--prod` | 仅安装运行时依赖（不含 pytest） |

### 手动步骤

```bash
python3.14 -m venv .venv
source .venv/bin/activate            # Windows PowerShell：.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env                 # 至少改掉 SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"   # 生成随机密钥
flask db upgrade
flask run                            # http://127.0.0.1:5000
```

没有配置 `DATABASE_URL` 时，应用使用 `instance/flog.sqlite3`。

## 环境变量

配置只来自 `.env` 或进程环境变量，改完需要重启应用；后台没有编辑环境变量的页面。`.env` 里多余的旧变量（如 `REDIS_URL`、翻译密钥）会被忽略。

| 变量 | 是否必需 | 用途 |
| --- | --- | --- |
| `SECRET_KEY` | 是 | Session、CSRF 与令牌签名密钥 |
| `DATABASE_URL` | 否 | 数据库连接；未设置时使用 SQLite |
| `ADMIN_EMAILS` | 建议 | 出错通知和新评论通知的收件人，多个地址用逗号分隔；没设 `MAIL_FROM` 且 `MAIL_USERNAME` 不是邮箱地址时，其中第一个也作为邮件的发件人 |
| `MAIL_SERVER` | 邮件功能需要 | SMTP 服务器 |
| `MAIL_PORT` | 否 | SMTP 端口，默认 `465` |
| `MAIL_USE_SSL` | 否 | 是否使用 SSL，默认 `true` |
| `MAIL_USERNAME` | 邮件功能需要 | SMTP 用户名；它是邮箱地址时同时作为发件地址 |
| `MAIL_PASSWORD` | 邮件功能需要 | SMTP 密码或授权码 |
| `MAIL_FROM` | 否 | 发件地址。SMTP 用户名不是邮箱地址时必须设置（例如 Resend：用户名 `resend`，密码是 API Key，发件地址用已验证域名下的地址） |
| `MAIL_SENDERS` | 否 | 后台“邮件”页写信时可选的发件地址，逗号分隔，须是 Resend 已验证域名下的地址；`MAIL_FROM` 始终可选 |
| `RESEND_API_KEY` | 否 | Resend 的 Full access 密钥，供后台“邮件”页查看收发的邮件；不设置则该页只显示配置说明 |
| `UPLOAD_FOLDER` | 否 | 上传目录，默认 `instance/uploads` |
| `SITE_URL` | 否 | 本站的公开网址（不带结尾斜杠），旧播客域名重定向时用它拼出目标地址；以 `https://` 开头时登录 Cookie 只经 HTTPS 发送 |
| `PODCAST_REDIRECT_HOSTS` | 否 | 以前是播客独立站的域名，逗号分隔；访问它们会 301 到 `SITE_URL` 下的 `/podcast/`，旧单集地址和旧 RSS 地址也会对应跳转 |
| `PODCAST_AUDIO_MAX_MB` | 否 | 后台上传单集音频的大小上限（MB），默认 `300` |
| `DISPLAY_TIMEZONE` | 否 | 页面上日期的显示时区，默认 `Asia/Shanghai`；数据库里统一存 UTC |
| `GTM_ID` | 否 | Google Tag Manager 容器 ID（形如 `GTM-XXXXXXX`），不设置则不加载 |
| `GA_MEASUREMENT_ID` | 否 | Google Analytics 测量 ID（形如 `G-XXXXXXXXXX`），不设置则不加载 |

不要提交 `.env`、数据库、日志、上传文件或生产数据。

## 测试

```bash
pytest                       # Python 测试，默认用内存 SQLite
node --test tests/*.test.js  # 前端测试（需要较新的 Node.js）
```

完整测试约一千个、两分钟左右；改动时先用 `pytest -q -k <关键字>` 跑相关部分。

**MySQL / MariaDB**：把 `TEST_DATABASE_URL` 设为本机专用测试库的 SQLAlchemy URL（例如通过环境变量注入凭据），再运行 `pytest -q -ra`。测试会反复创建和删除该库中的表，所以只允许本机地址且库名以 `test` 结尾。SQLite FTS5 专属测试在 MySQL 上跳过。默认使用数据库自己的隔离级别，可用 `DB_ISOLATION_LEVEL` 显式指定（`READ COMMITTED`、`READ UNCOMMITTED`、`REPEATABLE READ`、`SERIALIZABLE` 或 `AUTOCOMMIT`）。在 MySQL/MariaDB 上请设为 `READ COMMITTED`，以支持 MariaDB 11.8 的并发草稿写入；该隔离级别下，同一事务内的重复读取可能看到其他事务新提交的数据。

**浏览器端到端**（Live Photo 首次自动播放与 LIVE 按钮、灯箱、后台成对上传；需要 Node.js 和 ffmpeg，首次运行 `npx` 会下载 Playwright CLI，使用临时数据库和上传目录，不会动 `instance/`）：

```bash
.venv/bin/python scripts/e2e_live_photo.py [--headed] [--keep]
```

## 部署

生产服务器（以 `flog` 用户运行，systemd 服务 `flog`）始终跟随公开仓库的 `origin/main`。服务器访问不了 github.com，所以由本机推送：

```bash
git push origin main
./scripts/deploy.sh --dry-run   # 先看会发布哪些提交
./scripts/deploy.sh             # 备份 → 同步代码 → 依赖 → ffmpeg → 迁移 → 重启 → 回填 → 冒烟测试
```

提交以 git bundle 经 SSH 传到服务器，再作为 `origin/main` 快进合并，所以服务器版本严格等于公开仓库。脚本在改动任何东西之前，先把数据库、上传目录和 `.env` 备份到服务器上的备份目录，失败时会打印回滚命令。选项：`--no-optimize` 跳过旧图回填，`--recompress` 同时就地压缩旧图。

服务器的地址、目录等放在仓库之外的 `~/.config/flog/deploy.env`（路径可用 `FLOG_DEPLOY_ENV` 改，环境变量优先），不要提交。它是 `KEY=value` 文件：

- 必填：`DEPLOY_HOST`（SSH 别名）、`DEPLOY_DIR`（服务器上的检出目录）、`DEPLOY_UV`（服务器上 `uv` 的绝对路径）、`DEPLOY_UPLOADS`（`.env` 里的 `UPLOAD_FOLDER`）、`DEPLOY_BACKUPS`、`DEPLOY_SITE`（站点网址）
- 可选：`DEPLOY_USER`、`DEPLOY_SERVICE`、`DEPLOY_VENV`、`DEPLOY_LOCAL_URL`、`DEPLOY_KEEP_BACKUPS`（备份目录里保留最近几份部署前备份，默认 10，更早的每次部署时自动删除；见脚本头部）

Caddy 配置不由脚本修改；让 Caddy 直接发图的配置见 [docs/caddy-uploads.md](docs/caddy-uploads.md)。

## 备份

`deploy.sh` 的备份只存在服务器本机，丢了服务器就一起丢。异地备份用 `scripts/backup_r2.sh`，把整站存到 Cloudflare R2：

| 内容 | R2 里的位置 | 方式 |
| --- | --- | --- |
| 数据库 | `db/flog-<时间戳>.sql.gz` | 每次一份 `mysqldump`，写入前校验压缩包完整且非空 |
| `.env` | `env/env-<时间戳>` | 每次一份 |
| 上传目录（图片、Live Photo 视频、播客音频） | `uploads/` | 镜像同步，只传新增或变化的文件，重复运行很快 |
| 服务器上已删除的上传文件 | `uploads-removed/<时间戳>/` | 不直接销毁，先移到这里 |

`db/`、`env/` 和 `uploads-removed/` 超过 `BACKUP_KEEP_DAYS`（默认 30 天）后自动清理。`.env` 含密钥，请把存储桶设为私有，并给脚本用只限这一个桶的 R2 API 令牌。

**准备**

1. 在 Cloudflare 里建一个私有存储桶，再创建只限该桶读写的 API 令牌，记下账户 ID、Access Key ID 和 Secret Access Key。
2. 服务器上安装 [rclone](https://rclone.org/)（脚本通过环境变量配置 R2，不需要 `rclone config`）。
3. 在服务器的项目根目录写 `.env.backup`（和 `.env` 并排，已被 `.gitignore` 忽略；路径可用 `FLOG_BACKUP_ENV` 改，环境变量优先），权限设为 `600`：

```bash
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=...
BACKUP_UPLOADS=/path/to/uploads      # 即 .env 里的 UPLOAD_FOLDER
BACKUP_ENV_FILE=/path/to/flog/.env
# 可选：BACKUP_PREFIX（默认 flog）、BACKUP_KEEP_DAYS（默认 30）、BACKUP_DB_NAME（默认 flog）
```

**运行**

```bash
scripts/backup_r2.sh --dry-run   # 只显示会传什么、删什么
scripts/backup_r2.sh
```

确认能跑后每天执行一次：`deploy/systemd/` 里有 `flog-backup.service` 和 `flog-backup.timer` 模板（默认每天 03:30），把其中的路径改成服务器上的检出目录，用 `systemctl link` 装上，再 `systemctl enable --now flog-backup.timer`。**恢复**：从 R2 下载最新的 `db/` 转储用 `gunzip -c … | mysql flog` 导回，`uploads/` 同步回上传目录，`env/` 里取回 `.env`。

## Markdown 编辑器

文章和独立页面使用 Vditor 的“即时渲染”模式：写 Markdown 的同时，光标所在行显示源码标记，其余内容直接渲染；也可以切换到分屏预览。图片可通过工具栏、拖拽或粘贴上传，沿用 `/upload` 接口。

编辑器里的渲染引擎（Lute）和站点发布页的渲染（Python-Markdown：`extra`、`sane_lists`、`codehilite`）不是同一个，细节会有差异（例如软换行、脚注编号）；工具栏因此只提供站点能渲染的语法（没有删除线、任务列表、公式）。已有的旧版 HTML 内容仍用普通文本框编辑。

## 界面语言

站点界面仅提供简体中文，不会根据浏览器语言切换。模板里的 `_()` 原文是英文，中文译文维护在 `app/translations/zh/LC_MESSAGES/messages.po`，`.po` 与编译后的 `.mo` 都要提交。新增或修改了带 `_()` 的文案后：

```bash
flask translate update
flask translate compile
```

`update` 会把相近的旧译文标记为 `fuzzy`，而 `fuzzy` 条目不会被编译，请逐条核对后删除该标记。

## 数据库升级提示

后台内容管理统一位于 `/admin`，旧管理地址保留兼容重定向。升级已有 MySQL 数据库前，先读 [后台 CMS 迁移说明](docs/admin-cms-migration.md)，并**先备份数据库**。以下迁移会删除数据，降级只会重建空表：

- `bad2dd157a5f`：永久删除友链、留言簿、Todo 和电影的数据（含 `kind='module'` 的页面记录）。需要类似页面时，请在后台新建自定义内容页。
- `5a1f9c0d7e42`：永久删除 `message`、`notification` 和 `task` 三张表的数据（私信、个人资料和文章导出已移除）。
- `c8d3a5e7b102`：删除遗留的 `about` 表（正文早已在 `9c8e2f3a4b5d` 中搬进 `page` 表）。`/about` 仍由通用页面路由提供，`/about/edit` 已移除，请在后台“页面管理”里编辑。

`d5e7b9c1f203` 新增图片库 `image` 表，降级只会删除该表，不动磁盘上的图片。升级后第一次打开后台“图片”页时，上传目录里已有的图片会自动登记。

## License

本项目以 [MIT 许可证](LICENSE) 发布。

`app/static/vendor/` 下的第三方库（Vditor、KaTeX、Mermaid、PhotoSwipe）和 `app/static/fonts/` 下的字体（Source Serif 4、Noto Serif SC）各自保留其原有许可证，见对应目录里的许可证文件。
