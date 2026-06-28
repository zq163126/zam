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


async def check_and_solve_turnstile(page, description=""):
    """
    通用 Turnstile 自动穿透守卫：
    动态检测页面（包括嵌套 Iframe）里是否存在 Cloudflare Turnstile 验证框，
    如果存在，自动切入 Iframe 并精准点击复选框。
    """
    print(f"🔄 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    
    # 1. 寻找 Turnstile 的核心容器 Iframe
    iframe_selector = "iframe[src*='challenges.cloudflare.com']"
    
    try:
        # 限时 4 秒快速探测，不阻塞正常业务流程
        iframe_element = page.locator(iframe_selector).first
        if await iframe_element.is_visible(timeout=4000):
            print("⚠️ 现场发现 Cloudflare Turnstile 验证码 Iframe！准备穿透...")
            
            # 获取 iframe 视图对象
            box = await iframe_element.bounding_box()
            if box:
                # 方案 A：直接在页面上计算 Iframe 的中心绝对坐标进行物理点击，绕过元素防护
                click_x = box["x"] + box["width"] / 2
                click_y = box["y"] + box["height"] / 2
                print(f"🎯 正在向验证码中心坐标 [{click_x}, {click_y}] 发送物理点击...")
                await page.mouse.click(click_x, click_y)
            else:
                # 方案 B：如果拿不到 bounding_box，尝试切入 iframe 内部点击 #challenge-stage
                frame = page.frame(url=lambda u: "challenges.cloudflare.com" in u)
                if frame:
                    await frame.locator('#challenge-stage, input[type="checkbox"]').first.click(timeout=3000)
            
            print("⏳ 已触发验证码点击，等待 5 秒让验证状态在后台同步完成...")
            await asyncio.sleep(5)
        else:
            print("🔍 未发现 CF 验证元素，页面安全。")
    except Exception as e:
        print(f"ℹ️ 探测验证框时安全跳过或发生异常: {e}")


async def run_automation():
    if not EMAIL or not PASSWORD:
        print("错误: 缺少登录凭证 EMAIL 或 PASSWORD 环境变量")
        sys.exit(1)

    print("正在启动带有 Cloudflare-Bypass 守护的全局浏览器实例...")
    
    # 💡 核心调整 1：将 domain 直接设置为登录页
    # 这样一会调用 bypass 时，它内部刚好帮我们把浏览器初始化完，并顺利停留在登录页
    LOGIN_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
    solver = CF_Solver(
        domain=LOGIN_URL,
        headless=True,
        slow_mo=150,
        poll_interval=1.0,
        max_wait=45.0,
    )

    page = None
    try:
        print("正在调用 cfbypass 建立浏览器环境并加载登录页面...")
        # 💡 核心调整 2：调用 bypass() 唤醒初始化进程（不传任何参数）
        try:
            await solver.bypass()
        except Exception as bypass_err:
            print(f"💡 提示: 初始 bypass 探测结束（可能未生成 clearance cookie，属于正常现象）: {bypass_err}")
        
        # 此时 solver.page 绝对已经成功被建立并处于就绪状态
        page = solver.page
        if not page:
            raise Exception("未能成功通过 solver 获取到 Playwright 页面实例。")

        print("浏览器就绪。")
        # 🔗 访问后检查一次
        await check_and_solve_turnstile(page, "进入登录页后")

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
        await check_and_solve_turnstile(page, "提交 Email 后")

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
        await check_and_solve_turnstile(page, "提交密码后")

        # 等待自动跳转确认登录成功
        print("检查是否登录成功...")
        await page.wait_for_url("**/homepage", timeout=20000)
        print("登录成功！已跳转至主页。")

        # 2. 直接访问续期服务器页面
        print("访问目标服务器页面...")
        await page.goto("https://dash.zampto.net/server?id=6932", wait_until="load")
        # 🔗 访问后检查
        await check_and_solve_turnstile(page, "进入目标服务器页后")

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
        await asyncio.sleep(2) # 稍微等待弹窗动画完成
        
        # 🔗 核心突破点：处理续期弹窗中的 Turnstile 人机验证框
        await check_and_solve_turnstile(page, "点击 Renew 按钮弹出安全验证后")

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
