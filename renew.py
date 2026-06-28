import os
import sys
import asyncio
import requests
import json

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
ZAMPTO_COOKIES_JSON = os.environ.get("ZAMPTO_COOKIES") # 💡 建议新加的 Secret

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
    针对 Closed Shadow DOM 以及各种静态、动态拦截框的高级物理穿透守卫
    """
    print(f"🔄 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    
    cf_selectors = [
        "iframe[src*='challenges.cloudflare.com']",
        "#turnstileContainer",
        "#cf-challenge-slot",
        "#renewModal .confirmation-modal-content",
        "div:has-text('Verify you are human')"
    ]
    
    try:
        for selector in cf_selectors:
            element = page.locator(selector).first
            if await element.is_visible(timeout=2000):
                print(f"⚠️ 现场发现拦截元素: {selector}，开始进行物理定位...")
                box = await element.bounding_box()
                if box:
                    click_x = box["x"] + (box["width"] / 2)
                    click_y = box["y"] + (box["height"] / 2)
                    
                    if "renewModal" in selector:
                        click_y = box["y"] + (box["height"] * 0.62)
                        
                    print(f"🎯 正在向目标坐标 [{click_x:.1f}, {click_y:.1f}] 发起物理敲击...")
                    await page.mouse.move(click_x, click_y)
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await page.mouse.up()
                    print("⏳ 物理点击完成，等待 6 秒同步状态...")
                    await asyncio.sleep(6)
                    return True
    except Exception as e:
        print(f"ℹ️ 扫描已知验证框时跳过: {e}")
        
    try:
        content = await page.content()
        if "captcha" in content.lower() or "verify you are human" in content.lower():
            print("🚨 页面文字触发风控警报，进行视口中心物理轰击...")
            viewport = page.viewport_size
            if viewport:
                await page.mouse.click(viewport["width"] / 2, viewport["height"] / 2)
                await asyncio.sleep(6)
                return True
    except:
        pass
    return False


async def run_automation():
    print("正在启动带有 Cloudflare-Bypass 守护的全局浏览器实例...")
    
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
            print(f"💡 提示: 初始探测结束: {bypass_err}")
        
        page = solver.page
        if not page:
            raise Exception("未能成功通过 solver 获取到 Playwright 页面实例。")

        # 彻底抹除自动化指纹特征
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        has_logged_in = False

        # 💡 核心优化策略：优先尝试 Cookie 注入免登录，彻底封杀 Google 拦截
        if ZAMPTO_COOKIES_JSON:
            print("📦 发现配置了本地持久化 Cookies 凭证，正在尝试免登录直接切入...")
            try:
                cookies_list = json.loads(ZAMPTO_COOKIES_JSON)
                # 显式为主域和认证域同时注入 Cookie
                await solver.context.add_cookies(cookies_list)
                print("✅ 凭证数据成功同步至隔离上下文空间。")
                
                # 尝试直接去服务器页面测试 Cookie 是否有效
                await page.goto("https://dash.zampto.net/server?id=6932", wait_until="networkidle")
                await asyncio.sleep(3)
                
                # 检测是否由于 Cookie 失效或仍被拦截退回到登录页
                if "sign-in" not in page.url and "google" not in page.url:
                    print("🎉 完美！使用 Cookies 成功跳过全部登录质询，已直接进入目标页！")
                    has_logged_in = True
                else:
                    print("⚠️ 注入的 Cookies 似乎已失效，系统已自动将其踢回，降级准备执行账号密码登录流程...")
            except Exception as cookie_err:
                print(f"❌ 尝试解析或注入 Cookie 时发生异常，将自动切回备用方案: {cookie_err}")

        # 备用方案：传统的账号密码登录流程（应对没有配置 Cookie 的情况）
        if not has_logged_in:
            if not EMAIL or not PASSWORD:
                raise Exception("未注入有效的 Cookie 且缺少常规 EMAIL/PASSWORD 环境变量，脚本终止。")

            print("正在强制导航至传统登录网关...")
            await page.goto(
                "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl",
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(4)

            await check_and_solve_turnstile(page, "刚进入登录页")

            print("输入 Email...")
            email_input = page.locator('input[name="identifier"]')
            try:
                await email_input.wait_for(state="visible", timeout=8000)
            except Exception as e:
                # 如果找不到，多半是出了 Google 或者别的强验证，尝试做最后一次突围点击
                print("🚨 输入框未显现（可能被 Google 或拦截挡住），尝试物理破盾...")
                did_solve = await check_and_solve_turnstile(page, "找不到输入框时的紧急状态")
                if did_solve:
                    await email_input.wait_for(state="visible", timeout=10000)
                else:
                    raise Exception("页面打不开或卡死在第三方/Google登录风控层，请优先配置 ZAMPTO_COOKIES 免登录。")

            await email_input.fill(EMAIL)

            print("点击登录提交按钮...")
            login_btn = page.locator('button[type="submit"]')
            await login_btn.click()
            await asyncio.sleep(3)
            
            await check_and_solve_turnstile(page, "提交 Email 后")

            print("等待密码页面加载并输入密码...")
            password_input = page.locator('input[name="password"]')
            await password_input.wait_for(state="visible", timeout=15000)
            await password_input.fill(PASSWORD)

            print("点击继续提交按钮...")
            continue_btn = page.locator('button[type="submit"]')
            await continue_btn.click()

            await asyncio.sleep(5)
            
            print("正在跨越主页，直接强行访问目标服务器页面...")
            await page.goto("https://dash.zampto.net/server?id=6932", wait_until="networkidle")

        print("已成功切入服务器管理页面，缓冲 5 秒等待页面后台 JS 渲染完毕...")
        await asyncio.sleep(5)

        # 清理干扰广告元素
        print("清理干扰广告元素...")
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
            }""")
        except:
            pass

        # 3. 多重组合拳选择器定位 Renew 按钮
        print("开始定位 Renew 按钮...")
        renew_selectors = [
            'a[onclick*="handleServerRenewal"]',
            'button:has-text("Renew Server")',
            'a:has-text("Renew")',
            '.btn:has-text("Renew")'
        ]
        
        renew_link = None
        for sel in renew_selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=3000):
                    renew_link = locator
                    print(f"✅ 成功通过选择器 [{sel}] 锁定 Renew 元素！")
                    break
            except:
                continue

        if not renew_link:
            print("⚠️ 组合选择器未能在第一现场抓到元素，尝试使用强力兜底策略等待...")
            renew_link = page.locator('a[onclick*="handleServerRenewal"]').first
            await renew_link.wait_for(state="visible", timeout=15000)

        print("点击最外层的 Renew Server 按钮，唤起安全验证弹窗...")
        await renew_link.click()
        await asyncio.sleep(3.0) 
        
        # 🔗 核心突破点：处理续期弹窗中被 Closed Shadow DOM 隐藏的 Turnstile 人机验证框
        await check_and_solve_turnstile(page, "点击 Renew 按钮弹出安全验证后")

        # 4. 稍作等待让续期操作在验证通过后有充足时间完成
        print("等待 8 秒让续期业务后台确认结果...")
        await asyncio.sleep(8)

        # 再次清理广告
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
