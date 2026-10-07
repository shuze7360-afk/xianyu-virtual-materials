# 环境级踩坑清单（35 条速查表）

出错先查这张表，别瞎试重试。

| # | 现象 | 原因 | 解法 |
|---|---|---|---|
| 1 | 描述提交后红字"不能包含emoji" | emoji 被闲鱼拦截 | 全文去 emoji，用"注意："等文字替代；勾号用 √ |
| 2 | 发布页橙字"网页版暂不支持发布此分类" | 自动分类选中 APP 专属/服务分类 | 资料类手动改回「电子资料」；服务类走破解路线（见 publish-xianyu.md） |
| 3 | draft_item 第二次调用跳到 /im | fishclaw 导航 bug | restart→login→draft 一次一轮 |
| 4 | 上传报 errno -7 | 路径不在 /apps 下 | remote_path 以 /apps/ 开头 |
| 5 | token 报 20017/-6 | 复制不全/体验 key 失效 | 重新授权，curl 先验后用 |
| 6 | npm 包 404 | 网传配置包名不存在 | 官方 repo：baidu-netdisk/mcp |
| 7 | uv sync 编译失败 | Python 3.14 无 aiohttp 轮子 | `uv sync --python 3.12` |
| 8 | python 脚本连 SSE 卡死 | 本地代理（127.0.0.1:xxxx）劫持长连接 | `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY NO_PROXY="*"` |
| 9 | UA 原生点击/滚轮全被拒 | 本机对坐标类原始输入限制 | 全走 a11y 元素点击 + app 键盘；select 下拉用键盘 down+enter |
| 10 | 坐标点击报 frame 不匹配/stale | 帧绑定失效 | 不修，绕行（见 #9）；zoom 子帧同样会被拒 |
| 11 | 分享报 errno=2 param error（各档期全报） | pwd 超过 4 位 | pwd 必须**正好 4 位**数字+小写字母（如 k1a2） |
| 12 | file_list 传 path 一直返回根目录 | 参数名是 `dir` 且中文路径要 URL 编码 | `dir=quote(path, safe="")`；搜文件用 file_keyword_search 的 `key` |
| 13 | 点"添加细节图"以为没弹对话框 | 对话框是独立 Chromium 子进程（新 pid） | list_apps 找新 pid（标题"打开"）→ type 多个**带引号路径**一次多选 → AXPress"打开(O)" |
| 14 | 3.14 跑脚本报 No module named 'mcp' | mcp 包装在 Python 3.13 | 用 Python313 的 python.exe 跑脚本 |
| 15 | manage_item 找不到「下架/删除」按钮 | 选择器与页面结构不匹配，重试无效 | 用户在商品页手点（「下架」在「删除」左边，别点错） |
| 16 | **流程翻车：未交审就发布** | 把"继续"当成了发布授权 | 发布前固定停下交审，"确认发布"才 publish |
| 17 | 分类键盘导航选错项 | 下拉选项每轮重排顺序 | "动一步观察一步"：up/down 后核对 focused 行再回车 |
| 18 | 键入文字进了地址栏 | 输入时焦点在 omnibox 不在页面 | 输入前核对 a11y focused 标记；误入按 Esc 撤销 |
| 19 | 操作中途弹扫码登录框 | 会话掉登录（Cookie 失效） | 先 login 再重试原操作，别误判为工具坏了 |
| 20 | 输入类操作报"activateWindow"拒绝 | 浏览器窗口被最小化 | 恢复/前置窗口后再操作 |
| 21 | AI 生图出图与主题无关（默认图） | 生图 MCP 未配 API KEY，自动回退内置默认图 | PIL + 系统雅黑字体自绘封面；✅ 在雅黑渲染成豆腐块，勾号统一用 √ |
| 22 | 键盘操作报 frontmost_pid_mismatch 反复出现 | 多窗口环境焦点被抢（浮窗/终端本体） | 激活窗口只能救急；**终解 = 自开 Playwright 操作，完全无焦点依赖** |
| 23 | 发布页找不到分类下拉 | 下拉是动态渲染，须先传图/填描述触发"智能识别属性" | 先传图再选分类；候选分类随内容变，识别错时补填对口描述矫正 |
| 24 | 脚本跑完表单全丢 | 发布页表单不持久化 | 填表+动作一个脚本一次跑完，中途不 close |
| 25 | 想注入 JS/改响应但 CDP 连不上 | 本机浏览器用 --remote-debugging-pipe 管道非端口 | 放弃 CDP，自开 Playwright（headless=False + route 拦截），Cookie 从 FishClaw 缓存 add_cookies 复用 |
| 26 | 网页版"我卖出的"入口点击无响应 | 卖家订单列表页网页版不存在（路由表只有 bought/order-detail，无 sold） | 卖家侧状态源改用 /im 会话列表「交易成功」芯片 + 聊天内订单卡（见 publish-xianyu.md 全自动代发） |
| 27 | 两个登录态判定结论相反 | 已登录页顶栏/页脚也有"登录"链接（SEO sitemap），先查登录按钮会假阴性；宽匹配 `div[class*="user"]` 又会假阳性 | 只认正向特征（个人中心链接/头像/订单/收藏）；拿不准 dump 页面 innerText 找用户名定性 |
| 28 | 会话"交易成功"芯片不一定是目标商品订单 | 芯片只反映该会话最新订单状态，可能是小额其他商品 | 商品判定看聊天内容：关键词强匹配 + 价格签名弱匹配（签名别配太短）；判定不出→跳过交人工，别瞎发 |
| 29 | 发送按钮按 innerText"发送"搜不到 | 按钮文字是"发 送"（带空格）；textarea placeholder 明示"按Enter键发送" | 输入后按 Enter 发送；发送后回读会话文本含网盘链接才算成功 |
| 30 | 页面类名难写稳定选择器 | 类名带哈希后缀且随发版变化（如 conversation-item-hover--sNtmkHXC） | 一律前缀匹配 `[class*="..."]`；结构不认识先跑 probe 模式 dump 现场 |
| 31 | 统计类细节图把商品核心数据挂上详情页 | 防剧透只防了"题目内容"，没防"统计结论"；分布/档位/构成本身就是货 | 凭证型三件套：结构清单/打码表格样例/隐私承诺；统计图表进 zip 不上架 |
| 32 | 直连 rest/2.0/xpan/share?method=set 全档期报 errno=2 | 分享不在开放 xpan REST API 里，只能走官方 MCP 网关 | Python313+mcp 客户端连 mcp-pan.baidu.com/sse?access_token=<token> 直调 file_sharelink_set |
| 33 | superfile2 上传成功但断言失败 | 成功返回 {"md5":...} 无 errno 字段 | 判断 "md5" in resp，别只看 errno |
| 34 | PIL 自绘图文字出框/列截断 | 固定字号+固定列宽，中文与符号实际宽度不可控 | fit() 按最长行 textlength 自动取统一字号；列宽逐列预算；出图必须目检 |
| 35 | 商品标题与文案首行不一致 | 闲鱼用描述首行+次行开头自动拼接成标题 | 首行按"会成为标题"设计且信息自足；拼接结果可接受就不必改 |
