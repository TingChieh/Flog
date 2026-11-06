# Flog

一个基于 Flask 的个人博客与轻量内容管理系统，支持文章发布、草稿与修订、评论互动、独立页面以及后台管理。

线上站点：[flog.aisaka.cc](https://flog.aisaka.cc)

## 功能

- 文章：Markdown / HTML 内容、分类、浏览量、点赞与评论
- 写作：Typora 式即时渲染 Markdown 编辑器（Vditor，自托管、无外部请求）、自动草稿、文章修订历史、预览与发布状态控制
- 内容管理：可配置的独立页面、导航顺序与旧地址重定向
- 用户：注册登录与密码重置
- 管理后台：集中管理文章、页面、分类、评论、用户（新建、编辑、删除并转交文章）及站点设置；“关于”只是一个普通的页面
- 文章渲染：Markdown 支持表格（保留列对齐）、任务列表 `- [ ]`、行内公式 `$…$`、块级公式 `$$…$$` 和 ` ```mermaid ` 流程图；编辑器里仍显示源码，发布后的页面才会渲染公式和图表
- 图片库：记录每张上传图片的名称、备注、大小和上传者，可搜索，显示被哪些文章和页面引用，编辑器中可直接从图片库选图
- 界面：仅提供简体中文，文案由 Flask-Babel 管理
- 部署：Gunicorn 与数据库迁移支持

## 技术栈

- Python 3.14、Flask 3
- SQLAlchemy 2、Flask-Migrate / Alembic
- SQLite（本地默认）或 MySQL
- Jinja2、原生 JavaScript、CSS
- Vditor 4.0.1（Markdown 编辑器，位于 `app/static/vendor/vditor/`，只保留必需文件，见其中的 README）
- KaTeX 0.19.0 与 Mermaid 12.2.0（文章里的公式和图表，位于 `app/static/vendor/`，自托管，仅在页面真的含有公式或图表时才加载）
- Pytest、Node.js Test Runner
- Gunicorn

## 项目结构

```text
Flog/
├── app/
│   ├── admin/              # 后台管理蓝图、表单与业务路由
│   ├── static/             # 样式、脚本、图片、字体与前端依赖
│   ├── templates/          # 公共页面、用户页面和后台模板
│   ├── translations/       # Babel 翻译资源
│   ├── __init__.py         # Flask 应用与扩展初始化
│   ├── models.py           # 数据模型
│   ├── routes.py           # 公共路由
│   ├── pages.py            # CMS 页面逻辑
│   └── post_drafts.py      # 草稿与修订逻辑
├── docs/                   # 迁移和设计文档
├── migrations/             # Alembic 数据库迁移
├── scripts/
│   ├── bootstrap.sh        # 一键搭建开发环境并启动
│   ├── e2e_live_photo.py   # 用真实浏览器验证 Live Photo 与图片交付
│   └── generate_article_fonts.py  # 生成文章字体子集
├── tests/                  # Python 与 JavaScript 测试
├── config.py               # 环境变量与应用配置
├── flog.py                 # 应用入口及 Flask shell 上下文
└── requirements*.txt       # 运行及开发依赖
```

## 本地开发

### 一键启动（推荐）

```bash
git clone git@github.com:TingChieh/Flog.git
cd Flog

./scripts/bootstrap.sh
```

脚本会依次完成：

1. 创建 Python 3.14 虚拟环境 `.venv`（已安装 [uv](https://docs.astral.sh/uv/) 时使用 uv，否则需要本机有 `python3.14`；虚拟环境版本不符时会自动重建）
2. 安装 `requirements-dev.txt` 中的依赖
3. 若没有 `.env`，从 `.env.example` 复制并生成随机 `SECRET_KEY`，数据库回退到本地 SQLite
4. 编译翻译、执行数据库迁移
5. 启动开发服务器 <http://127.0.0.1:5000>

可选参数：

| 参数 | 作用 |
| --- | --- |
| `--upgrade` | 先用 uv 将 `requirements.in` 重新解析为最新版本并写入 `requirements.txt` |
| `--no-run` | 只配置环境，不启动服务器 |
| `--prod` | 仅安装运行时依赖（`requirements.txt`，不含 pytest） |

### 手动步骤

不使用脚本时，可按以下步骤操作。

#### 1. 创建虚拟环境

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Windows PowerShell 使用：

```powershell
.venv\Scripts\Activate.ps1
```

#### 2. 配置环境变量

```bash
cp .env.example .env
```

至少应修改 `SECRET_KEY`。如果暂时不配置 `DATABASE_URL`，应用会自动使用 `instance/flog.sqlite3`。

生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 3. 初始化数据库并启动

```bash
flask db upgrade
flask run
```

默认访问地址为 <http://127.0.0.1:5000>。

## 环境变量

| 变量 | 是否必需 | 用途 |
| --- | --- | --- |
| `SECRET_KEY` | 是 | Session、CSRF 与令牌签名密钥 |
| `DATABASE_URL` | 否 | 数据库连接；未设置时使用 SQLite |
| `ADMIN_EMAILS` | 建议 | 出错通知的收件人和重置密码邮件的发件人，多个地址用逗号分隔 |
| `MAIL_SERVER` | 邮件功能需要 | SMTP 服务器 |
| `MAIL_PORT` | 否 | SMTP 端口，默认 `465` |
| `MAIL_USE_SSL` | 否 | 是否使用 SSL，默认 `true` |
| `MAIL_USERNAME` | 邮件功能需要 | SMTP 用户名和发件地址 |
| `MAIL_PASSWORD` | 邮件功能需要 | SMTP 密码或授权码 |
| `UPLOAD_FOLDER` | 否 | 上传目录，默认 `instance/uploads` |
| `DISPLAY_TIMEZONE` | 否 | 页面上日期的显示时区，默认 `Asia/Shanghai`；数据库里统一存 UTC |
| `GTM_ID` | 否 | Google Tag Manager 容器 ID（形如 `GTM-XXXXXXX`），不设置则不加载 |
| `GA_MEASUREMENT_ID` | 否 | Google Analytics 测量 ID（形如 `G-XXXXXXXXXX`），不设置则不加载 |

不要提交 `.env`、数据库、日志、上传文件或生产数据。

配置只通过 `.env` 或进程环境变量提供，修改后需要重启应用才会生效；后台没有编辑环境变量的页面。`.env` 中多余的旧变量（如 `REDIS_URL`、翻译密钥）会被忽略。

## 测试

运行 Python 测试：

```bash
pytest
```

默认使用内存 SQLite。要在 MySQL 或 MariaDB 上运行，将 `TEST_DATABASE_URL`
设为本机专用测试库的 SQLAlchemy URL（例如通过环境变量注入凭据），再运行
`pytest -q -ra`。测试会反复创建和删除该库中的表；为防止误用，仅允许本机
地址且数据库名以 `test` 结尾。SQLite FTS5 专属测试在 MySQL 上跳过。
默认使用数据库的隔离级别。可通过 `DB_ISOLATION_LEVEL` 显式设置为
`READ COMMITTED`、`READ UNCOMMITTED`、`REPEATABLE READ`、`SERIALIZABLE`
或 `AUTOCOMMIT`。通过 `TEST_DATABASE_URL` 在 MySQL/MariaDB 上运行测试时，
请设置 `DB_ISOLATION_LEVEL="READ COMMITTED"`，以支持 MariaDB 11.8 的并发草稿写入；
该隔离级别下，同一事务内的重复读取可能看到其他事务新提交的数据。

运行前端 JavaScript 测试（需要较新的 Node.js）：

```bash
node --test tests/*.test.js
```

浏览器端到端检查（Live Photo 首次自动播放与 LIVE 按钮、灯箱、后台成对上传，需要 Node.js 和 ffmpeg；
首次运行时 `npx` 会下载 Playwright CLI，使用临时数据库和上传目录，不会改动 `instance/`）：

```bash
.venv/bin/python scripts/e2e_live_photo.py [--headed] [--keep]
```

## Markdown 编辑器

文章和独立页面使用 Vditor 的"即时渲染"模式：写 Markdown 的同时，光标所在行显示源码标记，其余内容直接渲染；也可以切换到分屏预览。图片可通过工具栏、拖拽或粘贴上传，沿用 `/upload` 接口。

编辑器里的渲染引擎（Lute）和站点发布页的渲染（Python-Markdown：`extra`、`sane_lists`、`codehilite`）不是同一个，细节会有差异（例如软换行、脚注编号）；工具栏因此只提供站点能渲染的语法（没有删除线、任务列表、公式）。已有的旧版 HTML 内容仍用普通文本框编辑。

## 界面语言

站点界面仅提供简体中文，不会根据浏览器语言切换。模板里的 `_()` 原文是英文，对应的中文译文维护在 `app/translations/zh/LC_MESSAGES/messages.po`。

新增或修改了带 `_()` 的文案后，更新并编译翻译：

```bash
flask translate update
flask translate compile
```

`update` 会把相近的旧译文标记为 `fuzzy`，而 `fuzzy` 条目不会被编译，请逐条核对后删除该标记。

## 数据库升级提示

后台内容管理功能统一位于 `/admin`。旧管理地址目前保留兼容重定向；升级已有 MySQL 数据库前，请先阅读 [后台 CMS 迁移说明](docs/admin-cms-migration.md)。

**内置模块已移除**：迁移 `bad2dd157a5f` 会永久删除友链、留言簿、Todo 和电影的数据（含 `kind='module'` 的页面记录），降级只会重建空表。执行 `flask db upgrade` 前请先备份数据库。需要类似页面时，请在后台新建自定义内容页。

**私信、个人资料和文章导出已移除**：迁移 `5a1f9c0d7e42` 会永久删除 `message`、`notification` 和 `task` 三张表的数据，降级只会重建空表。

**新增图片库**：迁移 `d5e7b9c1f203` 创建 `image` 表，降级只会删除该表，不会动磁盘上的图片文件。升级后第一次打开后台“图片”页时，上传目录里已有的图片会自动登记。

**“关于”不再有专用代码**：迁移 `c8d3a5e7b102` 会删除遗留的 `about` 表（正文早已在迁移 `9c8e2f3a4b5d` 中搬进 `page` 表）。降级只会重建空表。已有 `/about` 地址仍由通用页面路由提供，`/about/edit` 已移除，请在后台“页面管理”里编辑。

## License

本项目以 [MIT 许可证](LICENSE) 发布。

`app/static/vendor/` 下的第三方库（Vditor、KaTeX、Mermaid、PhotoSwipe）和 `app/static/fonts/` 下的字体（Source Serif 4、Noto Serif SC）各自保留其原有许可证，见对应目录里的许可证文件。
