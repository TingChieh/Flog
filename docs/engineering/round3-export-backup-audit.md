# Flog Round 3 审计结论与非生产演练记录

本文档记录 Flog Round 3（Markdown + 媒体批量导出/导入、R2 备份恢复演练与告警、定时发布与轻量统计）的前置代码审计结论、设计边界与非生产演练结果。

## 1. 前置审计结论

### 1.1 文章内容、Front Matter 与媒体引用现状
- **模型现状**：`Post` 表存储 `title`、`body`、`body_format`（`markdown` / `html`）、`timestamp`（UTC）、`updated_at`（UTC）、`is_published`、`comments_enabled`、`legacy_id`、`category_id`（单分类）及关联 `PostDraft` / `PostRevision`。当前无 `Post.slug` 字段与独立 `Tag` 模型（`Page` 使用 `slug`，文章路由为 `/post/<id>` 与 `/archives/<legacy_id>/`）。
- **媒体引用**：上传图片存于 `UPLOAD_FOLDER/<32hex>.(png|jpe?g|gif)`，正文以 `/files/<filename>` 引用；Live Photo 伴生视频以 `<32hex>.mp4` 存于同目录并记录在 `Image.video_filename`。`app/images.py` 已有 `USAGE_RE`、`IMAGE_NAME_RE`、文件头魔数校验与尺寸读取，可直接复用。
- **导出/导入现状**：旧版任务导出表 `task` 已在迁移 `5a1f9c0d7e42` 中移除，`app/cli.py` 无任何文章批量导出/导入命令。
- **决策**：实现 `app/content_io.py` + `flask content export` / `flask content import`。不新增无关第三方依赖（内置无 RCE 风险的 YAML front matter 序列化/解析器）；导出时成对输出文章、front matter（含 `slug`、`category`、`tags`、`published_at`、`updated_at`、`scheduled_at`、`media` 清单与 SHA-256）及 `media/`（含 Live Photo `.mp4`），正文路径重写为相对 `../media/<filename>`；导入采用“只读全量校验 → 暂存区落盘与原文件备份 → 单事务提交（异常全量回滚 DB 与上传文件）”，重复导入幂等，冲突默认拒绝直至显式 `--overwrite`。

### 1.2 R2 备份、恢复、告警与保留策略现状
- **现有实现**：`scripts/backup_r2.sh` + `deploy/systemd/flog-backup.{service,timer}`，通过环境变量注入 R2 凭据驱动 `rclone` 与 `mysqldump`，凭据来自被 `.gitignore` 忽略的 `.env.backup`（`FLOG_BACKUP_ENV` 可覆盖）。
- **审计发现缺口**：
  1. 无校验和清单（manifest / SHA-256），恢复后无法自动化核对完整性；
  2. 无可自动化运行的恢复脚本，仅有 README 手工命令提示；
  3. 无最小保留份数保护（仅按 `BACKUP_KEEP_DAYS` 删除，极端时钟漂移或连续失败可能清空历史快照）；
  4. 无失败告警链路（出错仅非零退出写 stderr，未对接现有 `ADMIN_EMAILS`/SMTP 邮件或 Webhook）。
- **决策**：保持生产默认行为（`BACKUP_STORAGE=rclone`、`BACKUP_DB_BACKEND=mysql`）完全向后兼容，新增：
  - `manifests/manifest-<stamp>.json`（SHA-256 + 字节大小 + 保留策略元数据）；
  - `BACKUP_MIN_KEEP`（默认 7）+ `BACKUP_KEEP_DAYS`（默认 30）双条件保留策略（`app/backup.py:plan_retention`）；
  - `ERR` trap 失败捕获与告警分发（`BACKUP_ALERT_CMD` 或 `flask backup alert`，复用 `app/email.py` 邮件与日志，并支持可选 `BACKUP_ALERT_WEBHOOK`）；
  - `scripts/restore_r2.sh`（强制 `--target-dir` 隔离恢复、严格校验 gzip 与全部 SHA-256，不自动覆写生产库）；
  - `BACKUP_STORAGE=local` + `BACKUP_DB_BACKEND=sqlite` 非生产演练模式，完全隔离、零生产凭据依赖。

### 1.3 发布调度现状（定时发布）
- **现有实现**：`Post` 仅有 `is_published` 与 `timestamp`，所有公开入口（`/`、`/post/<id>`、`/archive`、`/categories`、`/search`、`/feed.xml`、`/sitemap.xml`）均按 `Post.is_published.is_(True)` 过滤。无后台 worker，生产宿主机采用 `systemd timer` 模式。
- **审计结论**：个人博客写作工作流已有草稿与修订历史，但无法预约未来时间自动公开；结合现有 `systemd timer` 架构，无需引入 Celery/Redis 即可低成本、无常驻进程实现。
- **决策**：新增可空索引列 `Post.scheduled_at`（可回滚 Alembic 迁移 `d4e8f1a2b305_add_post_scheduled_at.py`），统一以 UTC 存储、按 `DISPLAY_TIMEZONE` 输入与展示；未到期的定时文章保持 `is_published=False`（零公开泄漏）；`publish_due_posts()` / `flask posts publish-due` 幂等发布到期文章；手动发布与取消发布均清理 `scheduled_at`；提供 `deploy/systemd/flog-publish.{service,timer}` 模板。

### 1.4 统计来源与查询开销现状
- **现有实现**：已有 `Post.view_count`（24h 签名 Cookie 去重原子计数）、`PostLike`（按 `post_id` 索引）和 `PostComment`（按 `post_id`/`timestamp` 索引）。后台 `/admin/` 仅有 7 次单表计数卡片，缺少累计阅读量、近 N 天互动、热门文章排行与分类阅读聚合视图。
- **决策**：新增 `app/stats.py`、`GET /admin/stats` 与 `flask stats [--top N] [--days N] [--json]`。全部使用数据库聚合（`COUNT`/`SUM`/`CASE`/`GROUP BY`）与批量 `IN` 查询，**绝不加载 `Post.body`**，单次统计严格控制在 ≤ 7 条 SQL，兼容 SQLite 与 MySQL/MariaDB，且完整覆盖空库与边界参数。

## 2. 非生产备份恢复演练步骤与验证结果

演练严格使用隔离临时目录与本地 SQLite fixture，不读取 `.env.backup`，不触碰任何生产 R2 bucket 或生产数据库：

1. **Dry-run 检查**：以 `BACKUP_STORAGE=local`、`BACKUP_DB_BACKEND=sqlite` 运行 `scripts/backup_r2.sh --dry-run`，确认仅输出计划，隔离目标目录无写入。
2. **保留策略校验**：在隔离目标预置 3 份过期旧快照（`20250101`–`20250103`），配置 `BACKUP_MIN_KEEP=2`、`BACKUP_KEEP_DAYS=30`，执行 `scripts/backup_r2.sh` 后确认保留新快照 + 最新 1 份历史快照共 2 份，其余过期快照与 `uploads-removed/` 旧目录均被清理。
3. **完整性恢复校验**：执行 `scripts/restore_r2.sh --target-dir <isolated-restore-dir>`，确认：
   - `gzip -t` 与 `manifest-<stamp>.json` 中全部文件的 SHA-256 校验通过；
   - 恢复后的 `.env` 权限为 `600` 且 SHA-256 与源文件一致；
   - 恢复后的 `uploads/`（含子目录 `audio/`）所有文件 SHA-256 与源文件一致；
   - 恢复后的 `restored.sqlite3` 通过 `PRAGMA integrity_check == ok`，文章与分类记录完全一致。
4. **篡改拦截校验**：人为篡改隔离备份中的 `uploads/photo.png` 后再次运行 `scripts/restore_r2.sh`，确认脚本检测到 `checksum mismatch` 并以非零退出码中止，不创建半完成恢复目录。
5. **失败告警校验**：指向缺失数据库路径触发 `scripts/backup_r2.sh` 失败，确认 `ERR` trap 触发告警命令并传入正确阶段（`db_dump`）、退出码与目标路径，同时保留原始非零退出码；`tests/test_backup_restore.py` 同时使用 mock 校验了邮件告警与 Webhook POST 告警链路。
