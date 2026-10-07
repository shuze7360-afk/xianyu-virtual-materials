# -*- coding: utf-8 -*-
"""
闲鱼电子资料自动发货
====================
升级自 xianyu-virtual-materials SOP 的"确认收货后人工代发"流程：

    /im 会话列表扫「交易成功」芯片 → 点开会话 → 聊天内容判定商品（关键词+价格签名）
    → 会话里无 pan.baidu.com 历史才发货（三重防线）→ textarea 输入 + Enter 发送 → 回读验证 → 记台账

说明：闲鱼网页版没有"我卖出的"订单页（入口点了无响应），卖家侧唯一的
交易状态源就是 IM 会话列表芯片与聊天内订单卡，本脚本据此设计。

模式：
  check   只检测不发送，输出报告（默认，最安全）
  send    检测 + 自动发送（受单次/每日上限与随机间隔约束）
  probe   结构侦察：把 /im 现场 dump 到 recon/ 供排查页面改版

用法：
  python auto_delivery.py                     # check 模式
  python auto_delivery.py --mode send         # 检测并发送
  python auto_delivery.py --mode probe        # 页面结构侦察

退出码：0 正常（含"无事可做"）| 3 登录失效 | 4 页面结构不认识 | 5 有发送失败
依赖：Playwright（chromium）+ 闲鱼网页版 Cookie 文件（JSON 数组格式，可由 FishClaw MCP 等
任意登录流程产出，路径用环境变量 XIANYU_COOKIES 指定，默认 ~/.goofish-auto-delivery/）。
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent
COOKIES_PATH = Path(os.environ.get(
    "XIANYU_COOKIES",
    str(Path.home() / ".goofish-auto-delivery" / "xianyu_cookies.json")))
CONFIG_PATH = BASE / "listing_links.json"
LEDGER_PATH = BASE / "delivery_ledger.json"
REPORT_DIR = BASE / "reports"
RECON_DIR = BASE / "recon"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# ── 业务常量（改这里适配新话术/新状态） ──────────────────────
SUCCESS_CHIP = "交易成功"          # 会话列表芯片：买家已确认收货
LINK_MARK = "pan.baidu.com"        # 会话里出现即视为已发货
MAX_SEND_PER_RUN = 2               # 单次运行最多发送条数（防风控）
MAX_SEND_PER_DAY = 6               # 每日自动发送上限
SEND_DELAY_RANGE = (40, 80)        # 两条消息之间的随机间隔秒数

# 页面结构锚点（哈希后缀会随前端发版变化，一律前缀匹配）
SEL_CONVERSATION_ITEM = '[class*="conversation-item"]'
SEL_TEXTAREA = 'textarea[class*="textarea-no-border"], textarea[placeholder*="请输入消息"]'

MSG_TEMPLATE = """【{name}】
链接：{url}
提取码：{pwd}（链接{days}天有效）

收到后请尽快转存：打开链接→勾选资料→保存到我的网盘，
转存后就是你自己的副本，不怕链接失效。
链接万一过期，联系我免费补发。
资料仅供个人复习使用，请勿倒卖传播。"""


def log(msg):
    line = f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(BASE / "auto_delivery.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def delay(a=0.8, b=1.8):
    time.sleep(random.uniform(a, b))


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"!! 解析 {path.name} 失败：{e}")
    return default


def save_ledger(ledger):
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


# ══════════════════════════════════════════════════════
# 浏览器与登录
# ══════════════════════════════════════════════════════

class Browser:
    def __init__(self, headless=False):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless, args=[
            "--disable-blink-features=AutomationControlled", "--no-sandbox",
            "--disable-dev-shm-usage", "--window-position=200,50", "--window-size=1150,900"])
        self.ctx = self.browser.new_context(
            viewport={"width": 1150, "height": 900}, user_agent=UA,
            locale="zh-CN", timezone_id="Asia/Shanghai")
        self.ctx.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});
            window.chrome={runtime:{}};
        """)
        cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
        self.ctx.add_cookies(cookies)
        self.page = self.ctx.new_page()
        log(f"浏览器已启动，载入 {len(cookies)} 条 Cookie")

    def close(self):
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass

    def is_logged_in(self):
        """只认正向特征；已登录页顶栏/页脚也可能有『登录』链接，不能拿它当未登录证据。"""
        page = self.page
        if "login.taobao.com" in page.url:
            return False
        for sel in ['a[href*="/personal"]', 'img[class*="avatar"]', 'div[class*="avatar"]']:
            try:
                if page.locator(sel).first.is_visible(timeout=700):
                    return True
            except Exception:
                pass
        for kw in ["订单", "收藏"]:
            try:
                if page.locator(f'text="{kw}"').first.is_visible(timeout=600):
                    return True
            except Exception:
                pass
        return False

    def dump(self, name):
        """把当前页面 dump 到 recon/，用于页面改版排查。"""
        try:
            RECON_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%m%d_%H%M%S")
            (RECON_DIR / f"{ts}_{name}.url.txt").write_text(self.page.url, encoding="utf-8")
            (RECON_DIR / f"{ts}_{name}.text.txt").write_text(
                self.page.evaluate("document.body.innerText"), encoding="utf-8")
            (RECON_DIR / f"{ts}_{name}.html.html").write_text(self.page.content(), encoding="utf-8")
            log(f"[dump] {name} -> recon/")
        except Exception as e:
            log(f"[dump:{name}] 失败：{e}")

    def body_text(self):
        try:
            return self.page.evaluate("document.body.innerText") or ""
        except Exception:
            return ""


# ══════════════════════════════════════════════════════
# 检测：会话列表 → 交易成功 买家
# ══════════════════════════════════════════════════════

def scan_conversation_list(b: Browser) -> list:
    """扫描 /im 左侧会话列表，返回 [{buyer, status}]（status 取 SUCCESS_CHIP 或 ''）。"""
    page = b.page
    if "/im" not in page.url:
        page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=30000)
        delay(3.0, 4.0)

    items = page.evaluate("""(chip) => {
        const out = [];
        const nodes = document.querySelectorAll('[class*="conversation-item"]');
        for (const e of nodes) {
            const t = (e.innerText || '').trim();
            if (!t || t.length > 120) continue;
            out.push(t);
        }
        // 兜底：类名不认识时，用短文本节点凑（列表里带状态芯片的小块）
        if (out.length === 0) {
            for (const e of document.querySelectorAll('div,li')) {
                const t = (e.innerText || '').trim();
                if (t.includes(chip) && t.length < 90 && t.split('\\n').length <= 5) out.push(t);
            }
        }
        return out;
    }""", SUCCESS_CHIP)

    results, seen = [], set()
    for raw in items:
        lines = [x.strip() for x in raw.split("\n") if x.strip()]
        if not lines:
            continue
        buyer = lines[0]
        status = SUCCESS_CHIP if SUCCESS_CHIP in lines else ""
        if status and re.fullmatch(r"[\w\*\u4e00-\u9fa5·]{2,20}", buyer) and buyer not in seen:
            seen.add(buyer)
            results.append({"buyer": buyer, "status": status})
    log(f"会话列表扫描完成：{len(items)} 项，其中「{SUCCESS_CHIP}」{len(results)} 人")
    return results


def open_conversation(b: Browser, buyer: str) -> bool:
    """点击会话列表中该买家的会话项。"""
    page = b.page
    try:
        loc = page.locator(SEL_CONVERSATION_ITEM, has_text=buyer).first
        if loc.is_visible(timeout=2500):
            loc.click()
            delay(1.5, 2.5)
            return True
    except Exception:
        pass
    # 兜底：纯文本定位
    try:
        loc = page.locator(f'text="{buyer}"').first
        if loc.is_visible(timeout=2000):
            loc.click()
            delay(1.5, 2.5)
            return True
    except Exception:
        pass
    return False


def match_product(chat_text: str, config: list):
    """按 关键词（强）→ 价格签名（弱） 判定会话对应哪个商品配置；0 或多个命中返回 None。"""
    nospace = re.sub(r"\s+", "", chat_text)
    kw_hits = [e for e in config
               if any(k and k in chat_text
                      for k in (e["match"] if isinstance(e.get("match"), list) else [e.get("match", "")]))]
    if len(kw_hits) == 1:
        return kw_hits[0]
    if len(kw_hits) > 1:
        return None  # 歧义，交人工
    price_hits = [e for e in config if e.get("price") and e["price"] in nospace]
    if len(price_hits) == 1:
        return price_hits[0]
    return None


# ══════════════════════════════════════════════════════
# 发送
# ══════════════════════════════════════════════════════

def send_message(b: Browser, text: str) -> bool:
    """在当前打开的会话输入消息并发送，回读验证链接已出现在会话里。"""
    page = b.page
    try:
        ta = page.locator(SEL_TEXTAREA).first
        if not ta.is_visible(timeout=3000):
            b.dump("send_no_textarea")
            return False
        ta.click()
        delay(0.3, 0.6)
        try:
            ta.press_sequentially(text, delay=12)   # 拟人输入
        except Exception:
            ta.type(text, delay=12)
        delay(0.4, 0.9)
        page.keyboard.press("Enter")
        delay(1.5, 2.5)
        return LINK_MARK in b.body_text()
    except Exception as e:
        log(f"发送异常：{e}")
        b.dump("send_error")
        return False


# ══════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["check", "send", "probe"], default="check")
    ap.add_argument("--max-send", type=int, default=MAX_SEND_PER_RUN)
    args = ap.parse_args()

    if not COOKIES_PATH.exists():
        log(f"!! 找不到 Cookie 文件：{COOKIES_PATH}")
        return 3

    config = load_json(CONFIG_PATH, [])
    ledger = load_json(LEDGER_PATH, {})
    if not config:
        log("!! listing_links.json 为空：先配置商品→网盘链接映射")
        return 0

    REPORT_DIR.mkdir(exist_ok=True)
    report = {"time": datetime.now().isoformat(timespec="seconds"), "mode": args.mode,
              "success_buyers": [], "sent": [], "skipped": [], "errors": []}

    b = Browser(headless=os.environ.get("XIANYU_HEADLESS", "") == "1")
    try:
        b.page.goto("https://www.goofish.com", wait_until="domcontentloaded", timeout=30000)
        delay(2.0, 3.0)
        if not b.is_logged_in():
            log("!! 登录已失效：请让助手调用 fishclaw login 扫码，Cookie 会自动共享")
            report["errors"].append("login_expired")
            return finish(report, 3)

        if args.mode == "probe":
            b.dump("probe_home")
            b.page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=30000)
            delay(3.0, 4.0)
            b.dump("probe_im")
            log("probe 完成：现场已存 recon/")
            return finish(report, 0)

        convs = scan_conversation_list(b)
        if not convs:
            b.dump("im_no_conversations")
            report["errors"].append("conversation_list_not_parsed")
            return finish(report, 4)

        buyers = [c["buyer"] for c in convs if c["status"] == SUCCESS_CHIP]
        report["success_buyers"] = buyers
        if not buyers:
            log("当前没有「交易成功」待处理会话")
            return finish(report, 0)

        today = datetime.now().strftime("%F")
        sent_today = sum(1 for v in ledger.values()
                         if isinstance(v, dict) and str(v.get("sent_at", "")).startswith(today))
        budget = min(args.max_send, MAX_SEND_PER_DAY - sent_today)
        if args.mode == "send":
            log(f"发送预算：本次最多 {max(budget, 0)} 条（今日已发 {sent_today}/{MAX_SEND_PER_DAY}）")

        for buyer in buyers:
            if any(s.get("buyer") == buyer for s in report["skipped"] + report["sent"]):
                continue
            ledger_hit = next((k for k, v in ledger.items()
                               if isinstance(v, dict) and v.get("buyer") == buyer), None)
            if ledger_hit:
                report["skipped"].append({"buyer": buyer, "reason": "台账已有记录"})
                continue

            if not open_conversation(b, buyer):
                report["skipped"].append({"buyer": buyer, "reason": "未能点开会话"})
                continue
            chat_text = b.body_text()

            if LINK_MARK in chat_text:
                ledger[ledger_hit or f"history|{buyer}"] = {
                    "buyer": buyer, "sent_at": datetime.now().isoformat(timespec="seconds"),
                    "mode": "history_dedup"}
                save_ledger(ledger)
                report["skipped"].append({"buyer": buyer, "reason": "会话中已有网盘链接（历史人工发货）"})
                continue

            entry = match_product(chat_text, config)
            if entry is None:
                excerpt = re.sub(r"\s+", " ", chat_text)[:120]
                report["skipped"].append({"buyer": buyer,
                                          "reason": "聊天内容无法唯一判定商品（关键词/价格都不中或歧义）",
                                          "chat_excerpt": excerpt})
                continue

            msg = MSG_TEMPLATE.format(name=entry.get("name", ""), url=entry["url"],
                                      pwd=entry["pwd"], days=entry.get("days", 365))
            if args.mode != "send":
                report["skipped"].append({"buyer": buyer, "product": entry.get("name"),
                                          "reason": "check 模式（待发送候选）"})
                continue
            if budget <= 0:
                report["skipped"].append({"buyer": buyer, "reason": "超出本次/今日发送预算"})
                continue

            ok = send_message(b, msg)
            if ok:
                budget -= 1
                ledger[f"{entry.get('item_id', '')}|{buyer}"] = {
                    "buyer": buyer, "item": entry.get("name"), "link": entry["url"],
                    "pwd": entry["pwd"], "sent_at": datetime.now().isoformat(timespec="seconds"),
                    "mode": "auto"}
                save_ledger(ledger)
                report["sent"].append({"buyer": buyer, "product": entry.get("name")})
                log(f"√ 已发货：{buyer} ← {entry.get('name')}")
                if budget > 0:
                    time.sleep(random.uniform(*SEND_DELAY_RANGE))
            else:
                report["errors"].append({"buyer": buyer, "reason": "发送后回读验证失败（未写台账，下轮重试）"})
                log(f"× 发送验证失败：{buyer}")

        code = 5 if report["errors"] else 0
        return finish(report, code)
    finally:
        b.close()


def finish(report, code):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (REPORT_DIR / f"report_{ts}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    n_sent, n_skip, n_err = len(report["sent"]), len(report["skipped"]), len(report["errors"])
    log(f"== 结束 mode={report['mode']} 发送={n_sent} 跳过={n_skip} 异常={n_err} 退出码={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
