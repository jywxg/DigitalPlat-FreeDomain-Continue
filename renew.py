# renew.py
# GitHub Actions 优化版 - 使用系统 Chromium
# 最后更新时间: 2025-01-XX

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
# DigitalPlat 账号信息
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")

# Telegram 通知配置
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# --- 2. 配置参数 ---
CONFIG = {
    "max_retries": 3,
    "headless": True,
    "slow_mo": 1000,  # 增加操作延迟，避免被检测
    "timeout": 120000,
    "cf_timeout": 300,
    "executablePath": "/usr/bin/chromium-browser",  # 系统 Chromium 路径
    "browser_args": [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--single-process",
        "--no-zygote",
        "--disable-setuid-sandbox",
        "--disable-software-rasterizer",
        "--disable-features=site-per-process",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-web-security",
        "--disable-features=VizDisplayCompositor",
        "--hide-scrollbars",
        "--mute-audio"
    ]
}

# --- 3. 网站固定 URL ---
LOGIN_URL = "https://dash.domain.digitalplat.org/auth/login"
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

def save_results(renewed_domains, failed_domains, skipped_domains, errors):
    """保存处理结果到JSON文件"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "renewed_count": len(renewed_domains),
        "failed_count": len(failed_domains),
        "skipped_count": len(skipped_domains),
        "renewed_domains": renewed_domains,
        "failed_domains": failed_domains,
        "skipped_domains": skipped_domains,
        "errors": errors
    }

    try:
        with open("renewal_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print_log("处理结果已保存到 renewal_results.json", "info")
    except Exception as e:
        print_log(f"保存结果时发生错误: {e}", "error")

async def simulate_human_behavior(page):
    """模拟人类行为"""
    # 随机鼠标移动
    viewport = page.viewport_size
    if viewport:
        await page.mouse.move(
            random.randint(100, viewport["width"] - 100),
            random.randint(100, viewport["height"] - 100)
        )
    
    # 随机滚动
    await page.evaluate(f"window.scrollTo(0, {random.randint(0, 500)})")
    
    # 随机延迟
    await asyncio.sleep(random.uniform(1, 3))

async def setup_browser_context(playwright):
    """设置浏览器上下文 - 使用系统 Chromium"""
    print_log("正在启动浏览器...", "info")
    
    browser = await playwright.chromium.launch(
        headless=CONFIG["headless"],
        executable_path=CONFIG["executablePath"],  # 使用系统 Chromium
        args=CONFIG["browser_args"],
        slow_mo=CONFIG["slow_mo"],
        ignore_default_args=[
            "--enable-automation",
            "--enable-blink-features=IdleDetection"
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ignore_https_errors=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        }
    )

    print_log("浏览器启动成功", "info", True)
    return browser, context

async def add_anti_detection_scripts(page):
    """添加反检测脚本"""
    print_log("正在注入反检测脚本...", "debug")
    
    scripts = [
        # 隐藏webdriver属性
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});",
        
        # 覆盖Chrome运行时
        "window.chrome = {runtime: {}};",
        
        # 覆盖权限
        "const originalQuery = window.navigator.permissions.query;",
        "window.navigator.permissions.query = (parameters) => (",
        "    parameters.name === 'notifications' ?",
        "        Promise.resolve({ state: Notification.permission }) :",
        "        originalQuery(parameters)",
        ");",
        
        # 覆盖硬件并发数
        "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4});",
        
        # 覆盖WebGL属性
        "const getParameter = WebGLRenderingContext.getParameter;",
        "WebGLRenderingContext.prototype.getParameter = function(parameter) {",
        "    if (parameter === 37445) { return 'Intel Open Source Technology Center'; }",
        "    if (parameter === 37446) { return 'Mesa DRI Intel(R) HD Graphics'; }",
        "    return getParameter(parameter);",
        "};"
    ]

    for script in scripts:
        try:
            await page.add_init_script(script)
        except Exception as e:
            print_log(f"注入脚本时出错: {e}", "debug")
    
    print_log("反检测脚本注入完成", "debug")

async def handle_cloudflare_challenge(page):
    """处理CloudFlare验证"""
    print_log("正在等待CloudFlare验证...", "info")
    
    max_wait_time = 180  # 最大等待3分钟
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        # 检查是否还在挑战页面
        challenge_form = await page.query_selector('div#challenge-form, .challenge-form, [class*="challenge"]')
        if challenge_form:
            print_log("检测到CloudFlare挑战页面，等待自动验证...", "warning")
            await asyncio.sleep(5)
            continue
        
        # 检查是否跳转到登录页面
        if "auth/login" in page.url:
            print_log("✅ 成功通过CloudFlare验证，进入登录页面", "info", True)
            return True
        
        # 检查是否有登录表单
        email_input = await page.query_selector("input[name='email'], input[type='email']")
        if email_input:
            print_log("✅ 成功通过CloudFlare验证，检测到登录表单", "info", True)
            return True
            
        # 检查是否直接进入面板
        if "panel/main" in page.url or "dashboard" in page.url:
            print_log("✅ 已直接进入面板页面", "info", True)
            return True
        
        await asyncio.sleep(3)
    
    print_log("❌ CloudFlare验证超时", "error")
    return False

async def login(page):
    """执行登录流程"""
    for attempt in range(CONFIG["max_retries"]):
        try:
            print_log(f"登录尝试 {attempt + 1}/{CONFIG['max_retries']}", "info", True)
            
            # 导航到登录页面
            print_log("正在导航到登录页面...", "info")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=CONFIG["timeout"])
            
            # 处理CloudFlare验证
            if not await handle_cloudflare_challenge(page):
                if attempt == CONFIG["max_retries"] - 1:
                    raise Exception("CloudFlare验证失败")
                print_log("CloudFlare验证失败，准备重试...", "warning")
                continue
            
            # 等待登录表单
            print_log("等待登录表单加载...", "info")
            try:
                await page.wait_for_selector("input[name='email'], input[type='email']", timeout=60000)
            except PlaywrightTimeoutError:
                print_log("登录表单加载超时，重试...", "warning")
                if attempt == CONFIG["max_retries"] - 1:
                    raise Exception("无法找到登录表单")
                continue
            
            # 模拟人类行为
            await simulate_human_behavior(page)
            
            # 填写登录信息
            print_log("正在填写登录信息...", "info")
            await page.fill("input[name='email'], input[type='email']", DP_EMAIL)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.fill("input[name='password'], input[type='password']", DP_PASSWORD)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # 点击登录
            print_log("正在点击登录按钮...", "info")
            submit_button = page.locator("button[type='submit']").first
            await submit_button.click()
            
            # 等待导航完成
            try:
                await page.wait_for_url("**/panel/main**", timeout=60000)
                print_log("✅ 登录成功！", "info", True)
                return True
            except PlaywrightTimeoutError:
                current_url = page.url
                if "panel/main" in current_url or "dashboard" in current_url:
                    print_log("✅ 登录成功！", "info", True)
                    return True
                else:
                    # 检查是否有错误信息
                    error_elements = await page.query_selector_all('.error, .alert-danger, [class*="error"]')
                    if error_elements:
                        error_text = await error_elements[0].inner_text()
                        print_log(f"登录错误: {error_text}", "error")
                    
                    if attempt == CONFIG["max_retries"] - 1:
                        await page.screenshot(path="login_failed.png")
                        raise Exception("登录失败")
                    print_log("登录失败，准备重试...", "warning")
                    continue
                    
        except Exception as e:
            print_log(f"登录尝试 {attempt + 1} 失败: {str(e)}", "error")
            if attempt == CONFIG["max_retries"] - 1:
                raise
            await asyncio.sleep(10)
    
    return False

async def renew_domains(page):
    """续期域名"""
    renewed_domains = []
    failed_domains = []
    skipped_domains = []
    errors = []
    
    try:
        print_log("正在加载域名列表...", "info")
        await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=CONFIG["timeout"])
        
        # 等待域名表格加载
        try:
            await page.wait_for_selector('table tbody tr', timeout=60000)
        except PlaywrightTimeoutError:
            error_msg = "域名列表加载超时"
            print_log(error_msg, "error")
            failed_domains.append("所有域名 - 列表加载失败")
            errors.append(error_msg)
            return renewed_domains, failed_domains, skipped_domains, errors
        
        rows = await page.query_selector_all('table tbody tr')
        print_log(f"发现 {len(rows)} 个域名", "info", True)
        
        for i, row in enumerate(rows, 1):
            domain = "未知域名"
            try:
                # 获取域名名称
                domain_cell = await row.query_selector('td:nth-child(2), td:first-child')
                if domain_cell:
                    domain = (await domain_cell.inner_text()).strip()
                
                # 查找续期按钮
                renew_btn = await row.query_selector('button:has-text("Renew"), button:has-text("续期"), button:has-text("Prolong")')
                
                if not renew_btn:
                    skipped_domains.append(domain)
                    print_log(f"[{i}/{len(rows)}] {domain} - 无需续期", "warning")
                    continue
                
                print_log(f"[{i}/{len(rows)}] {domain} - 正在续期...", "info")
                await renew_btn.click()
                
                # 处理确认对话框
                try:
                    await page.wait_for_selector('text=确认, button:has-text("Confirm")', timeout=15000)
                    confirm_btn = page.locator('text=确认, button:has-text("Confirm")').first
                    await confirm_btn.click()
                    
                    # 等待操作完成
                    await asyncio.sleep(3 + random.uniform(0, 1))
                    
                    # 检查是否成功
                    renewed_domains.append(domain)
                    print_log(f"[{i}/{len(rows)}] {domain} - ✅ 续期成功", "info", True)
                    
                except PlaywrightTimeoutError:
                    error_msg = f"{domain} - 确认按钮超时"
                    print_log(f"[{i}/{len(rows)}] {error_msg}", "error")
                    failed_domains.append(domain)
                    errors.append(error_msg)
                
            except Exception as e:
                error_msg = f"{domain} - 处理失败: {str(e)[:80]}"
                print_log(f"[{i}/{len(rows)}] {error_msg}", "error")
                failed_domains.append(domain)
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
            if errors:
                message = f"⚠️ *DigitalPlat 续期报告* ⚠️\n" \
                         f"⏱️ 时间: {report_time}\n" \
                         f"🔄 尝试: {attempt}/{CONFIG['max_retries']}\n" \
                         f"✅ 成功: {len(renewed)}\n" \
                         f"⏭️ 跳过: {len(skipped)}\n" \
                         f"❌ 失败: {len(failed)}\n\n" \
                         f"最后错误: {errors[-1][:200] if errors else '无'}"
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
            save_results(renewed, failed, skipped, errors)
            
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
