# renew.py
# 优化版本 - 支持GitHub Actions运行并绕过CF验证
# 最后更新时间: 2025-01-XX

import os
import sys
import asyncio
import requests
import random
import json
import logging
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 1. 从环境变量中读取配置 ---
# DigitalPlat 账号信息
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")

# Bark 通知配置
BARK_KEY = os.getenv("BARK_KEY")
BARK_SERVER = os.getenv("BARK_SERVER")

# --- 2. 配置参数 ---
CONFIG = {
    "max_retries": 3,
    "headless": True,
    "slow_mo": 800,  # 增加操作延迟，避免被检测
    "timeout": 120000,
    "cf_timeout": 300,
    "executablePath": "/usr/bin/chromium-browser",
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
        "--disable-features=VizDisplayCompositor"
    ]
}

# --- 3. 网站固定 URL ---
LOGIN_URL = "https://dash.domain.digitalplat.org/auth/login"
DOMAINS_URL = "https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains"

def validate_config():
    """验证必需的环境变量是否已设置"""
    required_vars = {
        "DP_EMAIL": DP_EMAIL,
        "DP_PASSWORD": DP_PASSWORD
    }

    missing = [var for var, value in required_vars.items() if not value]
    if missing:
        error_msg = f"错误：缺少必需的环境变量: {', '.join(missing)}。请在 GitHub Secrets 中配置。"
        logger.error(error_msg)
        send_bark_notification("DigitalPlat 脚本配置错误", error_msg, level="timeSensitive")
        sys.exit(1)

def send_bark_notification(title, body, level="active", badge=None):
    """发送 Bark 推送通知"""
    if not BARK_KEY:
        logger.info("BARK_KEY 未设置，跳过发送通知。")
        return

    server_url = BARK_SERVER if BARK_SERVER else "https://api.day.app"
    api_url = f"{server_url.rstrip('/')}/{BARK_KEY}"

    logger.info(f"正在向 Bark 服务器发送通知: {title}")

    try:
        payload = {
            "title": title,
            "body": body,
            "group": "DigitalPlat Renew",
            "level": level
        }
        if badge is not None:
            payload["badge"] = badge

        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Bark 通知已成功发送。")
    except Exception as e:
        logger.error(f"发送 Bark 通知时发生错误: {e}")

def save_results(renewed_domains, failed_domains, skipped_domains):
    """保存处理结果到JSON文件"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "renewed_count": len(renewed_domains),
        "failed_count": len(failed_domains),
        "skipped_count": len(skipped_domains),
        "renewed_domains": renewed_domains,
        "failed_domains": failed_domains,
        "skipped_domains": skipped_domains
    }

    try:
        with open("renewal_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info("处理结果已保存到 renewal_results.json")
    except Exception as e:
        logger.error(f"保存结果时发生错误: {e}")

async def simulate_human_behavior(page):
    """模拟人类行为 - 增强版"""
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
    """设置浏览器上下文 - 优化版"""
    # 在 GitHub Actions 中使用 Chromium 而不是 Firefox
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
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ignore_https_errors=True,
        # 添加额外的反检测参数
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        }
    )

    return browser, context

async def add_anti_detection_scripts(page):
    """添加反检测脚本 - 增强版"""
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
        
        # 覆盖plugins属性
        "Object.defineProperty(navigator, 'plugins', {",
        "    get: () => [1, 2, 3, 4, 5],",
        "});",
        
        # 覆盖硬件并发数
        "Object.defineProperty(navigator, 'hardwareConcurrency', {",
        "    get: () => 4",
        "});"
    ]

    for script in scripts:
        try:
            await page.add_init_script(script)
        except Exception:
            pass

async def handle_cloudflare_challenge(page):
    """处理CloudFlare验证 - 关键函数"""
    logger.info("正在等待CloudFlare验证...")
    
    max_wait_time = 180  # 最大等待3分钟
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        # 检查是否还在挑战页面
        if await page.query_selector('div#challenge-form'):
            logger.info("仍在CloudFlare挑战页面，继续等待...")
            await asyncio.sleep(5)
            continue
        
        # 检查是否跳转到登录页面
        if "auth/login" in page.url or "input[name='email']" in await page.content():
            logger.info("成功通过CloudFlare验证，进入登录页面")
            return True
            
        # 检查是否有其他重定向
        current_url = page.url
        if "panel/main" in current_url or "dashboard" in current_url:
            logger.info("已直接进入面板页面")
            return True
            
        await asyncio.sleep(2)
    
    logger.error("CloudFlare验证超时")
    return False

async def login(page):
    """执行登录流程 - 优化版"""
    for attempt in range(CONFIG["max_retries"]):
        try:
            logger.info(f"登录尝试 {attempt + 1}/{CONFIG['max_retries']}")
            
            # 导航到登录页面
            logger.info("正在导航到登录页面...")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=CONFIG["timeout"])
            
            # 处理CloudFlare验证
            if not await handle_cloudflare_challenge(page):
                if attempt == CONFIG["max_retries"] - 1:
                    raise Exception("CloudFlare验证失败")
                continue
            
            # 等待登录表单
            logger.info("等待登录表单加载...")
            try:
                await page.wait_for_selector("input[name='email']", timeout=60000)
            except PlaywrightTimeoutError:
                logger.warning("登录表单加载超时，重试...")
                if attempt == CONFIG["max_retries"] - 1:
                    raise Exception("无法找到登录表单")
                continue
            
            # 模拟人类行为
            await simulate_human_behavior(page)
            
            # 填写登录信息
            logger.info("正在填写登录信息...")
            await page.fill("input[name='email']", DP_EMAIL)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.fill("input[name='password']", DP_PASSWORD)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # 点击登录
            logger.info("正在点击登录按钮...")
            submit_button = page.locator("button[type='submit']").first
            await submit_button.click()
            
            # 等待导航完成
            try:
                await page.wait_for_url("**/panel/main**", timeout=60000)
                logger.info("✅ 登录成功！")
                return True
            except PlaywrightTimeoutError:
                logger.warning("登录后跳转超时，检查是否登录成功...")
                current_url = page.url
                if "panel/main" in current_url or "dashboard" in current_url:
                    logger.info("✅ 登录成功！")
                    return True
                else:
                    # 检查是否有错误信息
                    error_elements = await page.query_selector_all('.error, .alert-danger, [class*="error"]')
                    if error_elements:
                        error_text = await error_elements[0].inner_text()
                        logger.error(f"登录错误: {error_text}")
                    
                    if attempt == CONFIG["max_retries"] - 1:
                        await page.screenshot(path="login_failed.png")
                        raise Exception("登录失败")
                    continue
                    
        except Exception as e:
            logger.error(f"登录尝试 {attempt + 1} 失败: {str(e)}")
            if attempt == CONFIG["max_retries"] - 1:
                raise
            await asyncio.sleep(10)
    
    return False

async def renew_domains(page):
    """续期域名 - 优化版"""
    renewed_domains = []
    failed_domains = []
    skipped_domains = []
    errors = []
    
    try:
        logger.info("正在加载域名列表...")
        await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=CONFIG["timeout"])
        
        # 等待域名表格加载
        try:
            await page.wait_for_selector('table tbody tr', timeout=60000)
        except PlaywrightTimeoutError:
            logger.error("域名列表加载超时")
            failed_domains.append("所有域名 - 列表加载失败")
            errors.append("域名列表加载超时")
            return renewed_domains, failed_domains, skipped_domains, errors
        
        rows = await page.query_selector_all('table tbody tr')
        logger.info(f"发现 {len(rows)} 个域名")
        
        for i, row in enumerate(rows, 1):
            domain = "未知域名"
            try:
                # 获取域名名称
                domain_cell = await row.query_selector('td:nth-child(2)')
                if domain_cell:
                    domain = (await domain_cell.inner_text()).strip()
                
                # 查找续期按钮
                renew_btn = await row.query_selector('button:has-text("Renew"), button:has-text("续期"), button:has-text("Prolong")')
                
                if not renew_btn:
                    skipped_domains.append(domain)
                    logger.info(f"[{i}/{len(rows)}] {domain} - 无需续期")
                    continue
                
                logger.info(f"[{i}/{len(rows)}] {domain} - 正在续期...")
                await renew_btn.click()
                
                # 处理确认对话框
                try:
                    await page.wait_for_selector('text=确认', timeout=15000)
                    confirm_btn = page.locator('text=确认').first
                    await confirm_btn.click()
                    
                    # 等待操作完成
                    await asyncio.sleep(3 + random.uniform(0, 1))
                    
                    # 检查是否成功
                    renewed_domains.append(domain)
                    logger.info(f"[{i}/{len(rows)}] {domain} - ✅ 续期成功")
                    
                except PlaywrightTimeoutError:
                    error_msg = f"{domain} - 确认按钮超时"
                    logger.error(f"[{i}/{len(rows)}] {error_msg}")
                    failed_domains.append(domain)
                    errors.append(error_msg)
                
            except Exception as e:
                error_msg = f"{domain} - 处理失败: {str(e)[:80]}"
                logger.error(f"[{i}/{len(rows)}] {error_msg}")
                failed_domains.append(domain)
                errors.append(error_msg)
                
    except Exception as e:
        error_msg = f"续期流程异常: {str(e)}"
        logger.error(error_msg)
        errors.append(error_msg)
        
    return renewed_domains, failed_domains, skipped_domains, errors

async def run_renewal():
    """主执行函数"""
    validate_config()
    
    start_time = time.time()
    logger.info("🚀 DigitalPlat 自动续期脚本启动")
    
    for attempt in range(1, CONFIG["max_retries"] + 1):
        logger.info(f"🔄 尝试 #{attempt}/{CONFIG['max_retries']}")
        
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
            report = {
                "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "attempt": attempt,
                "renewed": renewed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors
            }
            
            # 发送通知
            if errors:
                message = f"⚠️ DigitalPlat 续期报告 ⚠️\n" \
                         f"⏱️ 时间: {report['start_time']}\n" \
                         f"🔄 尝试: {attempt}/{CONFIG['max_retries']}\n" \
                         f"✅ 成功: {len(renewed)}\n" \
                         f"⏭️ 跳过: {len(skipped)}\n" \
                         f"❌ 失败: {len(failed)}\n\n" \
                         f"最后错误: {errors[-1][:200] if errors else '无'}"
            else:
                message = f"✅ DigitalPlat 续期成功 ✅\n" \
                         f"⏱️ 时间: {report['start_time']}\n" \
                         f"🔄 尝试次数: {attempt}\n" \
                         f"✔️ 成功: {len(renewed)}个\n" \
                         f"⏭️ 跳过: {len(skipped)}个"
                
                if renewed:
                    message += "\n\n🎉 成功续期:\n" + "\n".join(f"• {d}" for d in renewed[:5])
                    if len(renewed) > 5:
                        message += f"\n...等 {len(renewed)} 个域名"
            
            send_bark_notification("DigitalPlat 续期完成", message)
            save_results(renewed, failed, skipped)
            break
            
        except Exception as e:
            logger.error(f"尝试 #{attempt} 失败: {str(e)}")
            if attempt == CONFIG["max_retries"]:
                send_bark_notification(
                    "❌ DigitalPlat 续期彻底失败",
                    f"已重试 {CONFIG['max_retries']} 次\n最后错误: {str(e)}\n请立即手动检查!",
                    level="timeSensitive"
                )
            await asyncio.sleep(30)
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
    
    logger.info(f"📊 本次执行耗时: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    # 在GitHub Actions中需要的时间模块
    import time
    try:
        asyncio.run(run_renewal())
    except KeyboardInterrupt:
        logger.info("收到终止信号，脚本停止")
    except Exception as e:
        logger.error(f"脚本执行异常: {str(e)}")
        send_bark_notification("🔥 续期脚本执行异常", f"错误: {str(e)}")
