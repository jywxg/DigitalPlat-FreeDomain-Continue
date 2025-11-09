#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# (已修正登录 URL)
# (已修正 do_login 逻辑以等待元素可见)
# (已修正 print_log 中的 Color.END 拼写错误)

import asyncio
import os
import subprocess
import urllib.parse
import time
import random
from datetime import datetime

# --- GHA 移植修改 1: 从环境变量读取配置 ---
CONFIG = {
    "email": os.getenv("DP_EMAIL"),
    "password": os.getenv("DP_PASSWORD"),
    "tg_token": os.getenv("TG_TOKEN"),
    "tg_chat_id": os.getenv("TG_CHAT_ID"),
    "max_retries": 3,
    "headless": True,  
    "slow_mo": 500,    
    "timeout": 120000,  
    "cf_timeout": 300,  
    "executablePath": None, # <-- GHA 关键修改: 设为 None, 使用 GHA 自动下载的浏览器
    "browser_args": [   # 保留所有成功的反检测参数
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--single-process",
        "--no-zygote",
        "--disable-setuid-sandbox",
        "--disable-software-rasterizer",
        "--disable-features=site-per-process",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection"
    ]
}

# --- GHA 移植修改 2: 从环境变量读取代理 ---
PROXY_URL = os.getenv("PROXY_URL") # 格式: http://... 或 socks5://...

# ------------------------------------------
# ... 
# ------------------------------------------

class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_log(message, level="info", important=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if level == "error":
        color = Color.RED
        prefix = "❌ ERROR"
    elif level == "warning":
        color = Color.YELLOW
        prefix = "⚠️ WARN"
    elif level == "debug":
        color = Color.CYAN
        prefix = "🐛 DEBUG"
    else:
        color = Color.GREEN
        prefix = "ℹ️ INFO"
    if important:
        color = Color.BOLD + color
    # vvvvvvvvvvvv 这是唯一修改的行 vvvvvvvvvvvv
    print(f"{Color.WHITE}[{timestamp}]{Color.END} {color}{prefix}:{Color.END} {message}")
    # ^^^^^^^^^^^^^^ 这是唯一修改的行 ^^^^^^^^^^^^^^


async def tg_send(text):
    if not CONFIG["tg_token"] or not CONFIG["tg_chat_id"]:
        print_log("TG_TOKEN 或 TG_CHAT_ID 未设置，跳过发送通知。", "warning")
        return
    try:
        print_log(f"发送TG通知: {text[:100]}...", "debug")
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{CONFIG['tg_token']}/sendMessage",
            "-d", f"chat_id={CONFIG['tg_chat_id']}",
            "-d", f"text={urllib.parse.quote(text)}",
            "-d", "parse_mode=Markdown"
        ], capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            print_log(f"TG通知失败: {result.stderr}", "error")
    except Exception as e:
        print_log(f"TG通知异常: {str(e)}", "error")


# --- GHA 移植修改 3: 在 init_browser 中应用代理 ---
async def init_browser():
    from playwright.async_api import async_playwright
    try:
        playwright = await async_playwright().start()
        
        # 准备代理设置
        proxy_settings = None
        if PROXY_URL:
            print_log("检测到代理配置，将使用代理。", "debug")
            proxy_settings = {"server": PROXY_URL}
        else:
            print_log("未检测到代理配置，将直接连接 (在GHA上大概率失败)。", "warning")

        browser = await playwright.chromium.launch(
            headless=CONFIG["headless"],
            executable_path=CONFIG["executablePath"], # (值为 None)
            args=CONFIG["browser_args"],
            proxy=proxy_settings, # <-- 在此应用代理
            ignore_default_args=[
                "--enable-automation",
                "--enable-blink-features=IdleDetection"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            ignore_https_errors=True
        )
        page = await context.new_page()
        return playwright, browser, context, page
    except Exception as e:
        print_log(f"浏览器初始化失败: {str(e)}", "error")
        if "executable doesn't exist" in str(e):
            print_log("请检查Chromium安装路径是否正确", "warning")
        raise

# ------------------------------------------
# (do_login 函数是正确的, 无需修改)
# ------------------------------------------

async def do_login(page):
    try:
        print_log("正在访问登录页面...")
        await page.goto("https://dash.domain.digitalplat.org/auth/login", timeout=CONFIG["timeout"])
        
        # --- 修正逻辑 ---
        # 1. 不再使用旧的 wait_for_selector，因为它只等待 DOM，不等待“可见”。
        # 2. 我们将使用 page.locator(...).wait_for() 来明确等待“可见”状态。
        
        print_log("等待登录表单变为[可见]状态...")
        
        # 步骤 A: 等待 Email 输入框变为可见
        email_input = page.locator('input[name="email"]')
        try:
            # 等待3分钟，应对 CF 盾（虽然我们已经通过了，但保留这个时间是安全的）
            await email_input.wait_for(state="visible", timeout=180000)
            print_log("Email 输入框已可见。")
        except Exception as e:
            print_log(f"等待 Email 输入框[可见]超时: {e}", "error", important=True)
            await page.screenshot(path="login_email_not_visible_error.png")
            raise Exception("登录失败：Email 输入框未变为可见")

        # 步骤 B: 等待 Password 输入框变为可见
        password_input = page.locator('input[name="password"]')
        try:
            # 页面JS可能需要一点时间，我们给它30秒
            await password_input.wait_for(state="visible", timeout=30000)
            print_log("Password 输入框已可见。")
        except Exception as e:
            print_log(f"等待 Password 输入框[可见]超时: {e}", "error", important=True)
            await page.screenshot(path="login_password_not_visible_error.png")
            raise Exception("登录失败：Password 输入框未变为可见")

        # 步骤 C: 两个框都可见后，再填写
        print_log("正在填写登录表单...")
        await email_input.fill(CONFIG["email"])
        await password_input.fill(CONFIG["password"])
        
        # 步骤 D: 点击登录
        await page.click('button[type="submit"]')
        
        try:
            await page.wait_for_url("**/panel/main**", timeout=60000)
            print_log("登录成功", important=True)
            return True
        except Exception as e:
            print_log(f"登录状态验证失败: {str(e)}", "error")
            await page.screenshot(path="login_failed_error.png")
            return False
            
    except Exception as e:
        print_log(f"登录流程异常: {str(e)}", "error")
        return False

# ------------------------------------------
# ... (renew_domains 和 main 函数保持不变) ...
# ------------------------------------------

async def renew_domains(page):
    report = {
        "success": [],
        "skipped": [],
        "failed": [],
        "errors": []
    }
    
    try:
        print_log("正在加载域名列表...")
        await page.goto("https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains", 
                       timeout=CONFIG["timeout"])
        
        try:
            await page.wait_for_selector('table tbody tr', timeout=60000)
            rows = await page.query_selector_all('table tbody tr')
            print_log(f"发现 {len(rows)} 个域名", important=True)
            
            for i, row in enumerate(rows, 1):
                domain = "未知域名"
                try:
                    domain_cell = await row.query_selector('td:nth-child(2)')
                    domain = (await domain_cell.inner_text()).strip() if domain_cell else "未知域名"
                    
                    renew_btn = await row.query_selector('button:has-text("Renew"), button:has-text("续期"), button:has-text("Prolong")')
                    
                    if not renew_btn:
                        report["skipped"].append(domain)
                        print_log(f"[{i}/{len(rows)}] {domain} - 无需续期", "warning")
                        continue

                    print_log(f"[{i}/{len(rows)}] {domain} - 正在续期...")
                    await renew_btn.click()
                    
                    try:
                        await page.wait_for_selector('text=确认', timeout=15000)
                        await page.click('text=确认')
                        await asyncio.sleep(3 + random.uniform(0, 1))
                        report["success"].append(domain)
                        print_log(f"[{i}/{len(rows)}] {domain} - 续期成功 ✅", important=True)
                    except Exception as e:
                        error_msg = f"确认按钮超时: {str(e)}"
                        print_log(f"[{i}/{len(rows)}] {domain} - {error_msg}", "error")
                        report["failed"].append(domain)
                        report["errors"].append(error_msg)

                except Exception as e:
                    error_msg = f"处理失败: {str(e)[:80]}"
                    print_log(f"[{i}/{len(rows)}] {domain} - {error_msg}", "error")
                    report["failed"].append(domain)
                    report["errors"].append(error_msg)
                    
        except Exception as e:
            error_msg = f"加载域名列表失败: {str(e)}"
            print_log(error_msg, "error")
            report["errors"].append(error_msg)
            
    except Exception as e:
        error_msg = f"续期流程异常: {str(e)}"
        print_log(error_msg, "error")
        report["errors"].append(error_msg)
        
    return report


async def main():
    start_time = time.time()
    
    # GHA 移植修改 4: 添加启动前配置校验
    if not CONFIG["email"] or not CONFIG["password"]:
        print_log("错误：DP_EMAIL 或 DP_PASSWORD 环境变量未设置！", "error", important=True)
        print_log("请在 GitHub Secrets 中设置 DP_EMAIL 和 DP_PASSWORD。", "error")
        exit(1) # 严重错误，直接退出
    
    print_log("DigitalPlat 自动续期脚本启动 (GHA 移植版)", important=True)
    
    for attempt in range(1, CONFIG["max_retries"] + 1):
        print_log(f"尝试 #{attempt}/{CONFIG['max_retries']}", important=True)
        playwright = None
        browser = None
        try:
            playwright, browser, context, page = await init_browser()
            report = {
                "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "attempt": attempt
            }
            
            if not await do_login(page):
                report["errors"] = ["登录失败"]
                raise Exception("登录失败")
                
            domain_report = await renew_domains(page)
            report.update(domain_report)
            
            # 生成TG报告
            if report.get("errors"):
                message = f"⚠️ *DigitalPlat 续期结果* ⚠️\n" \
                        f"⏱️ 时间: {report['start_time']}\n" \
                        f"🔄 尝试: {attempt}/{CONFIG['max_retries']}\n" \
                        f"✅ 成功: {len(report.get('success', []))}\n" \
                        f"⏭️ 跳过: {len(report.get('skipped', []))}\n" \
                        f"❌ 失败: {len(report.get('failed', []))}\n\n" \
                        f"最后错误: {report['errors'][-1][:200]}"
            else:
                message = f"✅ *DigitalPlat 续期成功* ✅\n" \
                        f"⏱️ 时间: {report['start_time']}\n" \
                        f"🔄 尝试次数: {attempt}\n" \
                        f"✔️ 成功: {len(report.get('success', []))}个\n" \
                        f"⏭️ 跳过: {len(report.get('skipped', []))}个"
                
                if report.get('success'):
                    message += "\n\n🎉 成功续期:\n" + "\n".join(f"• {d}" for d in report['success'][:5])
                    if len(report['success']) > 5:
                        message += f"\n...等 {len(report['success'])} 个域名"
            
            await tg_send(message)
            break
            
        except Exception as e:
            print_log(f"尝试 #{attempt} 失败: {str(e)}", "error")
            if 'page' in locals():
                # 捕获截图以供调试
                await page.screenshot(path=f"attempt_{attempt}_failed_screenshot.png")
                print_log(f"已保存失败截图: attempt_{attempt}_failed_screenshot.png", "debug")

            if attempt == CONFIG["max_retries"]:
                await tg_send(f"❌ *DigitalPlat 续期彻底失败* ❌\n" \
                             f"已重试 {CONFIG['max_retries']} 次\n" \
                             f"最后错误: {str(e)}\n" \
                             f"请立即手动检查!")
            await asyncio.sleep(30)
        finally:
            if 'browser' in locals() and browser:
                await browser.close()
            if 'playwright' in locals() and playwright:
                await playwright.stop()
            print_log(f"本次执行耗时: {time.time() - start_time:.1f}秒", "debug")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_log("收到终止信号，脚本停止", important=True)
    except Exception as e:
        print_log(f"脚本执行异常: {str(e)}", "error")
        # GHA 确保在主协程之外也能发送TG通知
        asyncio.run(tg_send(f"🔥 *续期脚本执行异常* 🔥\n错误: {str(e)}"))
    finally:
        print_log("脚本执行结束", important=True)
