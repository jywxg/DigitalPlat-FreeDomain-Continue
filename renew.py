# renew.py
# 最后更新时间: 2025-07-17
# DigitalPlat 免费域名自动续期脚本

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
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- 从环境变量中读取配置 ---
DP_EMAIL = os.getenv("DP_EMAIL")
DP_PASSWORD = os.getenv("DP_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 网站固定 URL ---
BASE_URL = "https://dash.domain.digitalplat.org"
LOGIN_URL = f"{BASE_URL}/auth/login"
DOMAINS_URL = f"{BASE_URL}/panel/main?page=%2Fpanel%2Fdomains"

# --- 超时配置 ---
TIMEOUTS = {
    "page_load": 45000,
    "element_wait": 20000,
    "navigation": 30000,
    "login_wait": 120000
}

# --- 重试配置 ---
RETRY_CONFIG = {
    "max_retries": 3,
    "delay": 2
}

def validate_config():
    """验证必需的环境变量是否已设置"""
    required_vars = {
        "DP_EMAIL": DP_EMAIL,
        "DP_PASSWORD": DP_PASSWORD
    }

    missing = [var for var, value in required_vars.items() if not value]
    if missing:
        error_msg = f"错误：缺少必需的环境变量: {', '.join(missing)}"
        logger.error(error_msg)
        send_telegram_notification(f"❌ DigitalPlat 配置错误\n{error_msg}")
        sys.exit(1)

    # 检查 Telegram 配置（可选，但建议配置）
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram 配置不完整，将无法发送通知")

def send_telegram_notification(message):
    """
    发送 Telegram 推送通知。

    Args:
        message: 要发送的消息内容
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram 配置未设置，跳过发送通知")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram 通知发送成功")
    except requests.exceptions.RequestException as e:
        logger.error(f"发送 Telegram 通知失败: {e}")
    except Exception as e:
        logger.error(f"发送 Telegram 通知时发生未知错误: {e}")

def format_duration(seconds):
    """格式化时间间隔为可读字符串"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        return f"{seconds/60:.1f}分钟"
    else:
        return f"{seconds/3600:.1f}小时"

def save_results(renewed_domains, failed_domains, start_time):
    """保存处理结果到JSON文件"""
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    results = {
        "timestamp": end_time.isoformat(),
        "execution_duration_seconds": duration,
        "renewed_count": len(renewed_domains),
        "failed_count": len(failed_domains),
        "renewed_domains": renewed_domains,
        "failed_domains": failed_domains
    }

    try:
        with open("renewal_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"处理结果已保存到 renewal_results.json，执行耗时: {format_duration(duration)}")
    except Exception as e:
        logger.error(f"保存结果时发生错误: {e}")

async def retry_operation(operation, operation_name="操作", max_retries=3, delay=2):
    """
    重试操作的通用函数

    Args:
        operation: 要执行的异步操作
        operation_name: 操作名称（用于日志）
        max_retries: 最大重试次数
        delay: 重试之间的延迟（秒）
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as e:
            last_exception = e
            if attempt == max_retries - 1:
                break
            wait_time = delay * (attempt + 1)  # 递增等待时间
            logger.warning(f"{operation_name} 失败，{wait_time}秒后重试... (尝试 {attempt + 1}/{max_retries}) - 错误: {e}")
            await asyncio.sleep(wait_time)
    
    raise last_exception

async def simulate_human_behavior(page, intensity="normal"):
    """模拟人类行为"""
    behaviors = {
        "light": [
            lambda: page.mouse.move(random.randint(100, 500), random.randint(100, 500)),
            lambda: asyncio.sleep(random.uniform(0.3, 1.0))
        ],
        "normal": [
            lambda: page.mouse.move(random.randint(50, 800), random.randint(50, 600), steps=random.randint(5, 15)),
            lambda: asyncio.sleep(random.uniform(0.5, 1.5)),
            lambda: page.mouse.wheel(0, random.randint(-200, 200)),
            lambda: asyncio.sleep(random.uniform(0.2, 0.8))
        ],
        "intensive": [
            lambda: page.mouse.move(random.randint(0, 1200), random.randint(0, 800), steps=random.randint(10, 25)),
            lambda: asyncio.sleep(random.uniform(0.8, 2.0)),
            lambda: page.mouse.wheel(0, random.randint(-300, 300)),
            lambda: asyncio.sleep(random.uniform(0.5, 1.2)),
            lambda: page.mouse.click(random.randint(100, 1100), random.randint(100, 700), delay=random.randint(100, 300)) if random.random() > 0.7 else asyncio.sleep(0)
        ]
    }
    
    selected_behaviors = behaviors.get(intensity, behaviors["normal"])
    for behavior in random.sample(selected_behaviors, k=random.randint(2, len(selected_behaviors))):
        await behavior()

async def setup_browser_context(playwright):
    """设置浏览器上下文"""
    browser = await playwright.firefox.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-gpu',
            '--window-size=1920,1080',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor'
        ]
    )

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York"
    )

    return browser, context

async def add_anti_detection_scripts(page):
    """添加反检测脚本"""
    scripts = [
        # 隐藏 webdriver 属性
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        
        # 模拟 Chrome 运行时
        "window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};",
        
        # 覆盖 plugins 和 languages
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});",
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});",
        
        # 覆盖 permissions
        """
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """
    ]

    for script in scripts:
        try:
            await page.add_init_script(script)
        except Exception as e:
            logger.warning(f"注入反检测脚本时出错: {e}")

async def login(page):
    """执行登录流程"""
    logger.info("正在导航到登录页面...")
    
    async def login_operation():
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=TIMEOUTS["page_load"])
        
        # 模拟人类行为
        await simulate_human_behavior(page, "normal")
        
        # 等待登录表单
        logger.info("等待登录表单加载...")
        await page.wait_for_selector("input[name='email']", timeout=TIMEOUTS["login_wait"])
        
        # 填写登录信息
        logger.info("正在填写登录信息...")
        await page.type("input[name='email']", DP_EMAIL, delay=random.randint(30, 100))
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await page.type("input[name='password']", DP_PASSWORD, delay=random.randint(30, 100))
        
        # 再次模拟行为
        await simulate_human_behavior(page, "light")
        
        logger.info("正在点击登录按钮...")
        async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
            await page.click("button[type='submit']")
        
        # 确认登录成功
        if "/panel/main" not in page.url:
            raise Exception(f"登录后未能跳转到仪表盘，当前URL: {page.url}")
        
        logger.info("登录成功！已进入用户仪表盘。")
        return True
    
    return await retry_operation(login_operation, "登录", max_retries=2, delay=3)

async def process_domain(page, domain_name, domain_url_path):
    """处理单个域名的续期"""
    try:
        # 构造并访问域名管理页面
        full_domain_url = BASE_URL + domain_url_path
        logger.info(f"正在访问 {domain_name} 的管理页面")
        
        await page.goto(full_domain_url, wait_until="networkidle", timeout=TIMEOUTS["navigation"])
        await simulate_human_behavior(page, "light")

        # 查找续期链接
        renew_link = page.locator("a[href*='renewdomain']")
        if await renew_link.count() == 0:
            logger.info(f"域名 {domain_name} 无需续期或找不到续期链接")
            return None, None

        logger.info(f"找到续期链接，开始处理 {domain_name}...")
        
        # 点击续期链接
        async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
            await renew_link.click()

        # 处理续期流程
        await simulate_human_behavior(page, "light")
        
        # 点击 Order Now 或 Continue
        order_button = page.locator("button:has-text('Order Now'), button:has-text('Continue')").first
        if await order_button.count() == 0:
            return False, f"{domain_name} (找不到Order按钮)"

        async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
            await order_button.click()

        # 同意条款
        agree_checkbox = page.locator("input[name='accepttos']")
        if await agree_checkbox.count() > 0:
            await agree_checkbox.check()

        # 完成结账
        checkout_button = page.locator("button#checkout")
        if await checkout_button.count() == 0:
            return False, f"{domain_name} (找不到Checkout按钮)"

        async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
            await checkout_button.click()

        # 检查订单确认
        await asyncio.sleep(3)  # 等待页面完全加载
        page_content = await page.inner_text("body")
        
        if any(keyword in page_content for keyword in ["Order Confirmation", "successfully", "Thank you"]):
            logger.info(f"✅ 域名 {domain_name} 续期成功")
            return True, None
        else:
            logger.warning(f"域名 {domain_name} 续期确认信息不明确")
            await page.screenshot(path=f"warning_{domain_name.replace('.', '_')}_confirm.png")
            return False, f"{domain_name} (确认信息不明确)"

    except Exception as e:
        error_msg = f"{domain_name} ({type(e).__name__})"
        logger.error(f"处理域名 {domain_name} 时发生错误: {e}")
        try:
            await page.screenshot(path=f"error_{domain_name.replace('.', '_')}.png")
        except:
            pass
        return False, error_msg

async def run_renewal():
    """主执行函数，运行完整的登录和续期流程"""
    start_time = datetime.now()
    validate_config()
    
    # 发送开始通知
    send_telegram_notification("🔄 DigitalPlat 域名续期任务开始执行")

    browser = None
    page = None
    renewed_domains = []
    failed_domains = []

    async with async_playwright() as p:
        try:
            # 启动浏览器
            logger.info("正在启动浏览器...")
            browser, context = await setup_browser_context(p)
            page = await context.new_page()

            # 添加反检测措施
            await add_anti_detection_scripts(page)

            # 登录
            await login(page)

            # 导航到域名列表
            logger.info("正在导航到域名管理页面...")
            await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])
            
            # 等待域名列表加载
            try:
                await page.wait_for_selector("table.table-domains", timeout=TIMEOUTS["element_wait"])
            except PlaywrightTimeoutError:
                logger.warning("未找到域名表格，尝试继续执行...")

            # 获取域名行
            domain_rows = await page.locator("table.table-domains tbody tr").all()
            if not domain_rows:
                logger.info("未找到任何域名")
            else:
                logger.info(f"共找到 {len(domain_rows)} 个域名，开始检查续期...")
                
                for i, row in enumerate(domain_rows):
                    onclick_attr = await row.get_attribute("onclick")
                    if not onclick_attr:
                        continue
                        
                    domain_url_path = onclick_attr.split("'")[1]
                    domain_name = (await row.locator("td:nth-child(1)").inner_text()).strip()
                    status = (await row.locator("td:nth-child(3)").inner_text()).strip()
                    
                    logger.info(f"[{i+1}/{len(domain_rows)}] 检查: {domain_name} (状态: {status})")

                    success, error_msg = await process_domain(page, domain_name, domain_url_path)
                    if success:
                        renewed_domains.append(domain_name)
                    elif error_msg:
                        failed_domains.append(error_msg)

                    # 返回域名列表
                    if i < len(domain_rows) - 1:  # 如果不是最后一个域名
                        await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])

            # 发送结果通知
            duration = format_duration((datetime.now() - start_time).total_seconds())
            if not renewed_domains and not failed_domains:
                message = f"✅ DigitalPlat 续期完成\n\n所有域名检查完毕，本次没有需要续期的域名。\n⏰ 执行耗时: {duration}"
            else:
                message = f"📊 DigitalPlat 续期报告\n\n"
                if renewed_domains:
                    message += f"✅ 成功续期 {len(renewed_domains)} 个:\n" + "\n".join(f"  • {domain}" for domain in renewed_domains) + "\n\n"
                if failed_domains:
                    message += f"❌ 处理失败 {len(failed_domains)} 个:\n" + "\n".join(f"  • {domain}" for domain in failed_domains) + "\n\n"
                message += f"⏰ 执行耗时: {duration}"
            
            send_telegram_notification(message)
            logger.info("任务执行完成")

            # 保存结果
            save_results(renewed_domains, failed_domains, start_time)

        except Exception as e:
            # 错误处理
            error_message = f"脚本执行失败: {type(e).__name__} - {e}"
            logger.error(error_message)
            
            try:
                if page:
                    await page.screenshot(path="fatal_error.png")
            except:
                pass
                
            send_telegram_notification(f"❌ DigitalPlat 脚本错误\n{error_message}")
            sys.exit(1)
            
        finally:
            # 清理资源
            if browser and browser.is_connected():
                await browser.close()
                logger.info("浏览器已关闭")

if __name__ == "__main__":
    asyncio.run(run_renewal())
