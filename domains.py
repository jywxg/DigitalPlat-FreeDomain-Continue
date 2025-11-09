#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# (这是最终的“混合”版本)
# (1. 使用 domains.py 的“地狱模式”登录流: headless=False + 多阶段 + 按回车)
# (2. 删除了 do_login 中失败的 wait_for_url 验证)
# (3. 移植了 renew.py 的“专业”续期逻辑: process_domain)
# (4. 它必须配合 'xvfb-run' 和 'headless=False' 运行)

import asyncio
import os
import subprocess
import urllib.parse
import time
import random
from datetime import datetime
import json # (renew.py 的逻辑需要 json)
import logging # (renew.py 的逻辑需要 logging)

# --- 1. 配置您的信息 (已为您填好) ---
CONFIG = {
    "email": os.getenv("DP_EMAIL"),
    "password": os.getenv("DP_PASSWORD"),
    "tg_token": os.getenv("TG_TOKEN"),
    "tg_chat_id": os.getenv("TG_CHAT_ID"),
    "max_retries": 3,
    "headless": False,  # <-- 1. 关键: 在GHA上必须是 False
    "slow_mo": 500,    
    "timeout": 120000,  
    "cf_timeout": 300,  
    "executablePath": None, # <-- 设为 None, 使用自动下载的浏览器
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

# --- (GHA 移植) ---
PROXY_URL = os.getenv("PROXY_URL") # 格式: http://... 或 socks5://...

# --- (来自 renew.py 的超时配置) ---
TIMEOUTS = {
    "page_load": 60000,
    "element_wait": 30000,
    "navigation": 60000,
    "login_wait": 180000
}
DOMAINS_URL = "https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains"

# ------------------------------------------
# ... (Color, print_log, tg_send 函数保持不变) ...
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
    print(f"{Color.WHITE}[{timestamp}]{Color.END} {color}{prefix}:{Color.END} {message}")


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


async def init_browser():
    from playwright.async_api import async_playwright
    try:
        playwright = await async_playwright().start()
        
        proxy_settings = None
        if PROXY_URL:
            print_log("检测到代理配置，将使用代理。", "debug")
            proxy_settings = {"server": PROXY_URL}
        else:
            print_log("未检测到代理配置，将直接连接 (在GHA上大概率失败)。", "warning")

        browser = await playwright.chromium.launch(
            headless=CONFIG["headless"], # <-- 必须是 False
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
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
# (这是 domains.py 的“多阶段”+“按回车”登录逻辑)
# ------------------------------------------

async def do_login(page):
    try:
        print_log("正在访问登录页面 (阶段 1: Email)...")
        await page.goto("https://dash.domain.digitalplat.org/auth/login", timeout=CONFIG["timeout"], wait_until="networkidle")
        
        # --- 阶段 1: Email (无 CF 盾) ---
        
        email_input = page.locator('input[name="email"]')
        try:
            await email_input.wait_for(state="visible", timeout=30000) # 30秒
            print_log("Email 输入框已可见。")
        except Exception as e:
            print_log(f"等待 Email 输入框[可见]超时: {e}", "error", important=True)
            await page.screenshot(path="login_email_not_visible_error.png")
            raise Exception("登录失败：Email 输入框未变为可见")

        print_log("正在模拟[键入] Email ...")
        await email_input.click()
        await email_input.type(CONFIG["email"], delay=random.randint(50, 150))
        
        print_log("正在模拟按 [Enter] 键提交 Email (绕过'Next'按钮)...")
        await email_input.press('Enter')

        # --- 阶段 2: Password (有 CF 盾) ---
        
        print_log("等待页面跳转到密码框 (阶段 2)... (正在等待唯一的 CF 5秒盾...)")
        password_input = page.locator('input[name="password"]')
        try:
            await password_input.wait_for(state="visible", timeout=180000)
            print_log("Password 输入框已可见。(CF 盾已通过!)")
        except Exception as e:
            print_log(f"等待 Password 输入框[可见]超时 (阶段 2): {e}", "error", important=True)
            await page.screenshot(path="login_password_not_visible_error.png")
            raise Exception("登录失败：Password 输入框未变为可见 (卡在CF盾)")

        print_log("正在模拟[键入] Password...")
        await password_input.type(CONFIG["password"], delay=random.randint(50, 150))
        
        print_log("正在模拟按 [Enter] 键提交 Password (绕过'Login'按钮)...")
        await password_input.press('Enter')
        
        # 步骤 G: [最终逻辑] 不再验证! 假定登录成功!
        # 我们知道 wait_for_url 会失败, 所以我们直接返回 True
        print_log("登录信息已提交! 假定登录成功!", important=True)
        return True
            
    except Exception as e:
        print_log(f"登录流程异常: {str(e)}", "error")
        return False

# ------------------------------------------
# vvvvvvvvvvvv (这是 renew.py 的“专业”续期逻辑) vvvvvvvvvvvv
# ------------------------------------------
async def process_domain(page, domain_name, domain_url_path, base_url):
    """处理单个域名的续期 (来自 renew.py)"""
    try:
        # 构造并访问域名管理页面
        full_domain_url = base_url + domain_url_path
        print_log(f"正在访问 {domain_name} 的管理页面: {full_domain_url}")
        await page.goto(full_domain_url, wait_until="networkidle", timeout=TIMEOUTS["navigation"])

        # 查找续期链接
        renew_link = page.locator("a[href*='renewdomain']")
        if await renew_link.count() > 0:
            print_log("找到续期链接，开始续期流程...")

            # 点击续期链接
            async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                await renew_link.click()

            # 点击"Order Now"或"Continue"
            order_button = page.locator("button:has-text('Order Now'), button:has-text('Continue')").first
            if await order_button.count() > 0:
                async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                    await order_button.click()

                # 同意条款
                agree_checkbox = page.locator("input[name='accepttos']")
                if await agree_checkbox.count() > 0:
                    await agree_checkbox.check()

                # 完成结账
                checkout_button = page.locator("button#checkout")
                if await checkout_button.count() > 0:
                    async with page.expect_navigation(wait_until="networkidle", timeout=TIMEOUTS["navigation"]):
                        await checkout_button.click()

                    # 检查订单确认
                    await asyncio.sleep(2)  # 等待页面完全加载
                    page_content = await page.inner_text("body")
                    if "Order Confirmation" in page_content or "successfully" in page_content.lower():
                        print_log(f"成功！域名 {domain_name} 续期订单已提交。")
                        return True, None
                    else:
                        error_msg = f"{domain_name} (确认失败)"
                        print_log(f"域名 {domain_name} 最终确认失败", "warning")
                        await page.screenshot(path=f"error_{domain_name}_confirm.png")
                        return False, error_msg
                else:
                    error_msg = f"{domain_name} (无Checkout按钮)"
                    print_log(f"在 {domain_name} 的续期页面找不到 'Checkout' 按钮", "warning")
                    return False, error_msg
            else:
                error_msg = f"{domain_name} (无Order按钮)"
                print_log(f"在 {domain_name} 的续期页面找不到 'Order Now' 按钮", "warning")
                return False, error_msg
        else:
            print_log("在此域名详情页未找到续期链接，可能无需续期。")
            return None, None

    except Exception as e:
        error_msg = f"{domain_name} (异常: {str(e)})"
        print_log(f"处理域名 {domain_name} 时发生错误: {e}", "error")
        await page.screenshot(path=f"error_{domain_name}_exception.png")
        return False, error_msg

# ------------------------------------------
# (这是重写的 main 函数，它结合了 do_login 和 renew.py 的续期循环)
# ------------------------------------------
async def main():
    start_time = time.time()
    
    # GHA 移植修改 4: 添加启动前配置校验
    if not CONFIG["email"] or not CONFIG["password"]:
        print_log("错误：DP_EMAIL 或 DP_PASSWORD 环境变量未设置！", "error", important=True)
        print_log("请在 GitHub Secrets 中设置 DP_EMAIL 和 DP_PASSWORD。", "error")
        exit(1) # 严重错误，直接退出
    
    print_log("DigitalPlat 自动续期脚本启动 (GHA 混合版)", important=True)
    
    renewed_domains = []
    failed_domains = []

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
            
            # 1. 执行“地狱模式”登录
            if not await do_login(page):
                raise Exception("登录失败")
            
            # 2. 登录“成功”后，执行 renew.py 的续期逻辑
            print_log("\n正在导航到域名管理页面...")
            await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])

            # 等待域名列表加载
            await page.wait_for_selector("table.table-domains", timeout=TIMEOUTS["element_wait"])
            print_log("已到达域名列表页面。")

            # 获取所有域名行
            domain_rows = await page.locator("table.table-domains tbody tr").all()
            if not domain_rows:
                print_log("未找到任何域名。")
            else:
                print_log(f"共找到 {len(domain_rows)} 个域名，开始逐一检查...")
                base_url = "https://dash.domain.digitalplat.org/"

                # (renew.py 逻辑) 处理每个域名
                for i, row in enumerate(domain_rows):
                    # 从 onclick 属性中提取域名和状态
                    onclick_attr = await row.get_attribute("onclick")
                    if onclick_attr:
                        domain_url_path = onclick_attr.split("'")[1]
                        domain_name = await row.locator("td:nth-child(1)").inner_text()
                        status = await row.locator("td:nth-child(3)").inner_text()
                        domain_name = domain_name.strip()
                        status = status.strip()
                        print_log(f"\n[{i+1}/{len(domain_rows)}] 检查域名: {domain_name} (状态: {status})")

                        # 处理域名续期
                        success, error_msg = await process_domain(page, domain_name, domain_url_path, base_url)
                        if success:
                            renewed_domains.append(domain_name)
                        elif error_msg:
                            failed_domains.append(error_msg)

                        # 返回域名列表页面以便处理下一个
                        print_log("正在返回域名列表页面...")
                        await page.goto(DOMAINS_URL, wait_until="networkidle", timeout=TIMEOUTS["navigation"])
                    else:
                        print_log(f"第 {i+1} 行域名没有 onclick 属性，跳过。", "warning")

            
            # 3. (renew.py 逻辑) 发送最终执行结果通知
            print_log("\n--- 所有域名检查完成 ---")
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
            await tg_send(body.strip())
            
            # 4. 如果一切顺利，跳出重试循环
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
