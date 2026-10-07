# 百度网盘 MCP：环境、上传与分享

> 以下 `~` 指 Windows 用户主目录（`C:\Users\<你>`）。三件套配置持久化在 `~/.zcode/cli/config.json`，新机器/新会话零配置直接可用；新装 MCP 要重启 ZCode 才加载。

## 环境三件套

| 服务器 | 类型 | 用途 |
|---|---|---|
| `baidu-netdisk` | http(SSE) | 分享链接等 16 个云端工具 |
| `netdisk-fileupload` | stdio(uv) | **上传本地文件**（唯一通道） |
| `fishclaw` | stdio(uv) | 闲鱼：login / draft / publish / 在售管理 |

### 关键配置
- 源码位置：`~/.zcode/mcp/baidu-netdisk/src/baidu-netdisk`（必须 Python 3.12）、`~/.zcode/mcp/FishClaw_MCP`（uv sync + playwright install chromium）。
- AccessToken 填两处：SSE 的 URL 参数 + stdio 的 env `BAIDU_NETDISK_ACCESS_TOKEN`。
- token 获取：浏览器开授权 URL → 只复制 `access_token=` 到下一个 `&` → **先 curl 验证再写入配置**（errno 20017/-6 = 复制不全 / key 失效）。
- **写 SSE/stdio 脚本用 Python 3.13**（mcp 包只装在那；3.14 会报 No module named 'mcp'）。

### 大坑：网传包名要先验证
网上抄的 MCP 配置包名可能根本不存在（npm/镜像 404）——落配置前先 `npm view` / 搜 GitHub 验证。

## 上传（stdio MCP，直连 OpenAPI）

- 工具：`upload_file(local_file_path, remote_path)`
- **remote_path 必须在 `/apps/` 下**，否则预创建报 errno **-7**
- 工具会把 remote_path 当**文件夹**用 → 实际文件落在 `/apps/<你填的路径>/<文件名>`（套一层，不影响分享）
- 上传结果直接返回 `fs_id`，分享时直接用
- 连接方式：Python `mcp.client.stdio` + `ClientSession`（自写小脚本即可，脚本建议放固定目录备份，别只留 Temp）

## 分享（SSE 远程 MCP）

- 工具：`file_sharelink_set(fsid_list='["<fsid>"]', period=天数, pwd='4位数字+小写')`
- fsid_list 是**字符串化的 JSON 数组**（元素带引号）
- **period 一律拉最长：先试 365（已验证可行），失败降 240/120**——链接宁长勿短
- **pwd 必须正好 4 位**：超过 4 位（如 5 位）各档期全报 errno=2 param error，别误判成权限问题
- **查文件别用 file_list 的 path 参数**（不存在，会一直返回根目录）：用 `dir` 参数且中文路径要 URL 编码（`quote(path, safe="")`，斜杠也编码）；搜文件用 `file_keyword_search` 的 `key` 参数
- 返回 `data.link` + `short_url`；创建后 curl -I 验证可访问
- **买家侧链接格式：`https://pan.baidu.com/s/1<short_url>?pwd=<4位码>`**
- 同一文件可建多条分享并存（旧的不会自动失效）——**换新链接后必须明确"对外唯一"那条**，话术里只发一条，避免发混
- **没有取消分享的工具**——撤回旧链接需手动：网盘网页版 → 我的分享 → 取消

## 万能钥匙

到期 / 想改有效期 / 怀疑泄露 → 重新 `file_sharelink_set` 生成一条新的即可，旧的自然过期。生成新链接能修复一切链接问题。

## token 过期恢复与分享网关（2026-10-07 实测补充）

### 症状与授权
- `upload_file` 报 errno **-6**、curl file?method=list 同样 -6 = token 过期（与 20017 复制不全区分：先 curl 预检）
- 恢复：项目 README 里的 oob 授权 URL（response_type=token）→ 浏览器授权后页面直接显示 access_token → **用户常把 &session_secret=... 一起复制，取 & 之前的主串**；先 curl 预检再写回 config 两处（全局替换旧 token，留 .bak）

### 免重启直连（当次绕过 MCP）
- 改 config 只在下次 ZCode 重启后影响 MCP；当次用脚本直连（token 走环境变量，勿落日志）
- **上传可直连 REST**：precreate → pcs/superfile2 → create（rtype=1 覆盖同路径会生成新 fs_id）；superfile2 成功返回 `{"md5":...}` **无 errno 字段**，别按 errno 断言
- **分享直连不通**：rest/2.0/xpan/share?method=set 全档期 errno=2 → 必须走官方 MCP 网关：Python313 + `mcp.client.sse` 连 `https://mcp-pan.baidu.com/sse?access_token=<token>` 直调 `file_sharelink_set`（fsid_list=字符串化JSON数组、period=数字、pwd=4位）
- 所有直连绕代理（见 pitfalls #8）：curl `env -u` 三变量，requests `trust_env=False`
