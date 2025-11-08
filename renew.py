# renew.py
# 基于成功经验优化的版本

import os
import sys
import asyncio
import requests
import random
import json
import logging
import time
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('renewal.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# --- 1. 从环境变量中读取配置 ---
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# --- 2. 配置参数 - 使用成功脚本的参数 ---
CONFIG = {
    "max_retries": 3,
    "headless": True,
    "slow_mo": 500,    # 使用成功脚本的延迟
    "timeout": 120000, # 使用成功脚本的超时
    "executablePath": "/usr/bin/chromium-browser",
    "browser_args": [   # 使用成功脚本的参数
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

# --- 3. 使用成功的URL ---
LOGIN_URL = "https://dash.domain.digitalplat.org/login"  # 关键：使用成功的URL
DOMAINS_URL = "https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains"

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
    """彩色日志输出"""
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
    
    log_message = f"{Color.WHITE}[{timestamp}]{Color.END} {color}{prefix}:{Color.END} {message}"
    print(log_message)
    logger.info(f"{prefix}: {message}")

def validate_config():
    """验证必需的环境变量是否已设置"""
    required_vars = {
        "DP_EMAIL": DP_EMAIL,
        "DP_PASSWORD": DP_PASSWORD
    }

    missing = [var for var, value in required_vars.items() if not value]
    if missing:
        error_msg = f"错误：缺少必需的环境变量: {', '.join(missing)}。请在 GitHub Secrets 中配置。"
        print_log(error_msg, "error")
        send_telegram_notification("DigitalPlat 脚本配置错误", error_msg)
        sys.exit(1)
    
    print_log("环境变量验证通过", "info", True)

def send_telegram_notification(title, body):
    """发送 Telegram 推送通知"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print_log("TG_TOKEN 或 TG_CHAT_ID 未设置，跳过发送通知", "debug")
        return

    try:
        message = f"*{title}*\n\n{body}"
        
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        params = {
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=params, timeout=15)
        response.raise_for_status()
        print_log("Telegram 通知已成功发送", "info")
    except Exception as e:
        print_log(f"发送 Telegram 通知时发生错误: {e}", "error")

async def setup_browser_context(playwright):
    """设置浏览器上下文 - 使用成功脚本的方法"""
    print_log("正在启动浏览器...", "info")
    
    browser = await playwright.chromium.launch(
        headless=CONFIG["headless"],
        executable_path=CONFIG["executablePath"],
        args=CONFIG["browser_args"],
        slow_mo=CONFIG["slow_mo"],
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

    print_log("浏览器启动成功", "info", True)
    return browser, context

async def login(page):
    """登录流程 - 完全复制成功脚本的方法"""
    try:
        print_log("正在访问登录页面...", "info")
        await page.goto(LOGIN_URL, timeout=CONFIG["timeout"])
        
        # 处理可能的验证 - 关键：直接复制成功的方法
        try:
            await page.wait_for_selector('input[name="email"]', timeout=60000)
        except Exception as e:
            if await page.query_selector('div#challenge-form'):
                print_log("可能需要人工验证，尝试自动处理...", "warning")
                await asyncio.sleep(10)
                if await page.query_selector('div#challenge-form'):
                    raise Exception("检测到需要人工验证")

        print_log("正在填写登录表单...", "info")
        await page.fill('input[name="email"]', DP_EMAIL)
        await page.fill('input[name="password"]', DP_PASSWORD)
        await page.click('button[type="submit"]')
        
        try:
            await page.wait_for_url("**/panel/main**", timeout=60000)
            print_log("登录成功", "info", True)
            return True
        except Exception as e:
            print_log(f"登录状态验证失败: {str(e)}", "error")
            return False
            
    except Exception as e:
        print_log(f"登录流程异常: {str(e)}", "error")
        return False

async def renew_domains(page):
    """续期域名 - 使用成功脚本的方法"""
    renewed_domains = []
    failed_domains = []
    skipped_domains = []
    errors = []
    
    try:
        print_log("正在加载域名列表...", "info")
        await page.goto(DOMAINS_URL, timeout=CONFIG["timeout"])
        
        try:
            await page.wait_for_selector('table tbody tr', timeout=60000)
            rows = await page.query_selector_all('table tbody tr')
            print_log(f"发现 {len(rows)} 个域名", "info", True)
            
            for i, row in enumerate(rows, 1):
                domain = "未知域名"
                try:
                    domain_cell = await row.query_selector('td:nth-child(2)')
                    domain = (await domain_cell.inner_text()).strip() if domain_cell else "未知域名"
                    
                    renew_btn = await row.query_selector('button:has-text("Renew"), button:has-text("续期"), button:has-text("Prolong")')
                    
                    if not renew_btn:
                        skipped_domains.append(domain)
                        print_log(f"[{i}/{len(rows)}] {domain} - 无需续期", "warning")
                        continue

                    print_log(f"[{i}/{len(rows)}] {domain} - 正在续期...", "info")
                    await renew_btn.click()
                    
                    try:
                        await page.wait_for_selector('text=确认', timeout=15000)
                        await page.click('text=确认')
                        await asyncio.sleep(3 + random.uniform(0, 1))
                        renewed_domains.append(domain)
                        print_log(f"[{i}/{len(rows)}] {domain} - 续期成功 ✅", "info", True)
                    except Exception as e:
                        error_msg = f"确认按钮超时: {str(e)}"
                        print_log(f"[{i}/{len(rows)}] {domain} - {error_msg}", "error")
                        failed_domains.append(domain)
                        errors.append(error_msg)

                except Exception as e:
                    error_msg = f"处理失败: {str(e)[:80]}"
                    print_log(f"[{i}/{len(rows)}] {domain} - {error_msg}", "error")
                    failed_domains.append(domain)
                    errors.append(error_msg)
                    
        except Exception as e:
            error_msg = f"加载域名列表失败: {str(e)}"
            print_log(error_msg, "error")
            errors.append(error_msg)
            
    except Exception as e:
        error_msg = f"续期流程异常: {str(e)}"
        print_log(error_msg, "error")
        errors.append(error_msg)
        
    return renewed_domains, failed_domains, skipped_domains, errors

async def run_renewal():
    """主执行函数"""
    validate_config()
    
    start_time = time.time()
    print_log("🚀 DigitalPlat 自动续期脚本启动", "info", True)
    
    for attempt in range(1, CONFIG["max_retries"] + 1):
        print_log(f"🔄 尝试 #{attempt}/{CONFIG['max_retries']}", "info", True)
        
        playwright = None
        browser = None
        
        try:
            # 初始化浏览器
            playwright = await async_playwright().start()
            browser, context = await setup_browser_context(playwright)
            page = await context.new_page()
            
            # 登录
            if not await login(page):
                raise Exception("登录失败")
                
            # 执行续期
            renewed, failed, skipped, errors = await renew_domains(page)
            
            # 生成报告
            report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 发送通知
            if errors or failed:
                message = f"⚠️ *DigitalPlat 续期报告* ⚠️\n" \
                         f"⏱️ 时间: {report_time}\n" \
                         f"🔄 尝试: {attempt}/{CONFIG['max_retries']}\n" \
                         f"✅ 成功: {len(renewed)}\n" \
                         f"⏭️ 跳过: {len(skipped)}\n" \
                         f"❌ 失败: {len(failed)}\n\n" \
                         f"错误信息: {errors[0][:200] if errors else '无'}"
            else:
                message = f"✅ *DigitalPlat 续期成功* ✅\n" \
                         f"⏱️ 时间: {report_time}\n" \
                         f"🔄 尝试次数: {attempt}\n" \
                         f"✔️ 成功: {len(renewed)}个\n" \
                         f"⏭️ 跳过: {len(skipped)}个"
                
                if renewed:
                    message += "\n\n🎉 成功续期:\n" + "\n".join(f"• {d}" for d in renewed[:5])
                    if len(renewed) > 5:
                        message += f"\n...等 {len(renewed)} 个域名"
            
            send_telegram_notification("DigitalPlat 续期完成", message)
            
            print_log(f"📊 续期完成 - 成功: {len(renewed)}, 跳过: {len(skipped)}, 失败: {len(failed)}", "info", True)
            break
            
        except Exception as e:
            print_log(f"尝试 #{attempt} 失败: {str(e)}", "error")
            if attempt == CONFIG["max_retries"]:
                send_telegram_notification(
                    "❌ DigitalPlat 续期彻底失败",
                    f"已重试 {CONFIG['max_retries']} 次\n最后错误: {str(e)}\n请立即手动检查!"
                )
            await asyncio.sleep(30)
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
    
    total_time = time.time() - start_time
    print_log(f"📊 本次执行耗时: {total_time:.1f}秒", "info", True)

if __name__ == "__main__":
    try:
        asyncio.run(run_renewal())
    except KeyboardInterrupt:
        print_log("收到终止信号，脚本停止", "info", True)
    except Exception as e:
        print_log(f"脚本执行异常: {str(e)}", "error")
        send_telegram_notification("🔥 续期脚本执行异常", f"错误: {str(e)}")
    finally:
        print_log("脚本执行结束", "info", True)
