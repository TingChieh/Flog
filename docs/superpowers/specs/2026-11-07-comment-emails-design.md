# 评论邮件通知设计

日期:2026-11-07

## 背景与目标

评论改造时(见 `2026-11-06-comments-redesign-design.md`)明确推迟了邮件通知。现在密码重置邮件已经改好(单一 `send_email`、`mail_configured()`、统一的发件人、网站风格的 HTML 模板),可以在它上面加评论邮件。

本次增加四种邮件:

1. 新评论 → 站长。
2. 新评论 → 文章作者。
3. 有人回复了你的评论 → 被回复的评论者。
4. 你的评论已通过审核 → 评论者。

**约束**:评论者身份匿名(昵称 + 邮箱,邮箱没有验证过),任何人都可能填别人的邮箱,所以发给评论者的邮件必须是评论者主动勾选才发,并且可以一键退订。

**不做**:邮箱验证(确认邮件)、站点设置里的通知开关、邮件里一键通过评论、发件箱与重试。

## 1. 数据模型

`PostComment` 加两列(一个 Alembic 迁移):

| 字段 | 说明 |
| --- | --- |
| `notify_replies` | 布尔,非空,`server_default` 与模型默认值都是 `false`。评论者勾选了“邮件通知我”才为 `true` |
| `answered_id` | 可空,自引用外键 `PostComment.id`,`ondelete=SET NULL`,有索引。记录回复的是哪一条评论 |

- 现在回复只存 `parent_id`(顶层评论),回复一条回复时无法知道具体回复了谁。`answered_id` 补上这一点:回复顶层评论时等于 `parent_id`,回复某条回复时指向那条回复。
- 已有评论的 `notify_replies` 都是 `false`,所以升级后不会有人突然收到邮件。
- `submit_comment` 增加 `notify_replies` 参数并写入 `answered_id`。

评论表单(`PostCommentForm`)加布尔字段 `notify`,标签“有回复或审核结果时,用邮件通知我”,默认不勾,放在姓名、邮箱之后。站长在后台回复(`reply_comment`)不涉及通知选项,`notify_replies` 为 `false`。

## 2. 邮件模块 `app/comment_mail.py`

只负责“发给谁、发什么”,不碰数据库事务。入口三个,都在 `db.session.commit()` 之后调用:

- `notify_comment_published(comment)`:评论已发布时调用(见下文触发点)。
- `notify_comment_pending(comment)`:评论进入待审核时调用。
- `notify_comments_approved(comments)`:后台把评论从待审核改为已发布后调用。

所有入口开头先 `mail_configured()`,没配置就静默返回。发送沿用 `send_email`(后台线程,失败写日志),每个收件人单独一封,避免互相看到地址。邮件里的链接用 `url_for(..., _external=True)`。

### 谁收到什么

| 邮件 | 时机 | 收件人 | 内容 |
| --- | --- | --- | --- |
| 新评论(已发布) | 评论一提交就发布 | 站长 + 文章作者 | 文章标题、评论者姓名和邮箱、评论正文、“查看评论”链接 `post#comment-id` |
| 新评论(待审核) | 评论进入待审核 | 站长 + 文章作者 | 同上,按钮是“前往审核”,指向 `/admin/comments?status=pending` |
| 有人回复了你 | 回复变为已发布 | 被回复的那条评论(`answered`)的评论者 | 回复者姓名、回复正文、“查看回复”链接、退订链接 |
| 评论已通过审核 | 待审核评论被通过 | 该评论的评论者 | 文章标题、评论正文、“查看评论”链接、退订链接 |

- **站长**:`ADMIN_EMAILS`(`app.config['ADMINS']`)。**文章作者**:`post.author.email`;页面评论没有作者,只发站长。两者合并后按小写地址去重。
- **去掉评论者自己**:收件人里与评论者邮箱相同的地址不发。站长自己评论或回复,不会通知自己。
- 待审核邮件只发这一封;评论通过后,站长和作者不再收到“已发布”的新评论邮件(他们已经知道了)。
- **回复通知的条件**:`answered` 存在、`answered.notify_replies` 为 `true`、`answered.email` 与回复者邮箱不同。对待审核的回复,等到它被通过时才发。
- **审核通过通知的条件**:该评论 `notify_replies` 为 `true`。如果它本身是一条回复,通过时还要走一次“有人回复了你”。
- 站长在后台“通过”不是评论者自己的操作,所以通过通知照常发;站长自己写的回复一提交就发布,走“有人回复了你”。

### 触发点

| 位置 | 调用 |
| --- | --- |
| `routes._take_comment`,commit 后,结果为已发布 | `notify_comment_published` |
| `routes._take_comment`,commit 后,结果为待审核 | `notify_comment_pending` |
| `admin.modules.reply_comment`,commit 后 | `notify_comment_published`(站长回复,自动发布) |
| `admin.modules.approve_comment` / `bulk_comments` 的 approve 分支,commit 后 | `notify_comments_approved`(只传本次由待审核变为已发布的评论) |

被丢弃的评论(蜜罐、太快,`DROPPED`)不发任何邮件。批量通过时对已经是已发布的评论不重复通知。

## 3. 退订

- 退订令牌:`URLSafeTimedSerializer(SECRET_KEY, salt='comment-unsubscribe')` 签名,内容是小写邮箱,不设过期(退订链接要长期有效)。
- 路由 `GET /comments/unsubscribe/<token>`:令牌有效时显示确认页(“不再给 xxx 发评论邮件?”,一个“确认退订”按钮);无效时 404。页面用公开页的表单外壳 `form-shell public-page`,和重置密码页一致。
- 路由 `POST /comments/unsubscribe/<token>`:带 CSRF,把所有 `lower(email)` 等于该邮箱的评论的 `notify_replies` 置为 `false`,flash 提示后跳转首页。**先确认再生效**,是为了防止邮件安全扫描自动打开链接就把人退订了。
- 邮件头加 `List-Unsubscribe`(指向确认页链接)。因为确认页要点按钮,不声明 `List-Unsubscribe-Post`。
- 退订按邮箱生效而不是单条评论;之后同一邮箱再次勾选通知,视为重新同意。
- 发给站长和文章作者的邮件不带退订链接。

## 4. 邮件样式

把现在 `app/templates/email/reset_password.html` 的骨架(暖灰底、纸色卡片、衬线字体、深色按钮、深色模式)抽成 `app/templates/email/base.html`,留出标题、正文和页脚(退订链接)几个块。密码重置和三种评论邮件都继承它。每种邮件各有一个 `.html` 和一个 `.txt`。

- 邮件主题:`[网站名] 新评论:文章标题`、`[网站名] 新评论待审核:文章标题`、`[网站名] 有人回复了你的评论`、`[网站名] 你的评论已通过审核`。
- 评论正文在邮件里以纯文本显示(转义,保留换行),不渲染 Markdown,避免邮件里出现不可信 HTML。长评论截断到 300 字,末尾“……”,完整内容在链接里。
- 全部简体中文,和网站其他文案一致。

## 5. 错误处理

- 邮件未配置、收件人为空、不满足条件:静默跳过。
- 发信失败:`send_async_email` 已经记录日志,不影响评论提交、审核和后台回复。
- 邮件模块自己的异常(例如渲染出错)不能让已经 commit 的评论请求变成 500:入口外层捕获并记录日志。

## 6. 测试

沿用 `tests/test_password_reset_email.py` 里的 `outbox` 夹具思路(配置邮件、抑制真实发送、后台线程改为同步、用 `email_dispatched` 收集),建议把它提到 `tests/conftest.py`,密码重置和评论邮件测试共用。

- **新评论**:已发布时站长和作者各收到一封;作者就是站长时只收到一封;待审核时收到“待审核”版本,通过后不再重复收到;页面评论只发站长;评论者自己不会收到。
- **回复通知**:被回复者勾选通知时收到,没勾选不收;回复自己不通知;回复一条回复时通知的是那条回复的评论者;待审核的回复在通过时才通知;站长后台回复触发通知。
- **审核通过**:勾选通知的评论者收到,没勾选不收;批量通过只通知本次状态变化的评论;通过一条待审核的回复时,评论者收到通过通知、被回复者收到回复通知。
- **不发信**:`DROPPED` 的评论、邮件未配置时都不发,且评论提交和审核都正常。
- **退订**:确认页用 GET 显示、不改数据;POST 才把该邮箱所有评论的 `notify_replies` 置为 `false`;令牌无效返回 404;大小写不同的邮箱一并退订;退订后不再收到通知。
- **表单**:勾选框默认不勾;勾选后评论的 `notify_replies` 为 `true`。
- **迁移**:升级后两列存在、已有评论 `notify_replies` 为 `false`、`answered_id` 为 `NULL`;降级后两列被删除(沿用 `tests/test_migrations.py` 的写法)。
- **模板**:每种邮件的 HTML 与纯文本都渲染成功,评论正文里的 HTML 被转义,评论邮件带退订链接,站长邮件不带。

## 7. 影响范围

- 新增:`app/comment_mail.py`、`app/templates/email/base.html` 与各评论邮件模板、一个迁移、退订页模板、对应测试。
- 修改:`app/models.py`(两列)、`app/comments.py`(`notify_replies`、`answered_id`)、`app/forms.py`(`notify` 字段)、`app/routes.py`(`_take_comment` 调用通知、退订路由)、`app/admin/modules.py`(回复与通过后调用通知)、`app/templates/_comments.html`(勾选框)、`app/templates/email/reset_password.*`(改为继承基础模板)、`README.md`(功能说明)、`tests/conftest.py`。
