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
    针对 Closed Shadow DOM 以及各种静态、动态拦截框的高级物理穿透守卫：
    """
    print(f"🔄 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    
    # 扩大探测范围：不仅看续期弹窗，也探测登录页可能出现的独立验证框
    cf_selectors = [
        "iframe[src*='challenges.cloudflare.com']",
        "#turnstileContainer",
        "#cf-challenge-slot",
        "#renewModal .confirmation-modal-content"
    ]
    
    try:
        for selector in cf_selectors:
            element = page.locator(selector).first
            if await element.is_visible(timeout=3000):
                print(f"⚠️ 现场发现安全拦截/验证元素: {selector}，启动物理测距穿透...")
                box = await element.bounding_box()
                if box:
                    click_x = box["x"] + (box["width"] / 2)
                    click_y = box["y"] + (box["height"] / 2)
                    
                    # 如果是续期弹窗，纵向位置做微调偏移以对准复选框
                    if "renewModal" in selector:
                        click_y = box["y"] + (box["height"] * 0.62)
                        
                    print(f"🎯 正在向目标中心坐标 [{click_x:.1f}, {click_y:.1f}] 发起物理敲击...")
                    await page.mouse.move(click_x, click_y)
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await page.mouse.up()
                    
                    print("⏳ 物理点击完成，留出 6 秒供验证器后台响应...")
                    await asyncio.sleep(6)
                    return
    except Exception as e:
        print(f"ℹ️ 测距守卫异常或跳过: {e}")


async def run_automation():
    if not EMAIL or not PASSWORD:
        print("错误: 缺少登录凭证 EMAIL 或 PASSWORD 环境变量")
        sys.exit(1)

    print("正在启动带有 Cloudflare-Bypass 守护的全局浏览器实例...")
    
    # 将初始探路域名改为主面板，降低在一开始被 auth 域名拦截的概率
    MAIN_DASH_URL = "https://dash.zampto.net"
    solver = CF_Solver(
        domain=MAIN_DASH_URL,
        headless=True,
        slow_mo=150,
        poll_interval=1.0,
        max_wait=30.0,
    )

    page = None
    try:
        print("正在调用 cfbypass 建立浏览器环境...")
        try:
            await solver.bypass()
        except Exception as bypass_err:
            print(f"💡 提示: 初始探测结束（忽略 Headless 警告，强行接管页面）: {bypass_err}")
        
        page = solver.page
        if not page:
            raise Exception("未能成功通过 solver 获取到 Playwright 页面实例。")

        # 强行重定向到登录页面
        print("正在强制导航至登录网关...")
        await page.goto(
            "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl",
            wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)

        # 🔗 核心加固：进入登录页后，立即扫射一次看有没有开门红的 CF 验证码，有就物理破开
        await check_and_solve_turnstile(page, "刚进入登录页")

        # 1.1 输入 EMAIL
        print("输入 Email...")
        email_input = page.locator('input[name="identifier"]')
        try:
            await email_input.wait_for(state="visible", timeout=15000)
        except Exception as e:
            # 如果依然找不到，说明可能被封锁在验证页，再实施一次紧急盲点敲击
            print("🚨 登录输入框未显现，尝试进行全屏中央紧急物理破壳...")
            await page.mouse.click(400, 300) # 尝试点击屏幕靠中心偏左位置
            await asyncio.sleep(4)
            await email_input.wait_for(state="visible", timeout=10000)

        await email_input.fill(EMAIL)

        # 1.2 点击登录提交按钮
        print("点击登录提交按钮...")
        login_btn = page.locator('button[type="submit"]')
        await login_btn.click()
        await asyncio.sleep(2)
        
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

        # 柔性等待登录状态写入
        await asyncio.sleep(4)

        # 2. 直接跨过主页，强行奔向目标续期服务器页面
        print("正在跨越主页，直接强行访问目标服务器页面...")
        await page.goto("https://dash.zampto.net/server?id=6932", wait_until="load")
        print("已成功切入服务器管理页面。")

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
        await asyncio.sleep(2.5) # 稳妥留出弹窗完全展开的动画时间
        
        # 🔗 核心突破点：处理续期弹窗中被 Closed Shadow DOM 隐藏的 Turnstile 人机验证框
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
