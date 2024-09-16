-- phpMyAdmin SQL Dump
-- version 5.2.1deb3
-- https://www.phpmyadmin.net/
--
-- 主机： localhost:3306
-- 生成日期： 2024-09-16 07:06:19
-- 服务器版本： 11.4.3-MariaDB-1
-- PHP 版本： 8.2.23

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- 数据库： `flog`
--

-- --------------------------------------------------------

--
-- 表的结构 `about`
--

CREATE TABLE `about` (
  `id` int(11) NOT NULL,
  `body` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `about`
--

INSERT INTO `about` (`id`, `body`) VALUES
(1, '<p><strong>这里是我的介绍啊</strong></p>\r\n');

-- --------------------------------------------------------

--
-- 表的结构 `alembic_version`
--

CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `alembic_version`
--

INSERT INTO `alembic_version` (`version_num`) VALUES
('80f877602ba0');

-- --------------------------------------------------------

--
-- 表的结构 `category`
--

CREATE TABLE `category` (
  `id` int(11) NOT NULL,
  `name` varchar(120) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `category`
--

INSERT INTO `category` (`id`, `name`) VALUES
(3, '学习'),
(2, '教程'),
(1, '默认');

-- --------------------------------------------------------

--
-- 表的结构 `comment`
--

CREATE TABLE `comment` (
  `id` int(11) NOT NULL,
  `email` varchar(120) NOT NULL,
  `name` varchar(64) NOT NULL,
  `body` varchar(240) NOT NULL,
  `timestamp` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `comment`
--

INSERT INTO `comment` (`id`, `email`, `name`, `body`, `timestamp`) VALUES
(6, 'tingchieh@foxmail.com', 'TingChieh', '<p><strong>这是我的一条留言</strong></p>\r\n', '2024-09-15 16:05:03');

-- --------------------------------------------------------

--
-- 表的结构 `followers`
--

CREATE TABLE `followers` (
  `follower_id` int(11) NOT NULL,
  `followed_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `followers`
--

INSERT INTO `followers` (`follower_id`, `followed_id`) VALUES
(2, 1),
(3, 1),
(1, 2);

-- --------------------------------------------------------

--
-- 表的结构 `link`
--

CREATE TABLE `link` (
  `id` int(11) NOT NULL,
  `name` varchar(64) NOT NULL,
  `email` varchar(128) NOT NULL,
  `url` varchar(255) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `text` varchar(128) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `link`
--

INSERT INTO `link` (`id`, `name`, `email`, `url`, `created_at`, `text`) VALUES
(1, 'TingChieh\'s Blog', 'tingchieh@foxmail.com', 'https://blog.aisaka.cc', '2024-09-12 00:54:08', '什么都不会的 21 岁学生一个'),
(2, 'Yzqzss', 'yzqzss@yandex.com', 'https://blog.othing.xyz/', NULL, '我想冻住-- 我的所见，所听，所想 他人所写，所创造 自然所变，所灭 冻住世界，冻住时间，冻住本就存在的一切！'),
(7, '牧云风柳', 'muyunfengliu@gmail.com', 'https://www.muyunfengliu.com/', '2024-09-15 15:32:23', '\"That\'s a secret between you and me…\" | Final Fantasy VIII'),
(8, 'Zankyo.', 'kot4ri@gmail.com', 'https://zankyo.cc/links/', '2024-09-15 15:34:54', '未来のかたちに');

-- --------------------------------------------------------

--
-- 表的结构 `message`
--

CREATE TABLE `message` (
  `id` int(11) NOT NULL,
  `sender_id` int(11) NOT NULL,
  `recipient_id` int(11) NOT NULL,
  `body` varchar(140) NOT NULL,
  `timestamp` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `message`
--

INSERT INTO `message` (`id`, `sender_id`, `recipient_id`, `body`, `timestamp`) VALUES
(1, 1, 2, '你好啊', '2024-09-11 02:59:17');

-- --------------------------------------------------------

--
-- 表的结构 `movie`
--

CREATE TABLE `movie` (
  `id` int(11) NOT NULL,
  `title` varchar(60) NOT NULL,
  `year` varchar(5) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `movie`
--

INSERT INTO `movie` (`id`, `title`, `year`) VALUES
(4, '你好世界', '2024');

-- --------------------------------------------------------

--
-- 表的结构 `notification`
--

CREATE TABLE `notification` (
  `id` int(11) NOT NULL,
  `name` varchar(128) NOT NULL,
  `user_id` int(11) NOT NULL,
  `timestamp` float NOT NULL,
  `payload_json` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `notification`
--

INSERT INTO `notification` (`id`, `name`, `user_id`, `timestamp`, `payload_json`) VALUES
(19, 'task_progress', 1, 1726040000, '{\"task_id\": \"aca48135-7467-4540-8db0-9284342d2746\", \"progress\": 100}'),
(67, 'unread_message_count', 1, 1726420000, '0'),
(72, 'unread_message_count', 2, 1726450000, '0');

-- --------------------------------------------------------

--
-- 表的结构 `post`
--

CREATE TABLE `post` (
  `id` int(11) NOT NULL,
  `body` text NOT NULL,
  `timestamp` datetime NOT NULL,
  `user_id` int(11) NOT NULL,
  `language` varchar(5) DEFAULT NULL,
  `category_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `post`
--

INSERT INTO `post` (`id`, `body`, `timestamp`, `user_id`, `language`, `category_id`) VALUES
(2, '<p>hello</p>\r\n', '2024-07-03 07:09:47', 2, NULL, 1),
(29, '<h1><strong>[Markdown+Typora/VSCode 超全教程] 给大一新生安利的文本神器</strong></h1>\r\n\r\n<h2><strong>😂 简要介绍</strong></h2>\r\n\r\n<p><strong>Markdown</strong> 是一种轻量型标记语言, 是一种语法. 以 <code>.md</code> 结尾的文本文件就是 Markdown 文件. 相较于 <strong>Word</strong>, 它更加像是 <strong>HTML</strong> 语言或是 $\\LaTeX$, 并不是最淳朴的那种&quot;所见即所得&quot;. 它处处透露着一种极简主义. 高效简洁清晰的同时, 又很简单. 看起来舒服, 语法简单, 尤其在处理纯文本上有很大的优势.</p>\r\n\r\n<p>它相较于 <strong>Word</strong>, 兼容性非常高, 可以跨平台使用, 不用担心奇奇怪怪的版本兼容问题. 同时, 有许多网站都支持或正在使用 <strong>Markdown</strong> 语法. 如 <strong>Github</strong> (等一系列代码托管平台), StackOverflow(等答疑平台), 简书, 语雀 (等一系列笔记平台).</p>\r\n\r\n<h2><strong>📐 实际应用</strong></h2>\r\n\r\n<p>所有要写文本的时候都可以用上 <strong>Markdown</strong>!</p>\r\n\r\n<p>它可以让你不再纠结什么字体, 什么样式, 什么排版. 而且逻辑清晰, 层次分明.</p>\r\n\r\n<p>像我大一的时候就用 Markdown 来写各种笔记, 演讲稿, 课程论文, 实验报告, 代码的 <code>README.md</code> ... 包括本教程文档.</p>\r\n\r\n<h2><strong>🍴 工具</strong></h2>\r\n\r\n<p>Markdown 只是一种语法. 那么用来写 Markdown 的文本编辑器呢? 我推荐的是 <strong>Typora</strong> 或者 <strong>VS Code</strong></p>\r\n\r\n<h3><strong>Typora</strong></h3>\r\n\r\n<p>Typora 应该是被广泛用于写 Markdown 的文本软件, 就和 Markdown 语法一样高效. 而且它还有很实用的扩展语法与自定义样式的功能. 其能将 <code>.md</code> 导出成多种文件, 如 <code>.pdf</code>, <code>.html</code>, <code>.docx</code> (没想到吧, 能导出到 Word)</p>\r\n\r\n<p>但是现在 Typora 已经发布正式版并且变为收费软件. 中文官网在此 <a href=\"https://typoraio.cn/\">Typora 官方中文站 </a>.</p>\r\n\r\n<p>我当然是推荐大家都用正版啦. 不过价格是永久版￥89, 好在可以用在3台设备上. 如果和你的两位同学/舍友均摊一下, 每人就只要￥30, 和一张游戏月卡差不多.</p>\r\n\r\n<p>至于盗版以及破解方法<a href=\"https://www.only4.work/blog/?id=379\">在此随便找一种改注册表时间方法的</a><del>不介绍(还挺多的其实)</del>.</p>\r\n\r\n<p><del>还有一种免费白嫖的方法就是安装测试版/Beta版. 官网有历史版本的下载链接 <a href=\"https://typoraio.cn/windows/dev_release.html\">Typora 历史版本下载页</a></del></p>\r\n\r\n<p>白嫖Beta版已经寄了, 要么支持正版要么去学习一下破解方法吧 (还是忍不住啦, 看上面的链接👆)</p>\r\n\r\n<h3><strong>VS Code</strong></h3>\r\n\r\n<p>这是微软家的开源文本编辑器, 理论上来说所有代码, 语言, 都可以用 VS Code 来写, 同样是非常的简洁好用. 在下载插件 <strong>Markdown All in One</strong> 后对 Markdown 的基础支持也是非常的好. 若在 VS Code 下载 Markdown 各种附加扩展, 就能获得比 Typora 更加丰富的扩展语法与操作.</p>\r\n\r\n<h3><strong>其他</strong></h3>\r\n\r\n<p>大部分IDE, 像 Jetbrain 的全家桶里应该每一款, 都支持 Markdown 语法, 在此不多赘述.</p>\r\n\r\n<p>本文档主要使用 Typora 进行演示, 同时会介绍许多 Typora 所包含的扩展语法.</p>\r\n\r\n<h2><strong>🍭 基础教程</strong></h2>\r\n\r\n<p>当有多种标记方法时我会倾向其中一种.</p>\r\n\r\n<p>标题有 <code>*</code> 表示该为扩展语法, 仅在 Typora 或 添加了扩展的 VS Code <strong>本地生效</strong>, 在大多数平台上<strong>并不认可</strong>.</p>\r\n\r\n<h3><strong>0. 写 Markdown 的第零步</strong></h3>\r\n\r\n<p>我们写文本的时候大多写的是中文, 可是输入法在输中文时使用的标点为全角标点, 如 <code>，。？！（）【】：；&ldquo;&rdquo;</code>. 这些标点是不被 Markdown 所认可的, 也是无法转义的.</p>\r\n\r\n<p>我建议大家写 Markdown 的时候都用半角标点, 即英文标点, 如 <code>,.?!()[]:;&quot;&quot;</code>. 且每个半角标点在文本使用时加上后置空格, 符合英文标点的书写规范, 也更加美观.</p>\r\n\r\n<p>以微软自带输入法举例, 在使用中文输入法时按下 <code>Ctrl</code> + <code>.(这是个句号)</code>, 切换标点的全角与半角. 这样即可中文输入+半角标点.</p>\r\n\r\n<h3><strong>1. 标题 [数个 &quot;#&quot; + 空格 前置]</strong></h3>\r\n\r\n<pre>\r\n# 一级标题\r\n## 二级标题\r\n### 三级标题\r\n#### 四级标题\r\n##### 五级标题\r\n###### 六级标题</pre>\r\n\r\n<p>标题会在目录与大纲分级显示, 可以跳转.</p>\r\n\r\n<p>在 Typora 中建议开启 <code>严格模式</code>, 即不应为 <code>#标题</code>, 应为 <code># 标题</code>.</p>\r\n\r\n<p>应该要手动补上空格, 使得 Markdown 语法在其他文本编辑器上兼容.</p>\r\n\r\n<h3><strong>2. 强调 [用 &quot;**&quot; 或 &quot;__&quot; 包围]</strong></h3>\r\n\r\n<pre>\r\n**欢迎报考南京大学!** (我喜欢用这种)\r\n__欢迎报考南京大学!__</pre>\r\n\r\n<p>或者选中想要强调的文字按下 <code>Ctrl</code> + <code>B</code>.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p><strong>欢迎报考南京大学!</strong></p>\r\n\r\n<h3><strong>3. 斜体 [用 &quot;*&quot; 或 &quot;_&quot; 包围]</strong></h3>\r\n\r\n<pre>\r\n*欢迎大佬来浇浇我各种知识* (我喜欢用这种)\r\n_欢迎大佬来浇浇我各种知识_</pre>\r\n\r\n<p>或者选中想要强调的文字按下 <code>Ctrl</code> + <code>I</code>.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p><em>欢迎大佬来浇浇我各种知识</em></p>\r\n\r\n<p>(P.S. <em><strong>斜体并强调</strong></em> [用 &quot;***&quot; 或 &quot;___&quot; 包围])</p>\r\n\r\n<h3><strong>4. 删除线 [用 &quot;~~&quot; 包围]</strong></h3>\r\n\r\n<pre>\r\n~~我宣布个事儿, 我是Sabiyary!~~</pre>\r\n\r\n<p>E.G.</p>\r\n\r\n<p><del>我宣布个事儿, 我是Sabiyary!</del></p>\r\n\r\n<h3><strong>5. *高亮 [用 &quot;==&quot; 包围]</strong></h3>\r\n\r\n<p><strong>(注意: 此为扩展语法)</strong></p>\r\n\r\n<pre>\r\n==我喜欢黄色, 也喜欢绿色==</pre>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>==我喜欢黄色, 也喜欢绿色==</p>\r\n\r\n<h3><strong>6. 代码 [用 &quot;`&quot; 包围]</strong></h3>\r\n\r\n<pre>\r\n`sudo rm -rf /*`</pre>\r\n\r\n<p>E.G.</p>\r\n\r\n<p><code>sudo rm -rf /*</code> (没事别乱敲这个! )</p>\r\n\r\n<p><del>&quot;请输入管理员密码: (闪烁的光标)&quot;</del></p>\r\n\r\n<h3><strong>7. 代码块 [按三个 &quot;`&quot; 并敲回车]</strong></h3>\r\n\r\n<pre>\r\n```\r\n// 这里就可以开始输入你要的代码了\r\n#include &lt;stdio.h&gt;\r\nint mian() {\r\n &nbsp; &nbsp;print（&ldquo;Hello, world!\\n&quot;）;\r\n &nbsp; &nbsp;retrun O;\r\n}\r\n``` // (这三个&quot;`&quot;文本编辑器会帮你自动补全 一般不用手动输)</pre>\r\n\r\n<p>(我之前都是用这个来展示各种语法的, 应该不用举例了吧)</p>\r\n\r\n<p>要想显示行数的话, 一般要在 Typora 的设置里勾上这个显示行数的选项.</p>\r\n\r\n<p>代码块里可以选择语言, 其会根据语言来自动高亮各个语句. 在选择语言后, <code>```</code> 会变为 <code>````</code> + <code>对应语言</code>.</p>\r\n\r\n<h3><strong>8. 引用 [&quot;&gt;&quot; + 空格 前置]</strong></h3>\r\n\r\n<pre>\r\n&gt; 24岁, 是学生.\r\n&gt; &gt; 学生特有的无处不在(恼)</pre>\r\n\r\n<p>引用是可以嵌套的!</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<blockquote>\r\n<p>24岁, 是学生.</p>\r\n\r\n<blockquote>\r\n<p>学生特有的无处不在(恼)</p>\r\n</blockquote>\r\n</blockquote>\r\n\r\n<h3><strong>9. 无序列表 [&quot;-&quot; 或 &quot;+&quot; + 空格 前置]</strong></h3>\r\n\r\n<pre>\r\n- 一颗是枣树 (我喜欢用这种)\r\n+ 另一颗还是枣树\r\n* (其实这种也可以, 不过由于在 Typora 中很难单个输入, 故不常用)</pre>\r\n\r\n<p>三种前置符都可以, 敲回车会自动补全, 可在 Typora 设置中调整补全的符号, 敲回车后按下 <code>Tab</code> 会缩进一级.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<ul>\r\n	<li>\r\n	<p>一颗是枣树</p>\r\n	</li>\r\n	<li>\r\n	<p>另一颗还是枣树</p>\r\n	</li>\r\n</ul>\r\n\r\n<h3><strong>10. 有序列表 [数字 + &quot;.&quot; + 空格 前置]</strong></h3>\r\n\r\n<pre>\r\n我来这里就为了三件事:\r\n1. 公平\r\n2. 公平\r\n3. 还是tm的公平!</pre>\r\n\r\n<p>敲回车会自动补全, 敲回车后按下 <code>Tab</code> 会缩进一级.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>我来这里就为了三件事:</p>\r\n\r\n<ol>\r\n	<li>\r\n	<p>公平</p>\r\n	</li>\r\n	<li>\r\n	<p>公平</p>\r\n	</li>\r\n	<li>\r\n	<p>还是tm的公平!</p>\r\n	</li>\r\n</ol>\r\n\r\n<h3><strong>11. *上标 [用 &quot;^&quot; 包围]</strong></h3>\r\n\r\n<p><strong>(注意: 此为扩展语法)</strong></p>\r\n\r\n<pre>\r\nC语言中int的上限是 2^31^ - 1 = 2147483647</pre>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>C语言中 <code>int</code> 的上限是 2^31^ - 1 = 2147483647</p>\r\n\r\n<h3><strong>12. *下标 [用 &quot;~&quot; 包围]</strong></h3>\r\n\r\n<p><strong>(注意: 此为扩展语法)</strong></p>\r\n\r\n<pre>\r\nH~2~O 是剧毒的!</pre>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>H~2~O 是剧毒的!</p>\r\n\r\n<h3><strong>13. *注释 [&quot;[^]&quot; 后置]</strong></h3>\r\n\r\n<p><strong>(注意: 此为扩展语法)</strong></p>\r\n\r\n<pre>\r\n&gt; 今日我们相聚于此, 是为了学习 Markdown 的使用, 它的教程对于全体「观众」而言, 值得足足两个硬币的支持鼓励![^1]\r\n\r\n[^1]: 沃兹&middot;基&middot;硕德 改编自「公鸡」普契涅拉.</pre>\r\n\r\n<p>需要在文末写上注释对应的内容</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<blockquote>\r\n<p>今日我们相聚于此, 是为了学习 Markdown 的使用, 它的教程对于全体「观众」而言, 值得足足两个硬币的支持鼓励!1</p>\r\n</blockquote>\r\n\r\n<p>[<strong>1</strong>] &nbsp;沃兹&middot;基&middot;硕德 改编自「公鸡」普契涅拉.</p>\r\n\r\n<h3><strong>14. 链接 [常用 &quot;[ ]&quot; + &quot;( )&quot; 分别包围文本与链接]</strong></h3>\r\n\r\n<p><strong>(注意: 文内跳转为扩展用法)</strong></p>\r\n\r\n<pre>\r\n[来看看我贫瘠的仓库罢](https://github.com/Sakiyary)\r\n[基础教程: 12. 下标](#12. 下标 [用 &quot;~&quot; 包围])</pre>\r\n\r\n<p>支持网页链接与文内跳转, 按住 <code>Ctrl</code> 并 <code>单击鼠标左键</code> 即可跳转.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p><a href=\"https://github.com/Sakiyary\">来看看我贫瘠的仓库罢</a></p>\r\n\r\n<p><a href=\"#12.%20%E4%B8%8B%E6%A0%87%20%5B%E7%94%A8%20%22~%22%20%E5%8C%85%E5%9B%B4%5D\">基础教程: 12. 下标</a></p>\r\n\r\n<h3><strong>15. 任务列表 [&quot;- [ ]&quot; + 空格 前置]</strong></h3>\r\n\r\n<pre>\r\nTodoList:\r\n- [ ] 刷B站\r\n- [ ] 写代码\r\n- [x] 起床</pre>\r\n\r\n<p>用 <code>x</code> 代替 <code>[ ]</code> 中的空格来勾选任务列表. 在 Typora 中可以直接用鼠标左键单击勾选框.</p>\r\n\r\n<p>E.G. TodoList:</p>\r\n\r\n<ul>\r\n	<li>刷B站</li>\r\n	<li>写代码</li>\r\n	<li>起床</li>\r\n</ul>\r\n\r\n<h3><strong>16. 表格 [用 &quot;|&quot; 绘制表格边框]</strong></h3>\r\n\r\n<pre>\r\n| 学号 | 姓名  | 年龄 |\r\n| :--- | :---: | ---: | (引号的位置代表着 左对齐, 居中, 右对齐)\r\n|114514|田所|24|\r\n|1919810|浩三|25|</pre>\r\n\r\n<p>第一行为表头, 并由第二行分割线决定对齐方式与长度, 第三行及之后即表格数据</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<table border=\"1\" cellspacing=\"0\" style=\"width:854px\">\r\n	<thead>\r\n		<tr>\r\n			<th style=\"text-align:left; vertical-align:bottom\">学号</th>\r\n			<th style=\"text-align:center; vertical-align:bottom\">姓名</th>\r\n			<th style=\"text-align:right; vertical-align:bottom\">年龄</th>\r\n		</tr>\r\n	</thead>\r\n	<tbody>\r\n		<tr>\r\n			<td style=\"text-align:left; vertical-align:top\">114514</td>\r\n			<td style=\"text-align:center; vertical-align:top\">田所</td>\r\n			<td style=\"text-align:right; vertical-align:top\">24</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:left; vertical-align:top\">1919810</td>\r\n			<td style=\"text-align:center; vertical-align:top\">浩三</td>\r\n			<td style=\"text-align:right; vertical-align:top\">25</td>\r\n		</tr>\r\n	</tbody>\r\n</table>\r\n\r\n<h3><strong>17. 图片 [直接拖进来或者复制粘贴]</strong></h3>\r\n\r\n<pre>\r\n![图片](图片的位置)</pre>\r\n\r\n<p>我还是会选择拖进来或者复制粘贴啦~ 在 Typora 的设置里也可以改图片的储存方式.</p>\r\n\r\n<h3><strong>18. 分割线 [按三个 &quot;*&quot; 或 &quot;-&quot; 或 &quot;_&quot; 并敲回车]</strong></h3>\r\n\r\n<pre>\r\n***\r\n--- (我喜欢用这种)\r\n___\r\n// (其实按三个及以上都可以)</pre>\r\n\r\n<p>由于 <code>*</code> 与 <code>_</code> 均会自动补全, 所以我觉得 <code>-</code> 最为方便.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<hr />\r\n<hr />\r\n<hr />\r\n<h3><strong>19. Emoji表情 [&quot;:&quot; 前置]</strong></h3>\r\n\r\n<p><strong>(注意: 英文输入为扩展语法)</strong></p>\r\n\r\n<pre>\r\n:sweat_smile: \r\n:drooling_face:\r\n:clown_face:\r\n// (敲回车或者鼠标点击, 后置的&quot;:&quot;一般不需要手动输)</pre>\r\n\r\n<p>这个功能唯一的要求就是英语水平要高, 或者大概记得各个 Emoji 的英文名.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>😅 🤤 🤡</p>\r\n\r\n<p>对于其余普通的 Markdown 文本编辑器, 可以直接将 Emoji 表情复制进来, 这是直接<strong>硬编码</strong>的 (<del>刻进DNA里</del>)</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>😅🤤🤡</p>\r\n\r\n<p>用好这个功能可以让你的文本非常的可爱! <del>太抽象了</del></p>\r\n\r\n<p>这里分享一个可以复制<a href=\"https://emojipedia.org/apple/\">全Emoji的网站</a>, 非常好用! 我之前的C语言大作业也是从这里下载的资源!</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<h2><strong>🔥 进阶教程</strong></h2>\r\n\r\n<h3><strong>1. 目录 [自动生成]</strong></h3>\r\n\r\n<pre>\r\n[TOC] (此为 Typora 特有的, 如本文档开头)</pre>\r\n\r\n<p>若使用 VS Code 搭配 Markdown All in One 扩展, 可在 VS Code 的<code>命令面板</code> (即 <a href=\"https://code.visualstudio.com/docs/getstarted/userinterface#_command-palette\">VS Code Command Palette</a>) 输入 <code>Create Table of Contents</code> 自动生成目录, 且可在扩展设置中细调目录参数.</p>\r\n\r\n<h3><strong>2. 内联 HTML 代码 [用 &quot;&lt;&gt; &lt;/&gt;&quot; 包围]</strong></h3>\r\n\r\n<pre>\r\n&lt;div style=&quot;text-align:center&quot;&gt;\r\n  &lt;font style=&quot;color:red&quot;&gt;我不会 HTML 呜呜呜... 浇浇我&lt;/font&gt;\r\n&lt;/div&gt;\r\n\r\n&lt;center&gt;简单的文字居中也可以这样&lt;/center&gt;\r\n\r\n&lt;u&gt;我差点忘了还有下划线这东西...&lt;/u&gt;</pre>\r\n\r\n<p>只要你会写, 你完全可以把 Markdown 当作 <strong>HTML</strong> 来写.</p>\r\n\r\n<p>同时, <code>.md</code> 文件可以直接导出成一个网页.</p>\r\n\r\n<p>下划线可以选中想要下划的文字按下 <code>Ctrl</code> + <code>U</code>.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>​</p>\r\n\r\n<p>我不会 HTML 呜呜呜... 浇浇我</p>\r\n\r\n<p>​</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<p>​</p>\r\n\r\n<p>简单的文字居中也可以这样</p>\r\n\r\n<p>​</p>\r\n\r\n<p>我差点忘了还有下划线这东西...</p>\r\n\r\n<h3><strong>3. 内联 $\\LaTeX$ 公式 [用 &quot;$&quot; 包围]</strong></h3>\r\n\r\n<p><strong>(注意: 部分编译器会不识别部分符号)</strong></p>\r\n\r\n<pre>\r\n$\\LaTeX$ 是最好用的论文排版语言! 不信你看!\r\n\r\n$a^n+b^n=c^n$\r\n\r\n$$\r\n%\\usepackage{unicode-math}\r\n\\displaystyle \\ointctrclockwise\\mathcal{D}[x(t)]\r\n\\sqrt{\\frac{\\displaystyle3\\uppi^2-\\sum_{q=0}^{\\infty}(z+\\hat L)^{q}\r\n\\exp(\\symrm{i}q^2 \\hbar x)}{\\displaystyle (\\symsfup{Tr}\\symbfcal{A})\r\n\\left(\\symbf\\Lambda_{j_1j_2}^{i_1i_2}\\Gamma_{i_1i_2}^{j_1j_2}\r\n\\hookrightarrow\\vec D\\cdot \\symbf P \\right)}}\r\n=\\underbrace{\\widetilde{\\left\\langle \\frac{\\notin \\emptyset}\r\n{\\varpi\\alpha_{k\\uparrow}}\\middle\\vert\r\n\\frac{\\partial_\\mu T_{\\mu\\nu}}{2}\\right\\rangle}}_{\\mathrm{K}_3\r\n\\mathrm{Fe}(\\mathrm{CN})_6} ,\\forall z \\in \\mathbb{R}\r\n$$</pre>\r\n\r\n<p>用 <code>$</code> 包围为单条公式, 按下两个 <code>$</code> 并敲回车即生成公式块.</p>\r\n\r\n<p>E.G.</p>\r\n\r\n<p>$\\LaTeX$ 是最好用的论文排版语言! 不信你看!</p>\r\n\r\n<p>$a^n+b^n=c^n$</p>\r\n\r\n<p>$$<br />\r\n%\\usepackage{unicode-math} \\displaystyle \\ointctrclockwise\\mathcal{D}[x(t)] \\sqrt{\\frac{\\displaystyle3\\uppi^2-\\sum_{q=0}^{\\infty}(z+\\hat L)^{q} \\exp(\\symrm{i}q^2 \\hbar x)}{\\displaystyle (\\symsfup{Tr}\\symbfcal{A}) \\left(\\symbf\\Lambda_{j_1j_2}^{i_1i_2}\\Gamma_{i_1i_2}^{j_1j_2} \\hookrightarrow\\vec D\\cdot \\symbf P \\right)}} =\\underbrace{\\widetilde{\\left\\langle \\frac{\\notin \\emptyset} {\\varpi\\alpha_{k\\uparrow}}\\middle\\vert \\frac{\\partial_\\mu T_{\\mu\\nu}}{2}\\right\\rangle}}_{\\mathrm{K}_3 \\mathrm{Fe}(\\mathrm{CN})_6} ,\\forall z \\in \\mathbb{R}<br />\r\n$$</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<h3><strong>4. *网络图床</strong></h3>\r\n\r\n<p>(这是学长给我的网络图床教程, 我并未实践过...)</p>\r\n\r\n<p>分享一个 Typora 搭配腾讯云COS/阿里云OSS图床的<a href=\"https://blog.csdn.net/guo_ridgepole/article/details/108257277\">例子</a>. 新用户免费试用6个月, 另外还可选择七牛云或者路过图床.</p>\r\n\r\n<h3><strong>5. *Typora 的常用快捷键</strong></h3>\r\n\r\n<table border=\"1\" cellspacing=\"0\" style=\"width:854px\">\r\n	<thead>\r\n		<tr>\r\n			<th style=\"text-align:center; vertical-align:bottom\">按键</th>\r\n			<th style=\"text-align:center; vertical-align:bottom\">效果</th>\r\n			<th style=\"text-align:center; vertical-align:bottom\">按键</th>\r\n			<th style=\"text-align:center; vertical-align:bottom\">效果</th>\r\n		</tr>\r\n	</thead>\r\n	<tbody>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>D</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">选中当前词</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>L</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">选中当前句/行</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>E</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">选中当前区块</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>F</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">搜索当前选中</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>B</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">加粗当前选中</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>H</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">替换当前选中</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>I</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">倾斜当前选中</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>U</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">下划当前选中</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>K</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">将当前选中生成链接</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>J</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">滚动屏幕将选中滚至顶部</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>W</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">关闭当前窗口</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>N</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">打开新窗口</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>O</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">打开文件</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>P</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">搜索文件并打开</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>回车</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">表格下方插入行</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>,</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">打开偏好设置</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>.</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">切换全角/半角标点</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>/</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">切换正常/源代码视图</td>\r\n		</tr>\r\n		<tr>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>Shift</code> + <code>-</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">缩小视图缩放</td>\r\n			<td style=\"text-align:center; vertical-align:top\"><code>Ctrl</code> + <code>Shift</code> + <code>+</code></td>\r\n			<td style=\"text-align:center; vertical-align:top\">放大视图缩放</td>\r\n		</tr>\r\n	</tbody>\r\n</table>\r\n\r\n<p>还有一些不常用的/三键的快捷键不在此列出.</p>\r\n\r\n<h3><strong>6. *Typora 的主题样式与检查元素</strong></h3>\r\n\r\n<p>Markdown 在编译后约等于 HTML. 而 Typora 的正常视图就是编译后的 Markdown, 故Typora的主题样式本质就是 CSS 文件.</p>\r\n\r\n<p>可以下载各种好看的主题给 Typora换上, 同时也可以自己调整对应的 CSS 文件, 或者自己手搓.</p>\r\n\r\n<p>在 Typora 设置中开启 <code>调试模式</code> 后即可在正常视图右击打开 <code>检查元素</code>, 在其中就可以完全将 Markdown 文件当成 HTML 来编辑.</p>\r\n\r\n<p>&nbsp;</p>\r\n\r\n<h2><strong>💯 总结</strong></h2>\r\n\r\n<p>至此, <strong>Markdown + Typora / VSCode</strong> 的手册教程也告一段落.</p>\r\n\r\n<p>不知你看完这么长的教程/手册, 是否能体会到 Markdown 的精妙简洁之处呢?</p>\r\n\r\n<p>其实 Markdown 只是标记语言的最开始, 我的感受是会了 Markdown 之后对于理解 HTML 也有帮助, 对于用 $\\LaTeX$ 来写论文也有帮助. 标记语言正是为了摆脱 Word 那种虽然&quot;所见即所得&quot;, 但又过于花哨浮华, 很差的兼容性与闭源的编码的缺陷. 当你能掌握这样的&quot;所写即所得&quot;时, 你肯定会感受到用 Markdown 这类语言来处理文本的妙处!</p>\r\n', '2024-09-12 05:16:31', 1, 'vi', 2),
(31, '<h1><strong>这是一篇学习内容</strong></h1>\r\n', '2024-09-15 16:12:02', 2, 'vi', 3);

-- --------------------------------------------------------

--
-- 表的结构 `task`
--

CREATE TABLE `task` (
  `id` varchar(36) NOT NULL,
  `name` varchar(128) NOT NULL,
  `description` varchar(128) DEFAULT NULL,
  `user_id` int(11) NOT NULL,
  `complete` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- 表的结构 `todo`
--

CREATE TABLE `todo` (
  `id` int(11) NOT NULL,
  `title` varchar(120) NOT NULL,
  `complete` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `todo`
--

INSERT INTO `todo` (`id`, `title`, `complete`) VALUES
(14, '学习数学', 0),
(15, '背单词', 1);

-- --------------------------------------------------------

--
-- 表的结构 `user`
--

CREATE TABLE `user` (
  `id` int(11) NOT NULL,
  `username` varchar(64) NOT NULL,
  `email` varchar(120) NOT NULL,
  `password_hash` varchar(256) DEFAULT NULL,
  `about_me` varchar(140) DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `last_message_read_time` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- 转存表中的数据 `user`
--

INSERT INTO `user` (`id`, `username`, `email`, `password_hash`, `about_me`, `last_seen`, `last_message_read_time`) VALUES
(1, 'tingchieh', 'tingchieh@foxmail.com', 'scrypt:32768:8:1$IHUUKcSA1i0tmRZQ$c06681f69c7c396b4732b876c92657bba52e91bad3157e69edb63188725757b071e6e4d18fbd12d6be09c0996dcc9a4cce6371a26887df0175f866ca9df3cce4', '你好我好大家好', '2024-09-15 16:11:26', '2024-09-15 15:57:59'),
(2, 'susan', 'susan@example.com', 'scrypt:32768:8:1$LSyade8OfYwxlBk0$b631fd0f8222c2fbc3de692fd89868cc3fa9e39728531a228a9ad39383f6e3492c09402c4071c3b4bcf582e5fda9b274e51ffbfb7a100c59605ce55a3871455b', 'hello\r\n', '2024-09-16 02:31:41', '2024-09-16 02:14:46'),
(3, 'yzqzss', 'yzqzss@yandex.com', 'scrypt:32768:8:1$R7Ut9m3c1K7XhIe1$d287223f7724bcb911e868a3ba66871c901d0a0406e0d976cb052d251d6b85493ac0a96c88feb05328ae07203754098f35ca8ec17417fe1fbbfdad0a59d6a488', NULL, '2024-09-15 15:57:08', NULL);

--
-- 转储表的索引
--

--
-- 表的索引 `about`
--
ALTER TABLE `about`
  ADD PRIMARY KEY (`id`);

--
-- 表的索引 `alembic_version`
--
ALTER TABLE `alembic_version`
  ADD PRIMARY KEY (`version_num`);

--
-- 表的索引 `category`
--
ALTER TABLE `category`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- 表的索引 `comment`
--
ALTER TABLE `comment`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_comment_timestamp` (`timestamp`);

--
-- 表的索引 `followers`
--
ALTER TABLE `followers`
  ADD PRIMARY KEY (`follower_id`,`followed_id`),
  ADD KEY `followed_id` (`followed_id`);

--
-- 表的索引 `link`
--
ALTER TABLE `link`
  ADD PRIMARY KEY (`id`);

--
-- 表的索引 `message`
--
ALTER TABLE `message`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_message_recipient_id` (`recipient_id`),
  ADD KEY `ix_message_sender_id` (`sender_id`),
  ADD KEY `ix_message_timestamp` (`timestamp`);

--
-- 表的索引 `movie`
--
ALTER TABLE `movie`
  ADD PRIMARY KEY (`id`);

--
-- 表的索引 `notification`
--
ALTER TABLE `notification`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_notification_name` (`name`),
  ADD KEY `ix_notification_timestamp` (`timestamp`),
  ADD KEY `ix_notification_user_id` (`user_id`);

--
-- 表的索引 `post`
--
ALTER TABLE `post`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_post_timestamp` (`timestamp`),
  ADD KEY `ix_post_user_id` (`user_id`),
  ADD KEY `category_id` (`category_id`);

--
-- 表的索引 `task`
--
ALTER TABLE `task`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `ix_task_name` (`name`);

--
-- 表的索引 `todo`
--
ALTER TABLE `todo`
  ADD PRIMARY KEY (`id`);

--
-- 表的索引 `user`
--
ALTER TABLE `user`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `ix_user_email` (`email`),
  ADD UNIQUE KEY `ix_user_username` (`username`);

--
-- 在导出的表使用AUTO_INCREMENT
--

--
-- 使用表AUTO_INCREMENT `about`
--
ALTER TABLE `about`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- 使用表AUTO_INCREMENT `category`
--
ALTER TABLE `category`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- 使用表AUTO_INCREMENT `comment`
--
ALTER TABLE `comment`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- 使用表AUTO_INCREMENT `link`
--
ALTER TABLE `link`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=10;

--
-- 使用表AUTO_INCREMENT `message`
--
ALTER TABLE `message`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- 使用表AUTO_INCREMENT `movie`
--
ALTER TABLE `movie`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- 使用表AUTO_INCREMENT `notification`
--
ALTER TABLE `notification`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=73;

--
-- 使用表AUTO_INCREMENT `post`
--
ALTER TABLE `post`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=32;

--
-- 使用表AUTO_INCREMENT `todo`
--
ALTER TABLE `todo`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=17;

--
-- 使用表AUTO_INCREMENT `user`
--
ALTER TABLE `user`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- 限制导出的表
--

--
-- 限制表 `followers`
--
ALTER TABLE `followers`
  ADD CONSTRAINT `followers_ibfk_1` FOREIGN KEY (`followed_id`) REFERENCES `user` (`id`),
  ADD CONSTRAINT `followers_ibfk_2` FOREIGN KEY (`follower_id`) REFERENCES `user` (`id`);

--
-- 限制表 `message`
--
ALTER TABLE `message`
  ADD CONSTRAINT `message_ibfk_1` FOREIGN KEY (`recipient_id`) REFERENCES `user` (`id`),
  ADD CONSTRAINT `message_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `user` (`id`);

--
-- 限制表 `notification`
--
ALTER TABLE `notification`
  ADD CONSTRAINT `notification_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`);

--
-- 限制表 `post`
--
ALTER TABLE `post`
  ADD CONSTRAINT `post_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`),
  ADD CONSTRAINT `post_ibfk_2` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`);

--
-- 限制表 `task`
--
ALTER TABLE `task`
  ADD CONSTRAINT `task_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
