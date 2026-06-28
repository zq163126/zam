import os
import sys
import asyncio
import requests

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


async def check_and_solve_cf(solver, description=""):
    """
    核心自动化守护函数：检测当前页面是否有 Cloudflare 验证框。
    """
    page = solver.page
    if not page:
        return
        
    print(f"🔄 正在检查是否触发 CF 人机验证 ({description})...")
    
    cf_selectors = [
        "div.cf-turnstile",
        "iframe[src*='challenges.cloudflare.com']",
        "#cf-challenge-slot",
        "div:has-text('Verify you are human')"
    ]
    
    is_cf_present = False
    for selector in cf_selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=3000):
                is_cf_present = True
                print(f"⚠️ 检测到 CF 拦截元素: {selector}")
                break
        except:
            continue

    if is_cf_present:
        print("🚀 发现 Cloudflare 验证框！正在激活 cfbypass 穿透人机盾...")
        try:
            await solver.bypass()
            print("✅ cfbypass 处理流程结束，等待 3 秒使页面状态稳定...")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"❌ 穿透 CF 盾时发生异常: {e}")
    else:
        print("🔍 未发现 CF 验证框，继续下一步。")


async def run_automation():
    if not EMAIL or not PASSWORD:
        print("错误: 缺少登录凭证 EMAIL 或 PASSWORD 环境变量")
        sys.exit(1)

    print("正在启动带有 Cloudflare-Bypass 守护的全局浏览器实例...")
    
    # 修复点：带上必填的 domain 参数，满足底层 __init__ 的位置参数要求
    solver = CF_Solver(
        domain="https://dash.zampto.net",
        headless=True,
        slow_mo=150,
        poll_interval=1.0,
        max_wait=30.0,
    )

    page = None
    try:
        # 缓冲 3 秒，等待 solver 内部完全就绪
        await asyncio.sleep(3)
        page = solver.page
        
        if not page:
            raise Exception("未能成功初始化 Playwright 页面实例，solver.page 返回空。")

        # 1. 显式控制页面跳转到登录页
        print("正在控制浏览器访问登录页面...")
        await page.goto(
            "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl",
            wait_until="networkidle",
        )
        
        # 🔗 访问后检查
        await check_and_solve_cf(solver, "进入登录页后")

        # 1.1 输入 EMAIL
        print("输入 Email...")
        email_input = page.locator('input[name="identifier"]')
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(EMAIL)

        # 1.2 点击登录提交按钮
        print("点击登录提交按钮...")
        login_btn = page.locator('button[type="submit"]')
        await login_btn.click()
        # 🔗 动作后检查
        await check_and_solve_cf(solver, "提交 Email 后")

        # 1.3 输入密码
        print("等待密码页面加载并输入密码...")
        password_input = page.locator('input[name="password"]')
        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(PASSWORD)

        # 1.4 点击继续按钮
        print("点击继续提交按钮...")
        continue_btn = page.locator('button[type="submit"]')
        await continue_btn.click()
        # 🔗 动作后检查
        await check_and_solve_cf(solver, "提交密码后")

        # 等待自动跳转确认登录成功
        print("检查是否登录成功...")
        await page.wait_for_url("**/homepage", timeout=20000)
        print("登录成功！已跳转至主页。")

        # 2. 直接访问续期服务器页面
        print("访问目标服务器页面...")
        await page.goto("https://dash.zampto.net/server?id=6932", wait_until="load")
        # 🔗 访问后检查
        await check_and_solve_cf(solver, "进入目标服务器页后")

        # 清理干扰广告元素
        print("清理干扰广告元素...")
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
            }""")
        except:
            pass

        # 3. 定位最外层的续期链接并点击
        renew_link = page.locator('a[onclick*="handleServerRenewal"]')
        await renew_link.wait_for(state="visible", timeout=15000)

        print("点击最外层的 Renew Server 按钮，唤起安全验证弹窗...")
        await renew_link.click()
        
        # 🔗 关键动作后检查（处理弹窗中的 CF 验证码）
        await check_and_solve_cf(solver, "点击 Renew 按钮弹出安全验证后")

        # 4. 稍作等待让续期操作在验证通过后有充足时间完成
        print("等待 8 秒让续期业务后台确认结果...")
        await asyncio.sleep(8)

        # 再次清理广告，保证截图重点突出
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
            }""")
        except:
            pass

        # 5. 截图并发送通知
        print("正在截取操作结果图...")
        await page.screenshot(path=SCREENSHOT_PATH)

        success_msg = "Zampto 续期脚本执行完毕。请通过下方截图确认最终续期状态。"
        send_telegram_notification(success_msg, SCREENSHOT_PATH)

    except Exception as e:
        error_msg = f"脚本运行发生异常: {str(e)}"
        print(error_msg)
        try:
            if page:
                await page.screenshot(path=SCREENSHOT_PATH)
                send_telegram_notification(
                    f"❌ 续期失败！\n错误信息: {error_msg}", SCREENSHOT_PATH
                )
            else:
                send_telegram_notification(f"❌ 续期失败且无法截图（浏览器未就绪）！\n错误信息: {error_msg}")
        except:
            send_telegram_notification(f"❌ 续期失败且无法截图！\n错误信息: {error_msg}")
    finally:
        await solver.close()


if __name__ == "__main__":
    asyncio.run(run_automation())
