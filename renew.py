# renew.py
# 最后更新时间: 2025-11-08 (已移除 stealth，添加代理支持)
# 这是一个集成了所有功能的完整版本脚本

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
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")
BARK_KEY = os.getenv("BARK_KEY")
BARK_SERVER = os.getenv("BARK_SERVER")
# vvvvvvvvvvvv 新增代理配置 vvvvvvvvvvvv
PROXY_URL = os.getenv("PROXY_URL") # 格式: http://user:pass@host:port 或 socks5://user:pass@host:port
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

# --- 2. 网站固定 URL ---
LOGIN_URL = "https://dash.domain.digitalplat.org/auth/login"
DOMAINS_URL = "https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains"

# --- 3. 超时配置 ---
TIMEOUTS = {
    "page_load": 60000,
    "element_wait": 30000,
    "navigation": 60000,
    "login_wait": 180000
}

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
    
    if PROXY_URL:
        logger.info("检测到代理配置，将使用代理服务器。")
    else:
        logger.info("未检测到代理配置，将直接连接。")

def send_bark_notification(title, body, level="active", badge=None):
    """发送 Bark 推送通知"""
    if not BARK_KEY:
        logger.info("BARK_KEY 未设置，跳过发送通知。")
        return

    server_url = BARK_SERVER if BARK_SERVER else "https://api.day.app"
    api_url = f"{server_url.rstrip('/')}/{BARK_KEY}"
    logger.info(f"正在向 Bark 服务器 {server_url} 发送通知: {title}")

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
    except requests.exceptions.RequestException as e:
        logger.error(f"发送 Bark 通知时发生网络错误: {e}")
    except Exception as e:
        logger.error(f"发送 Bark 通知时发生未知错误: {e}")

def save_results(renewed_domains, failed_domains):
    """保存处理结果到JSON文件"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "renewed_count": len(renewed_domains),
        "failed_count": len(failed_domains),
        "renewed_domains": renewed_domains,
        "failed_domains": failed_domains
    }

    try:
        with open("renewal_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info("处理结果已保存到 renewal_results.json")
    except Exception as e:
        logger.error(f"保存结果时发生错误: {e}")

async def retry_operation(operation, max_retries=3, delay=2):
    """重试操作的通用函数"""
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"操作失败，{delay}秒后重试... (尝试 {attempt + 1}/{max_retries})")
            await asyncio.sleep(delay)

async def simulate_human_behavior(page):
    """模拟人类行为"""
    await page.mouse.move(
        random.randint(100, 500),
        random.randint(100, 500)
    )
    await asyncio.sleep(random.uniform(0.5, 2))

async def setup_browser_context(playwright):
    """
    设置浏览器上下文
    (回到 Headless=True, 并添加代理)
    """
    
    # 借鉴自 domains.py 的成功启动参数
    browser_args = [
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--single-process',
        '--no-zygote',
        '--disable-setuid-sandbox',
        '--disable-software-rasterizer',
        '--disable-features=site-per-process',
        '--disable-breakpad',
        '--disable-client-side-phishing-detection',
        '--window-size=1920,1080',
    ]

    # vvvvvvvvvvvv 代理设置 vvvvvvvvvvvv
    proxy_settings = None
    if PROXY_URL:
        proxy_settings = {
            "server": PROXY_URL
        }
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    browser = await playwright.chromium.launch(
        headless=True, # <-- 还原回 True
        args=browser_args,
        proxy=proxy_settings, # <-- 应用代理
        ignore_default_args=[
            "--enable-automation",
            "--enable-blink-features=IdleDetection"
        ]
    )

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )

    return browser, context

async def add_anti_detection_scripts(page):
    """添加反检测脚本"""
    scripts = [
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        "window.navigator.chrome = { runtime: {} };",
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
    ]

    for script in scripts:
        await page.add_init_script(script)

async def login(page):
    """执行登录流程"""
    logger.info("正在导航到登录页面...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUTS["page_load"])

    await simulate_human_behavior(page)

    logger.info("等待人机验证页(5秒盾)自动跳转到登录表单...")
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            await page.wait_for_selector("input[name='email']", timeout=TIMEOUTS["login_wait"])
            logger.info("检测到登录表单，已进入账号密码输入页面。")
            break
        except PlaywrightTimeoutError:
            logger.warning(f"尝试 {attempt + 1} 失败：在180秒内未检测到登录输入框。")
            if attempt == max_attempts - 1:
                logger.error("所有尝试均失败，退出。")
                await page.screenshot(path="login_timeout_error.png")
                with open("login_timeout_page_source.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                send_bark_notification(
                    "DigitalPlat 登录失败",
                    "多次尝试后未能跳过人机验证，请检查截图和页面源代码。",
                    level="timeSensitive"
                )
                raise Exception("登录失败：无法跳过人机验证")
            
            logger.info("刷新页面重试...")
            await page.reload(wait_until="domcontentloaded", timeout=TIMEOUTS["page_load"])
            await asyncio.sleep(5)

    logger.info("正在填写登录信息...")
    await page.type("input[name='email']", DP_EMAIL, delay=random.randint(50, 150))
    await page.type("input[name='password']", DP_PASSWORD, delay=random.randint(50, 150))

    logger.info("正在点击登录按钮...")
    async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
        await page.click("button[type='submit']")

    if "/panel/main" not in page.url:
        logger.error(f"登录失败，当前URL为: {page.url}")
        await page.screenshot(path="login_failed_error.png")
        send_bark_notification(
            "DigitalPlat 登录失败",
            "点击登录后未能跳转到预期的仪表盘页面。",
            level="timeSensitive"
        )
        raise Exception("登录失败：未能跳转到仪表盘")

    logger.info("登录成功！已进入用户仪表盘。")

async def process_domain(page, domain_name, domain_url_path, base_url):
    """处理单个域名的续期"""
    try:
        full_domain_url = base_url + domain_url_path
        logger.info(f"正在访问 {domain_name} 的管理页面: {full_domain_url}")
        await page.goto(full_domain_url, wait_until="networkidle", timeout=TIMEOUTS["navigation"])

        renew_locator = page.locator("button:has-text('Renew'), button:has-text('续期'), button:has-text('Prolong'), a[href*='renewdomain']")
        
        if await renew_locator.count() > 0:
            logger.info("找到续期链接/按钮，开始续期流程...")
            renew_button_or_link = renew_locator.first

            async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                await renew_button_or_link.click()

            order_button = page.locator("button:has-text('Order Now'), button:has-text('Continue')").first
            if await order_button.count() > 0:
                async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                    await order_button.click()

                agree_checkbox = page.locator("input[name='accepttos']")
                if await agree_checkbox.count() > 0:
                    await agree_checkbox.check()

                checkout_button = page.locator("button#checkout")
                if await checkout_button.count() > 0:
                    async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                        await checkout_button.click()

                    await asyncio.sleep(2)
                    page_content = await page.inner_text("body")
                    if "Order Confirmation" in page_content or "successfully" in page_content.lower():
                        logger.info(f"成功！域名 {domain_name} 续期订单已提交。")
                        return True, None
                    else:
                        error_msg = f"{domain_name} (确认失败)"
                        logger.warning(f"域名 {domain_name} 最终确认失败")
                        await page.screenshot(path=f"error_{domain_name}_confirm.png")
                        return False, error_msg
                else:
                    error_msg = f"{domain_name} (无Checkout按钮)"
                    logger.warning(f"在 {domain_name} 的续期页面找不到 'Checkout' 按钮")
                    return False, error_msg
            else:
                error_msg = f"{domain_name} (无Order按钮)"
                logger.warning(f"在 {domain_name} 的续期页面找不到 'Order Now' 按钮")
                return False, error_msg
        else:
            logger.info(f"域名 {domain_name} 在此详情页未找到续期按钮/链接，可能无需续期。")
            return None, None

    except Exception as e:
        error_msg = f"{domain_name} (异常: {str(e)})"
        logger.error(f"处理域名 {domain_name} 时发生错误: {e}")
        await page.screenshot(path=f"error_{domain_name}_exception.png")
        return False, error_msg


async def run_renewal():
    """主执行函数，运行完整的登录和续期流程。"""
    validate_config()

    browser = None
    page = None
    renewed_domains = []
    failed_domains = []

    async with async_playwright() as p:
        try:
            logger.info("正在启动浏览器 (Chromium, Headless 模式)...")
            browser, context = await setup_browser_context(p)
            page = await context.new_page()

            # (已移除 stealth)
            await add_anti_detection_scripts(page)

            await login(page)

            logger.info("\n正在导航到域名管理页面...")
            await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])

            await page.wait_for_selector("table.table-domains", timeout=TIMEOUTS["element_wait"])
            logger.info("已到达域名列表页面。")

            domain_rows = await page.locator("table.table-domains tbody tr").all()
            if not domain_rows:
                logger.info("未找到任何域名。")
            else:
                logger.info(f"共找到 {len(domain_rows)} 个域名，开始逐一检查...")
                base_url = "https://dash.domain.digitalplat.org/"

                for i, row in enumerate(domain_rows):
                    onclick_attr = await row.get_attribute("onclick")
                    if onclick_attr:
                        domain_url_path = onclick_attr.split("'")[1]
                        domain_name = await row.locator("td:nth-child(1)").inner_text()
                        status = await row.locator("td:nth-child(3)").inner_text()
                        domain_name = domain_name.strip()
                        status = status.strip()
                        logger.info(f"\n[{i+1}/{len(domain_rows)}] 检查域名: {domain_name} (状态: {status})")

                        success, error_msg = await process_domain(page, domain_name, domain_url_path, base_url)
                        if success:
                            renewed_domains.append(domain_name)
                        elif error_msg:
                            failed_domains.append(error_msg)

                        logger.info("正在返回域名列表页面...")
                        await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])
                    else:
                        logger.warning(f"第 {i+1} 行域名没有 onclick 属性，跳过。")

            logger.info("\n--- 所有域名检查完成 ---")
            if not renewed_domains and not failed_domains:
                title = "DigitalPlat 续期检查完成"
                body = "所有域名均检查完毕，本次没有需要续期或处理失败的域名。"
            else:
                title = f"DigitalPlat 续期报告"
                body = ""
                if renewed_domains:
                    body += f"✅ 成功续期 {len(renewed_domains)} 个域名:\n" + "\n".join(renewed_domains) + "\n\n"
                if failed_domains:
                    body += f"❌ 处理失败 {len(failed_domains)} 个域名:\n" + "\n".join(failed_domains)
            send_bark_notification(title, body.strip())

            save_results(renewed_domains, failed_domains)

        except Exception as e:
            error_message = f"脚本执行时发生严重错误: {type(e).__name__} - {e}"
            logger.error(f"错误: {error_message}")
            if page:
                await page.screenshot(path="fatal_error_screenshot.png")
                logger.info("已保存截图 'fatal_error_screenshot.png' 以供调试。")
            send_bark_notification("DigitalPlat 脚本严重错误", f"{error_message}\n请检查 GitHub Actions 日志获取详情。")
            sys.exit(1)
        finally:
            if browser and browser.is_connected():
                logger.info("关闭浏览器...")
                await browser.close()

if __name__ == "__main__":
    asyncio.run(run_renewal())
