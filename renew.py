import os
import sys
import asyncio
import requests
from playwright.async_api import async_playwright

# 兼容处理 cfbypass.py 的各种放置方式
try:
    from cfbypass import CF_Solver
except ImportError:
    try:
        from cfbypass.cfbypass import CF_Solver
    except ImportError:
        print("错误: 未能在项目中找到 'cfbypass.py'，请确保该文件已放入项目根目录或 cfbypass 文件夹下。")
        sys.exit(1)

# 从 GitHub Secrets 中读取环境变量
EMAIL = os.environ.get("ZAMPTO_EMAIL")
PASSWORD = os.environ.get("ZAMPTO_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

SCREENSHOT_PATH = "screenshot.png"
TARGET_DOMAIN = "https://dash.zampto.net"


def send_telegram_notification(message, screenshot_path=None):
    """发送 Telegram 消息和截图"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("TG配置不完整，跳过通知。")
        return

    print(f"正在发送 TG 通知: {message}")
    try:
        text_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(text_url, json={"chat_id": TG_CHAT_ID, "text": message})

        if screenshot_path and os.path.exists(screenshot_path):
            photo_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(screenshot_path, "rb") as photo:
                requests.post(
                    photo_url, data={"chat_id": TG_CHAT_ID}, files={"photo": photo}
                )
    except Exception as e:
        print(f"发送 TG 通知失败: {e}")


async def get_cloudflare_cookie():
    """使用 Cloudflare-Bypass 项目获取 cf_clearance cookie"""
    print("正在通过 Cloudflare-Bypass 项目获取凭证...")
    solver = CF_Solver(
        domain=TARGET_DOMAIN,
        headless=True,  # GitHub Actions 必须设置为 True
        slow_mo=100,
        poll_interval=1.0,
        max_wait=90.0,
    )

    try:
        cf_cookie = await solver.bypass()
        print(f"成功获取 cf_clearance: {cf_cookie}")
        return cf_cookie
    except Exception as e:
        print(f"Cloudflare-Bypass 获取 Cookie 失败: {e}")
        return None
    finally:
        await solver.close()


async def run_automation():
    if not EMAIL or not PASSWORD:
        print("错误: 缺少登录凭证 EMAIL 或 PASSWORD 环境变量")
        sys.exit(1)

    # 第一步：获取过 CF 盾必需的 cookie
    cf_clearance_value = await get_cloudflare_cookie()
    if not cf_clearance_value:
        print("警告: 未能成功拿到 cf_clearance，尝试直接进行普通登录流程...")

    # 第二步：启动常规 Playwright 流程进行登录和续期
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )

        # 如果成功拿到了过盾 Cookie，将其注入到浏览器上下文
        if cf_clearance_value:
            await context.add_cookies(
                [
                    {
                        "name": "cf_clearance",
                        "value": cf_clearance_value,
                        "domain": ".zampto.net",
                        "path": "/",
                    }
                ]
            )
            print("已成功将 cf_clearance Cookie 注入浏览器上下文。")

        page = await context.new_page()

        try:
            # 1. 访问登录页面
            print("正在访问登录页面...")
            await page.goto(
                "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl",
                wait_until="networkidle",
            )

            # 1.1 输入 EMAIL
            print("输入 Email...")
            email_input = page.locator('input[name="identifier"]')
            await email_input.wait_for(state="visible", timeout=15000)
            await email_input.fill(EMAIL)

            # 1.2 点击登录按钮（移除中文字符过滤，纯属性精确定位）
            print("点击登录提交按钮...")
            login_btn = page.locator('button[type="submit"]')
            await login_btn.click()

            # 1.3 输入密码
            print("等待密码页面加载并输入密码...")
            password_input = page.locator('input[name="password"]')
            await password_input.wait_for(state="visible", timeout=15000)
            await password_input.fill(PASSWORD)

            # 1.4 点击继续（移除中文字符过滤，纯属性精确定位）
            print("点击继续提交按钮...")
            continue_btn = page.locator('button[type="submit"]')
            await continue_btn.click()

            # 等待自动跳转确认登录成功
            print("检查是否登录成功...")
            await page.wait_for_url("**/homepage", timeout=20000)
            print("登录成功！已跳转至主页。")

            # 2. 直接访问续期服务器页面
            print("访问目标服务器页面...")
            await page.goto("https://dash.zampto.net/server?id=6932", wait_until="load")

            # 鲁棒性定位 Renew 元素链接
            renew_link = page.locator('a[onclick*="handleServerRenewal"]')
            await renew_link.wait_for(state="visible", timeout=15000)

            print("点击 Renew Server 按钮...")
            await renew_link.click()

            # 3. 稍作等待让续期操作在后台完成
            print("已触发 Renew，等待 8 秒确认结果...")
            await asyncio.sleep(8)

            # 4. 截图并发送通知
            print("正在截取操作结果图...")
            await page.screenshot(path=SCREENSHOT_PATH)

            success_msg = "Zampto 续期脚本执行完毕。请通过下方截图确认最终续期状态。"
            send_telegram_notification(success_msg, SCREENSHOT_PATH)

        except Exception as e:
            error_msg = f"脚本运行发生异常: {str(e)}"
            print(error_msg)
            try:
                await page.screenshot(path=SCREENSHOT_PATH)
                send_telegram_notification(
                    f"❌ 续期失败！\n错误信息: {error_msg}", SCREENSHOT_PATH
                )
            except:
                send_telegram_notification(f"❌ 续期失败且无法截图！\n错误信息: {error_msg}")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run_automation())
