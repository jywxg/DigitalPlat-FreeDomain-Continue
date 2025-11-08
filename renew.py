# renew.py
# 增强版 - 解决 CloudFlare 验证问题

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

# --- 配置参数 ---
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

CONFIG = {
    "max_retries": 5,  # 增加重试次数
    "headless": True,
    "slow_mo": 2000,   # 增加延迟，更像人类
    "timeout": 180000,
    "browser_args": [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=VizDisplayCompositor",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-popup-blocking",
        "--disable-translate",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-client-side-phishing-detection",
        "--disable-crash-reporter",
        "--disable-ipc-flooding-protection",
        "--disable-hang-monitor",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-sync",
        "--disable-web-resources",
        "--disable-logging",
        "--disable-software-rasterizer",
        "--disable-features=site-per-process",
        "--disable-breakpad",
        "--ignore-certificate-errors",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-zygote",
        "--window-size=1920,1080"
    ]
}

LOGIN_URL = "https://dash.domain.digitalplat.org/login"
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
    """设置浏览器上下文 - 增强反检测"""
    print_log("正在启动浏览器...", "info")
    
    # 更真实的用户代理列表
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
    ]
    
    browser = await playwright.chromium.launch(
        headless=CONFIG["headless"],
        args=CONFIG["browser_args"],
        slow_mo=CONFIG["slow_mo"],
        ignore_default_args=[
            "--enable-automation",
            "--enable-blink-features=IdleDetection",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding"
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=random.choice(user_agents),
        ignore_https_errors=True,
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1"
        }
    )

    print_log("浏览器启动成功", "info", True)
    return browser, context

async def add_anti_detection_scripts(page):
    """增强反检测脚本"""
    print_log("正在注入反检测脚本...", "debug")
    
    scripts = [
        # 隐藏webdriver属性
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        
        # 覆盖plugins和languages
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'zh-CN', 'zh']});",
        
        # 覆盖Chrome运行时
        "window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};",
        
        # 覆盖权限
        "const originalQuery = window.navigator.permissions.query;",
        "window.navigator.permissions.query = (parameters) => (",
        "    parameters.name === 'notifications' ?",
        "        Promise.resolve({ state: Notification.permission }) :",
        "        originalQuery(parameters)",
        ");",
        
        # 覆盖硬件信息
        "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});",
        "Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});",
        
        # WebGL指纹覆盖
        "const getParameter = WebGLRenderingContext.getParameter;",
        "WebGLRenderingContext.prototype.getParameter = function(parameter) {",
        "    if (parameter === 37445) { return 'Intel Open Source Technology Center'; }",
        "    if (parameter === 37446) { return 'Mesa DRI Intel(R) HD Graphics'; }",
        "    return getParameter(parameter);",
        "};",
        
        # 删除自动化痕迹
        "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;",
        "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;",
        "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;",
        "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Object;",
        "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Proxy;",
        
        # 覆盖WebDriver属性
        "if (window.navigator.chrome) {",
        "    Object.defineProperty(navigator, 'chrome', {",
        "        get: () => undefined,",
        "    });",
        "}"
    ]

    for script in scripts:
        try:
            await page.add_init_script(script)
        except Exception as e:
            print_log(f"注入脚本时出错: {e}", "debug")
    
    print_log("反检测脚本注入完成", "debug")

async def handle_cloudflare(page):
    """处理CloudFlare验证 - 增强版"""
    print_log("正在处理CloudFlare验证...", "info")
    
    max_wait = 180  # 最大等待3分钟
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        current_url = page.url
        page_content = await page.content()
        
        # 检查是否在CloudFlare挑战页面
        if any(indicator in current_url.lower() or indicator in page_content.lower() 
               for indicator in ['challenge', 'cf-', 'ray_id', 'ddos', 'just a moment']):
            
            print_log("检测到CloudFlare挑战页面，等待验证...", "warning")
            
            # 模拟人类行为：随机移动鼠标和滚动
            viewport = page.viewport_size
            if viewport:
                await page.mouse.move(
                    random.randint(100, viewport["width"] - 100),
                    random.randint(100, viewport["height"] - 100)
                )
                await page.mouse.wheel(0, random.randint(100, 300))
            
            await asyncio.sleep(5)
            
        # 检查是否通过验证
        elif any(indicator in current_url.lower() 
                for indicator in ['login', 'auth', 'signin']):
            print_log("✅ CloudFlare验证通过", "info", True)
            return True
            
        # 检查是否直接进入面板
        elif 'panel' in current_url or 'dashboard' in current_url:
            print_log("✅ 已直接进入面板", "info", True)
            return True
            
        else:
            print_log(f"当前页面: {current_url}", "debug")
            await asyncio.sleep(3)
    
    print_log("❌ CloudFlare验证超时", "error")
    return False

async def login(page):
    """登录流程 - 增强版"""
    for attempt in range(CONFIG["max_retries"]):
        try:
            print_log(f"登录尝试 {attempt + 1}/{CONFIG['max_retries']}", "info", True)
            
            # 访问登录页面
            print_log("正在访问登录页面...", "info")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=CONFIG["timeout"])
            
            # 处理CloudFlare验证
            if not await handle_cloudflare(page):
                if attempt == CONFIG["max_retries"] - 1:
                    raise Exception("CloudFlare验证失败")
                print_log("CloudFlare验证失败，准备重试...", "warning")
                continue
            
            # 等待登录表单
            print_log("等待登录表单加载...", "info")
            try:
                await page.wait_for_selector('input[name="email"]', timeout=60000)
            except Exception as e:
                if await page.query_selector('div#challenge-form'):
                    print_log("可能需要人工验证，尝试自动处理...", "warning")
                    await asyncio.sleep(10)
                    if await page.query_selector('div#challenge-form'):
                        raise Exception("检测到需要人工验证")
                raise e

            print_log("正在填写登录表单...", "info")
            await page.fill('input[name="email"]', DP_EMAIL)
            await asyncio.sleep(random.uniform(1, 2))
            await page.fill('input[name="password"]', DP_PASSWORD)
            await asyncio.sleep(random.uniform(1, 2))
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
            if attempt == CONFIG["max_retries"] - 1:
                raise
            await asyncio.sleep(10)
    
    return False

# renew_domains 和 run_renewal 函数保持不变
# [保持你之前成功的 renew_domains 和 run_renewal 函数]

async def renew_domains(page):
    """续期域名"""
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
            
            # 添加反检测
            await add_anti_detection_scripts(page)
            
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
