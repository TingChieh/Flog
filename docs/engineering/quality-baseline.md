# Flog 工程质量基线审计

本文档基于对当前仓库代码、配置、依赖与测试的实际检查及运行结果建立，仅记录已验证事实，不包含未经证实的推测。

## 1. 当前工程结构概览

| 维度 | 现状 |
| --- | --- |
| 技术栈 | Python 3.14、Flask 3.1、SQLAlchemy 2.1、Flask-Migrate / Alembic、Jinja2、原生 JS / CSS（无前端构建链） |
| 依赖管理 | `requirements.in`（直接依赖）→ `requirements.txt`（`uv pip compile` 锁定），`requirements-dev.txt`（开发依赖） |
| 应用初始化 | `app/__init__.py` 创建全局 `app`、`db`、`login`、`mail`、`babel`、`csrf`，末尾通过导入副作用注册路由、钩子与 CLI |
| 代码规模 | `app/` + `app/admin/` 共 45 个 Python 模块、约 7,088 行；公共路由集中在 `app/routes.py`（637 行）与 `app/podcast_routes.py`（101 行），后台为 `/admin` Blueprint（11 个模块） |
| 业务逻辑分层 | 核心逻辑已独立为普通模块：`content.py`、`markdown_extras.py`、`security.py`、`comment_markdown.py`、`comments.py`、`comment_mail.py`、`post_drafts.py`、`post_views.py`、`likes.py`、`search.py`、`search_index.py`、`pages.py`、`images.py`、`live_photos.py`、`podcast.py`、`authorization.py` |
| 模板体系 | `app/templates/base.html` 为公共壳模板（`index_base.html`、`admin/base.html` 均继承它），`email/base.html` 为邮件模板；模板内零 `|safe` 使用、零直接 ORM 查询 |
| 数据与迁移 | 本地默认 SQLite（带 FTS5 trigram 索引，可重建），生产 MySQL / MariaDB（保留 `LIKE` 回退）；`migrations/versions/` 含 58 个迁移脚本；时间统一存 UTC、按 `DISPLAY_TIMEZONE` 展示 |
| Markdown 与安全 | 文章由 `content.py` + `markdown_extras.py` 渲染并经 `security.py`（`bleach.clean` 白名单）清理；评论由 `comment_markdown.py` 先转义原始 HTML 再渲染并 `bleach.clean` + `linkify`；全仓 `Markup(` 仅出现在 4 个安全/渲染模块；`security_headers.py` 统一设置响应安全头 |
| 静态资源 | `app/static/` 下 20 个自定义 JS、2 个自定义 CSS；`static/vendor/` 托管 Bootstrap 5.3.3、Vditor 4.0.1、KaTeX 0.19.0、Mermaid 12.2.0、PhotoSwipe；`static/fonts/` 含子集化文章字体（17 MB）；`static_cache.py` 注入 `?v=` 内容指纹，`font_preload.py` 按页内联并预加载字体子集 |
| 配置与密钥 | 仅由 `config.py` 读取环境变量 / `.env`；后台不提供环境变量编辑页；`.env`、`instance/`、`logs/` 均被 `.gitignore` 忽略 |
| SEO / RSS / Sitemap | 已实现 `/feed.xml`（带 ETag / 304）、`/rss`（301）、`/sitemap.xml`、`/robots.txt`、`/podcast/feed.xml`、基础 `<title>` 与 `<meta name="description">` |

## 2. 已有质量保障（基线运行结果）

| 检查项 | 执行命令 | 基线结果 |
| --- | --- | --- |
| Python 测试套件 | `.venv/bin/python -m pytest tests -q -ra` | **1157 passed**，6 warnings（268.88s） |
| Node.js 前端测试 | `node --test tests/*.test.js` | **145 passed**, 0 failed（362ms） |
| JS 语法检查 | `node --check app/static/*.js` | 20/20 文件通过 |
| 翻译编译一致性 | `.venv/bin/pybabel compile -d app/translations && git diff --stat app/translations/` | 通过，无未编译差异 |
| GitHub Actions CI | `.github/workflows/ci.yml` | 已覆盖 Node 测试、翻译检查、全新迁移、SQLite 全量 pytest、MariaDB 11.8 全量 pytest |
| 仓库卫生测试 | `tests/test_public_repo_hygiene.py` | 检查个人统计 ID、部分本机路径、已删除图片引用、CSS 图片路径 |
| 手工浏览器 E2E | `scripts/e2e_live_photo.py` | 仅覆盖 Live Photo 与图片上传，需手工执行，未接入 pytest 或 CI |

### 运行时性能基线（SQLite 内存库，15 篇已发布文章 + 5 条评论）

| 路由 | 状态码 | SQL 查询数 | 响应耗时 | 响应体积 |
| --- | --- | --- | --- | --- |
| `/` | 200 | 9 | 110.2 ms | 14.9 KB |
| `/post/1` | 200 | 12 | 45.9 ms | 21.8 KB |
| `/archive` | 200 | 7 | 11.1 ms | 12.4 KB |
| `/search?q=测试` | 200 | 8 | 15.5 ms | 14.5 KB |
| `/feed.xml` | 200 | 2 | 7.4 ms | 6.4 KB |
| `/sitemap.xml` | 200 | 3 | 3.9 ms | 1.5 KB |
| `/categories` | 200 | 8 | 8.8 ms | 9.5 KB |
| `/nonexistent-404` | 404 | 7 | 7.0 ms | 5.1 KB |

## 3. 实际发现的问题清单

| 编号 | 类别 | 问题描述与证据 | 复现方法 | 风险等级 | 建议修改 | 当前自动化验证 | 计划处理阶段 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q1 | 静态检查缺失 | 无 Ruff Lint/格式检查、无类型检查（mypy/pyright）、无统一验证入口（如 `Makefile`），CI 也未运行静态检查 | 检查 `requirements-dev.txt` 与 `.github/workflows/ci.yml` | 高 | 接入 `ruff`、`mypy`、`node --check` 与 `Makefile` 统一命令，并纳入 CI | 无 | P1 / P5 |
| Q2 | Python Lint 基线问题 | `ruff check --select E,F,B --ignore E501` 在 `app/ config.py flog.py` 检出 24 处问题：含 `app/email_handler.py:37` 裸 `except:`、重复/未使用导入（`email_handler.py:1`、`flog.py:6`）、`cli.py` 与 `admin/forms.py` 的 `B904`、`routes.py:264` 的 `B905`，以及 `app/__init__.py` 刻意位于底部的副作用导入 | `uvx ruff check --isolated --select E,F,B --ignore E501 app config.py flog.py gunicorn.conf.py` | 中 | 修复真实问题，在 `pyproject.toml` 为 `app/__init__.py` 显式配置 per-file ignores | 无 | P1 |
| Q3 | 类型检查基线问题 | `mypy` 默认模式 20 个错误（14 个为 Flask-SQLAlchemy `db.Model` 基类识别问题，6 个为 `app.static_folder` 可空、未标注缓存字典、WSGI 包装赋值）；`--check-untyped-defs` 下共 54 个错误 | `mypy app config.py flog.py` | 中 | 在 `pyproject.toml` 配置 mypy 并修复真实空值/容器类型问题 | 无 | P1 |
| Q4 | 公共页面重复 SQL 查询 | 每个公共请求重复查询 `page` 2 次、`podcast_show` 2 次：`app/__init__.py:inject_navigation_pages` 同时调用 `visible_navigation_pages()` 与 `visible_navigation_items()`（后者再次查询 `Page`），且 `navigation_pages` 未在任何模板使用；`app/podcast_routes.py:inject_podcast_link` 再次查询 `PodcastShow`，而 `podcast_nav` 同样未被任何模板使用 | 监听 SQLAlchemy `before_cursor_execute` 请求 `/`、`/archive`、`/post/1` | 中 | 导航上下文合并为单次查询源；在 `/post/<id>` 避免 `record_view` 导致的重复 `SELECT post` 与 `post.author` 懒加载 | 无 | P3 |
| Q5 | SEO 元数据不完整 | `base.html` 缺少 `<link rel="canonical">`（`/` 与 `/index` 共用首页无规范链接）、缺少 Open Graph（`og:title` / `og:description` / `og:type` / `og:url` / `og:site_name`）；`/search`、认证页、错误页及 `/admin` 缺少 `<meta name="robots" content="noindex, nofollow">`；404/500 页面未传 `title` 导致 `<title>` 退化为站点名 | 检查 `app/templates/base.html`、`app/errors.py`、`app/templates/post/search_results.html`、`app/templates/admin/base.html` | 中 | 建立统一 SEO 元数据策略（canonical、OG、robots、错误页标题）并补充自动化回归测试 | 部分（仅测 RSS/Sitemap/robots.txt/preview noindex） | P2 / P3 |
| Q6 | 浏览器自动化测试缺失 | 无纳入测试体系的 Playwright 回归测试；`article-enhancements.js`（阅读进度、PhotoSwipe 灯箱、TOC 高亮）、`code-blocks.js`（代码复制）、`site.js`（移动端导航与返回顶部）均缺少自动化测试 | 核对 `app/static/*.js`（20 个）与 `tests/*.test.js`（14 个） | 中 | 补充核心前台交互的 Playwright 真实浏览器测试及轻量 Node 回归测试 | 无 | P2 / P5 |
| Q7 | 评论处理跨模块耦合与重复 | `app/podcast_routes.py:14` 导入 `app.routes._take_comment` 私有函数；`routes.py`（`post`、`public_page`）与 `podcast_routes.py`（`podcast_episode`）三处重复评论表单预填与提交流程 | 阅读 `app/routes.py:401-443,625-635` 与 `app/podcast_routes.py:14,65-75` | 低 | 将公共评论表单/提交协调抽到 `app/comments.py` 或单一辅助入口，消除跨路由私有导入 | 已有功能测试 | P3 |
| Q8 | 后台重定向校验与局部坏味道 | `app/admin/modules.py:_comments_back` 仅用 `startswith('/admin/comments')` 未排除控制字符/反斜杠；`app/routes.py:edit_post` 520-524 行存在不可达表单赋值死代码；`posts_by_category` 存在表面注释；`app/static/style.css` 带有可执行权限位（755） | 阅读 `app/admin/modules.py:94-99`、`app/routes.py:366-374,520-525`，检查 `ls -l app/static/style.css` | 低 | 复用统一本地路径校验函数、清理死代码与表面注释、修正 `style.css` 权限 | 部分 | P3 |
| Q9 | 架构边界与仓库卫生约束不足 | `tests/test_public_repo_hygiene.py` 仅扫描 macOS 家目录前缀，未拦截 Linux 家目录路径；无自动化测试锁定“模板禁用 `|safe`”、“`Markup()` 仅限白名单模块”、“模板禁止直接 DB 查询”、“页面 SQL 查询上限” | 阅读 `tests/test_public_repo_hygiene.py` | 中 | 扩展仓库卫生测试并新增架构边界专项测试 | 部分 | P2 / P3 |
| Q10 | 迁移环境弃用告警 | `migrations/env.py:21` 调用 `db.get_engine()` 触发 6 条 `DeprecationWarning`（Flask-SQLAlchemy 3.2 将移除） | `.venv/bin/python -m pytest tests/test_migrations.py -q` | 低 | 优先使用 `db.engine` 消除弃用告警 | 已有迁移测试 | 已完成 |

## 4. 明确暂不处理项及原因

- **保持 `app/__init__.py` 模块级单例初始化模式**：当前测试与 45 个模块均围绕 `from app import app, db` 组织，改为 Application Factory 会带来大规模无收益改动，违背“不无必要重构”原则。
- **保留 `app/routes.py` 中的旧管理路由兼容层**：`/post/<id>/edit`、`/post/delete/<id>`、`/category/<id>/edit`、`/delete_category/<id>` 已有 `tests/test_legacy_admin_routes.py` 锁定向后兼容，不予删除。
- **不引入前端构建工具或框架**：原生 JS + CSS + vendored 静态资源足够简单稳定，不引入 Vite/Webpack/ESLint 复杂工具链，前端静态检查以 `node --check` + Node 测试 + Playwright 浏览器测试保证。
- **暂不调整文章列表 `h3` 标题层级**：`app/templates/post/_post.html` 样式与现有 UI 回归测试耦合，若调整需同步评估视觉样式，先保持兼容并通过 SEO 专项测试锁定核心结构约束。

## 5. 改造闭环记录

- **Q1–Q3（静态检查与类型基线）**：已建立 `pyproject.toml`、`Makefile` 统一验证入口，`ruff check`、`node --check` 与 `mypy --check-untyped-defs` 全部清零并接入 CI。
- **Q4（重复 SQL 查询）**：合并导航上下文并移除无用 `inject_podcast_link`，预加载文章作者，公共页面平均减少 2 次 SQL 查询，并由 `tests/test_engineering_invariants.py` 锁定查询预算。
- **Q5（SEO 单一事实源）**：新增 `app/seo.py`，统一 canonical URL、Open Graph、`noindex, nofollow`、404/500 标题与 feed/sitemap/robots 公共域名策略，并建立 `tests/test_seo_and_core_regression.py`。
- **Q6（浏览器与前端测试）**：补充 `code_blocks.test.js`、`site_nav.test.js` 与 Playwright 真实 Chromium 测试 `tests/test_browser_e2e.py` 并纳入 CI `browser` 任务。
- **Q7–Q9（边界与安全）**：抽取 `app/security.py:is_local_path` 与公共 `handle_comment_request`，清理死代码/表面注释/文件权限；扩展 `test_public_repo_hygiene.py` 与架构不变量测试。
- **Q10 与 `bleach` → `nh3` 迁移**：修正 `migrations/env.py` 消除全部 6 条弃用告警；将 `app/security.py` 与 `app/comment_markdown.py` 迁移至 Rust 实现的 `nh3` 清理器并从依赖中移除已停维的 `bleach`。
