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
    针对 Closed Shadow DOM 的高级穿透守卫：
    由于 CF 验证码藏在 shadowrootmode="closed" 中，常规定位器无法穿透。
    我们直接利用外部可见的弹窗容器或整体视口定位，进行坐标降维打击。
    """
    print(f"🔄 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    
    # 定位最外层的续期弹窗容器（这是常规 DOM 可见元素）
    modal_selector = "#renewModal .confirmation-modal-content"
    
    try:
        modal = page.locator(modal_selector).first
        # 限时 4 秒判断弹窗是否切出并可见
        if await modal.is_visible(timeout=4000):
            print("⚠️ 现场发现续期安全弹窗！正在绕过 Closed Shadow DOM 物理测距...")
            
            # 获取整个中央弹窗的盒模型数据
            box = await modal.bounding_box()
            if box:
                # 根据弹窗的整体比例，Turnstile 验证框基本完美横向居中于弹窗内部
                # 纵向则位于弹窗中下部（取消按钮上方），在这里进行精确物理偏移计算
                click_x = box["x"] + (box["width"] / 2)
                click_y = box["y"] + (box["height"] * 0.62) # 约在弹窗纵向 62% 的位置
                
                print(f"🎯 测距成功。正在对封闭验证区坐标 [{click_x:.1f}, {click_y:.1f}] 发起物理敲击...")
                
                # 移动鼠标并点击，模拟真人轨迹
                await page.mouse.move(click_x, click_y)
                await page.mouse.down()
                await asyncio.sleep(0.1)
                await page.mouse.up()
                
                print(f"⏳ 物理敲击信号已发出，留出 6 秒供 Closed 容器内部响应与握手...")
                await asyncio.sleep(6)
            else:
                print("❌ 无法获取弹窗边界盒，跳过物理点击。")
        else:
            print("🔍 页面未拉起续期 Modal 弹窗或其处于不可见状态，继续下一步。")
    except Exception as e:
        print(f"ℹ️ 测距守卫运行期间发生异常或超时跳过: {e}")


async def run_automation():
    if not EMAIL or not PASSWORD:
        print("错误: 缺少登录凭证 EMAIL 或 PASSWORD 环境变量")
        sys.exit(1)

    print("正在启动带有 Cloudflare-Bypass 守护的全局浏览器实例...")
    
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
        try:
            await solver.bypass()
        except Exception as bypass_err:
            print(f"💡 提示: 初始 cfbypass 探测结束: {bypass_err}")
        
        page = solver.page
        if not page:
            raise Exception("未能成功通过 solver 获取到 Playwright 页面实例。")

        print("浏览器就绪。")

        # 1.1 输入 EMAIL
        print("输入 Email...")
        email_input = page.locator('input[name="identifier"]')
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(EMAIL)

        # 1.2 点击登录提交按钮
        print("点击登录提交按钮...")
        login_btn = page.locator('button[type="submit"]')
        await login_btn.click()

        # 1.3 输入密码
        print("等待密码页面加载并输入密码...")
        password_input = page.locator('input[name="password"]')
        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(PASSWORD)

        # 1.4 点击继续按钮
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
