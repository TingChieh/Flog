# 后台“邮件”页设计

日期:2026-11-07

## 背景与目标

博客的邮件全部走 Resend:发信用 SMTP,`admin@aisaka.cc`、`tingchieh@aisaka.cc` 的收信用 Resend 的 Inboxes。管理员想在博客后台里看到邮件的收和发,不必每次切到 Resend 控制台。

做一个**只读**的后台“邮件”页:列出 Resend 上已发送和已收到的邮件,点进去看详情。不新增任何服务,不装 Docker,不自托管邮箱软件。

**不做**:渲染邮件 HTML、下载附件、搜索、把邮件存进本地数据库。(写信和回复见第 7 节,后来补充。)

调研过的开源方案(inboxes、Mailstead、selfmail)都很年轻(星数 0 到 11),需要同样的完整权限密钥,还要处理不可信邮件内容和接收回调,因此不采用。

## 1. 配置与密钥

- 新增环境变量 `RESEND_API_KEY`,可选,默认空。`config.py` 读入 `Config.RESEND_API_KEY`(去掉首尾空白)。
- 读取列表接口要 Resend 的 `full_access` 密钥(`sending_access` 读不了),Resend 没有只读级别。因此:
  - 密钥只写在服务器 `.env`,不进仓库,不经聊天。
  - 建议单独建一把名为 `flog-admin` 的密钥,不与博客发信用的 SMTP 密钥共用,出问题可单独吊销。
  - 代码里**只发 GET 请求**,测试里验证。
- 没配置时,邮件页只显示配置说明,其他功能不受影响。

## 2. Resend 接口封装 `app/resend_client.py`

只用标准库(`urllib`),不加依赖。

| 函数 | 请求 |
| --- | --- |
| `list_sent(after=None)` | `GET /emails?limit=20[&after=<id>]` |
| `list_received(after=None)` | `GET /emails/receiving?limit=20[&after=<id>]` |
| `get_sent(email_id)` | `GET /emails/{id}` |
| `get_received(email_id)` | `GET /emails/receiving/{id}` |

- 请求头:`Authorization: Bearer <key>`、`Accept: application/json`、自定义 `User-Agent`(Resend 前面的网关会拒绝默认的 Python UA)。超时 8 秒。
- 列表返回 `MailPage(items, has_more)`;每封邮件归一为 `MailItem`:`id`、`sender`、`to`(列表)、`subject`、`created_at`(带时区的 `datetime` 或 `None`)、`status`(已发送才有)。缺字段一律给默认值,不抛 `KeyError`。
- 详情在 `MailItem` 之上再带:`text`(纯文本正文)、`cc`、`bcc`、`reply_to`、`attachments`(文件名、类型、大小)、`authentication`(SPF、DKIM、DMARC,仅已收到)。
- 正文:有 `text` 用 `text`;只有 `html` 时用 `app.search.plain_text` 提取文字。**从不输出原始 HTML。**
- 邮件 ID 必须是 UUID 格式,否则不发请求(防止拼出别的路径)。
- 错误统一抛 `ResendError(message)`,`message` 是给管理员看的中文提示:
  - 401、403:“Resend 拒绝了密钥:需要 Full access 权限的密钥。”
  - 429:“请求太频繁,稍后再试。”
  - 404:`NotFound`(子类),详情页转为 404。
  - 其他状态:“Resend 返回了错误(HTTP xxx)。”
  - 网络错误、超时、返回内容不是 JSON:“无法连接 Resend。”
  - 未配置:`NotConfigured`(子类)。
- 进程内缓存 20 秒(按完整 URL),最多 64 条,超出时丢弃最旧的,避免连续翻页重复请求。

## 3. 页面 `app/admin/mail.py`

只有管理员能访问(`@login_required` 加 `@admin_required`),后台导航“网站管理”组里加“邮件”。

- `GET /admin/mail?box=sent|received&after=<id>`:列表。`box` 默认 `sent`,取值不合法按 `sent`。
  - 顶部两个标签“已发送 / 已收到”,沿用评论页的 `.admin-filters` 样式。
  - 每行:时间(显示时区,`%Y-%m-%d %H:%M`)、发件人、收件人、主题;已发送再显示状态;链接到详情。
  - 翻页:Resend 返回 `has_more` 时显示“较早的邮件”,链接带 `after=<本页最后一封的 id>`;有 `after` 时再显示“回到最新”。
  - 空列表显示“还没有邮件”。
- `GET /admin/mail/<box>/<email_id>`:详情。`box` 不是 `sent` 或 `received`、或 ID 格式不对、或 Resend 返回 404,都返回 404。
  - 显示发件人、收件人、抄送、密送、回复地址、主题、时间、状态;已收到的再显示 SPF、DKIM、DMARC 和附件列表。
  - 正文放在 `<pre>` 里,`white-space: pre-wrap`,Jinja 自动转义。
  - “在 Resend 中打开”链接:`https://resend.com/emails/<id>`(已发送)或 `https://resend.com/emails/receiving/<id>`(已收到),`rel="noopener noreferrer"`。
- 任何 `ResendError`:页面正常返回 200,在 `.admin-notice` 里显示 `message`,不报 500。`NotConfigured`:显示“还没有配置 RESEND_API_KEY”和一两句配置说明。

## 4. 已知不确定点

Resend 文档里“Inboxes 收件箱”和“域名收信”是两套东西。收件箱里的邮件是否出现在 `GET /emails/receiving` 里,文档没说明。先按文档实现;拿到真实密钥后验证,如果看不到收件箱的邮件,再改读 Inboxes 的接口。

## 5. 测试(`tests/test_admin_mail.py`)

用假的 `urllib.request.urlopen` 记录请求并返回预设响应,不访问网络。

- 没配置:管理员看到说明,不发任何请求。
- 权限:未登录跳转登录;普通用户 403。
- 已发送列表:渲染发件人、收件人、主题、状态,主题里的 HTML 被转义,时间转成显示时区。
- 已收到列表:走 `/emails/receiving`;`box` 不合法时按已发送。
- 翻页:`has_more` 时出现带 `after` 的链接,且 `after` 被传给接口;有 `after` 时出现“回到最新”。
- 详情(已发送、已收到):正文转义;只有 HTML 的邮件显示提取出的文字,页面里没有原始 `<script>`;已收到的显示认证结果和附件名。
- 非法:ID 格式不对、`box` 不合法、接口返回 404,都是 404,且前两种不发请求。
- 接口错误:401、429、网络错误、返回非 JSON 时页面是 200 并显示对应提示。
- 所有请求都是 GET,带 `Bearer` 和 `User-Agent`,主机是 `api.resend.com`。
- 缓存:20 秒内相同列表只请求一次。
- 配置:`RESEND_API_KEY` 在 `.env.example` 和 README 里有说明;`config` 读取并去空白。

## 6. 影响范围

- 新增:`app/resend_client.py`、`app/admin/mail.py`、`app/templates/admin/mail/list.html`、`app/templates/admin/mail/detail.html`、`tests/test_admin_mail.py`。
- 修改:`config.py`、`app/admin/__init__.py`(导入新模块)、`app/templates/admin/base.html`(导航)、`app/static/style.css`(正文样式)、`.env.example`、`README.md`、`tests/test_env_config_removed.py`(登记新设置)。

## 7. 写邮件与回复(补充)

管理员希望在后台里直接用 `tingchieh@aisaka.cc`、`admin@aisaka.cc` 写信,所以在只读页之上加“写邮件”和“回复”。复用博客已有的 SMTP 发信(经 Resend),不需要新密钥。

- **配置**:新增 `MAIL_SENDERS`(逗号分隔,可选),与 `MAIL_FROM` 一起组成发件人白名单(`app.email.mail_senders()`)。没设置时只有 `MAIL_FROM`。
- **页面**:`GET/POST /admin/mail/compose`;列表页右上角“写邮件”;已收到邮件详情页的“回复”按钮(`?reply=<id>`)。邮件发送没配置时页面只显示说明,不显示表单。
- **字段**:发件人(下拉,服务端按白名单校验)、收件人(逗号、分号或空白分隔,最多 10 个,逐个用 `email_validator` 校验)、主题(单行,最多 200 字)、正文(纯文本,最多 20000 字)。不支持附件、HTML、抄送、密送。
- **回复预填**:收件人取 `reply_to` 的第一个,否则取发件人;主题加 `Re: `(已有则不重复);发件人取原邮件的收件地址(在白名单内才用);正文引用原文(最多 4000 字,每行加 `> `);有 `message_id` 就填入 `In-Reply-To` 和 `References`。预填失败(例如密钥不对)时显示错误,表单照常可用。
- **线程头安全**:`In-Reply-To`、`References` 由浏览器隐藏字段带回,发送前只接受形如 `<id@host>` 的单个或最多 10 个标识(空格分隔),其他一律丢弃,不放进邮件头。
- **发送**:同步发送。失败时在表单里显示“发送失败”,原因只写服务器日志,不回显。成功后清空列表缓存,闪现“邮件已发送。”并跳到“已发送”列表。
- **测试**:`tests/test_admin_mail_compose.py`,覆盖权限、发件人白名单、收件人和主题校验、头注入、数量上限、发送失败不泄漏、回复预填、线程头、按钮显示条件、配置文档。
