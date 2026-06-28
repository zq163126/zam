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
ZAMPTO_COOKIES_JSON = os.environ.get("ZAMPTO_COOKIES")

SCREENSHOT_PATH = "screenshot.png"
DEBUG_LOGIN_PATH = "debug_login.png"


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


async def check_and_solve_turnstile_safely(page, description=""):
    """
    深度全局扫描：遍历页面上所有的 frames，彻底攻克多层嵌套导致“未发现验证框”的问题。
    """
    print(f"🔄 [检查开始] 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    await asyncio.sleep(2.0)  # 给弹窗和异步域留出充足的加载时间
    
    try:
        # 1. 打印现场所有的 frames 状态，供日志分析
        all_frames = page.frames
        print(f"📊 [调试日志] 当前全页面共检测到 {len(all_frames)} 个 iframe 框架域。")
        for idx, f in enumerate(all_frames):
            print(f"  -> Frame [{idx}]: URL={f.url[:90]}")

        # 2. 全局动态寻找包含 cloudflare 挑战域的真实 iframe 节点
        cf_frame_instance = None
        target_element = None
        
        for f in all_frames:
            if "challenges.cloudflare.com" in f.url:
                cf_frame_instance = f
                print(f"🎯 [精准捕获] 成功在子域中锁定 CF 挑战 Frame: {f.url[:90]}")
                break

        if cf_frame_instance:
            # 找到内部的挑战容器节点
            target_element = cf_frame_instance.locator('#challenge-stage, .ctp-checkbox-label, #turnstile-wrapper').first
        else:
            # 备用方案：通过主页面常规 locator
            iframe_selector = "iframe[src*='challenges.cloudflare.com']"
            cf_locator = page.locator(iframe_selector).first
            if await cf_locator.is_visible(timeout=2000):
                print(f"🎯 [精准捕获] 通过主页面选择器找到了 CF 元素。")
                box = await cf_locator.bounding_box()
                if box:
                    click_x = box["x"] + (box["width"] * 0.22)
                    click_y = box["y"] + (box["height"] / 2)
                    print(f"🚀 正向常规坐标位置 [{click_x:.1f}, {click_y:.1f}] 发起敲击...")
                    await page.mouse.move(click_x, click_y)
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await page.mouse.up()
                    await asyncio.sleep(6)
                    return True

        # 3. 如果成功穿透进了子 frame，通过其绑定的真实页面父容器计算视口绝对坐标
        if cf_frame_instance:
            # 寻找承载该 frame 的主体 DOM 节点
            owner_frame_element = await cf_frame_instance.frame_element()
            box = await owner_frame_element.bounding_box()
            if box:
                print(f"📊 [坐标数据] 穿透测算 -> X: {box['x']:.1f}, Y: {box['y']:.1f}, 宽度: {box['width']:.1f}, 高度: {box['height']:.1f}")
                
                # 严格对准 Managed 拦截框的左侧复选框热区
                click_x = box["x"] + (box["width"] * 0.22)
                click_y = box["y"] + (box["height"] / 2)
                
                print(f"🎯 [执行动作] 穿透定位成功！正向实坐标 [{click_x:.1f}, {click_y:.1f}] 发起物理点击...")
                await page.mouse.move(click_x, click_y)
                await asyncio.sleep(0.1)
                await page.mouse.down()
                await asyncio.sleep(0.15)
                await page.mouse.up()
                
                print("⏳ [点击完成] 物理点击交互已触发，留出 8 秒等待凭证同步...")
                await asyncio.sleep(8)
                return True
            else:
                print("❌ [错误] 找到了 CF 子框架域，但无法逆向获取其 bounding_box 视口数据。")

        print("🔍 [元素探测] 经过多层深描，确定当前现场没有挂载或阻挡的 CF 验证码。")
            
    except Exception as e:
        print(f"ℹ️ [异常跳过] 全局深描验证框时发生非致命异常: {e}")
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

        # 将视口分辨率调整为 1920x1080，让截图看全整个页面
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # 抹除自动化指纹特征
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        has_logged_in = False

        # 优先尝试 Cookie 注入免登录
        if ZAMPTO_COOKIES_JSON:
            print("📦 发现配置了本地持久化 Cookies 凭证，正在尝试免登录直接切入...")
            try:
                cookies_list = json.loads(ZAMPTO_COOKIES_JSON)
                await solver.context.add_cookies(cookies_list)
                print("✅ 凭证数据成功同步至隔离上下文空间。")
                
                # 免登录跳转
                await page.goto("https://dash.zampto.net/server?id=6932", wait_until="domcontentloaded")
                await asyncio.sleep(3)
                
                if "sign-in" not in page.url and "google" not in page.url:
                    print("🎉 完美！使用 Cookies 成功跳过全部登录质询，已直接进入目标页！")
                    has_logged_in = True
                else:
                    print("⚠️ 注入的 Cookies 似乎已失效，将降级准备执行账号密码登录流程...")
            except Exception as cookie_err:
                print(f"❌ 尝试解析或注入 Cookie 时发生异常，将自动切回备用方案: {cookie_err}")

        # 备用方案：传统的账号密码登录流程
        if not has_logged_in:
            if not EMAIL or not PASSWORD:
                raise Exception("未注入有效的 Cookie 且缺少常规 EMAIL/PASSWORD 环境变量，脚本终止。")

            print("正在强制导航至传统登录网关...")
            LOGIN_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            # 如果初次进入发现被拦截或者加载异常，原地重刷页面
            content_before = await page.content()
            if "verify you are human" in content_before.lower() or "clerk" not in content_before.lower():
                print("⚠️ 监测到页面存在初次 CF 拦截或渲染不全，正在启动抗风控二次强制冲刷...")
                await page.goto(LOGIN_URL, wait_until="domcontentloaded")
                await asyncio.sleep(4)

            print("📸 正在截取【初始登录页面】视图以供分析...")
            await page.screenshot(path=DEBUG_LOGIN_PATH)
            send_telegram_notification("🔍 调试通知：这是输入 EMAIL 前的初始登录页面截图", DEBUG_LOGIN_PATH)

            # 仅在检测到有明确坐标的验证框时才进行点击
            await check_and_solve_turnstile_safely(page, "刚进入登录页")

            print("输入 Email...")
            email_input = page.locator('input[name="identifier"]').first
            try:
                await email_input.wait_for(state="visible", timeout=15000)
            except Exception as e:
                print("🚨 输入框超时未显现，尝试检测现场是否有明确的验证元素阻挡...")
                await check_and_solve_turnstile_safely(page, "输入框未显现时的常规探测")
                await email_input.wait_for(state="visible", timeout=5000)

            await email_input.fill(EMAIL)

            print("点击真实登录提交按钮...")
            login_btn_selectors = [
                'button[name="submit"][type="submit"]',
                'form button[type="submit"]:has-text("登录")',
                'form button[type="submit"]:has-text("Continue")',
                'button[type="submit"]'
            ]
            
            real_login_btn = None
            for selector in login_btn_selectors:
                try:
                    loc = page.locator(selector).first
                    if await loc.is_visible(timeout=2000):
                        real_login_btn = loc
                        print(f"🎯 成功锁定登录按钮选择器: {selector}")
                        break
                except:
                    continue
                    
            if not real_login_btn:
                raise Exception("无法在页面上准确定位到真实的【登录】表单提交按钮。")

            await real_login_btn.click()
            await asyncio.sleep(4)
            
            print("📸 正在截取【提交 Email 后】的过渡页面视图...")
            await page.screenshot(path=DEBUG_LOGIN_PATH)
            send_telegram_notification("🔍 调试通知：这是点击提交 EMAIL 后的状态截图", DEBUG_LOGIN_PATH)

            await check_and_solve_turnstile_safely(page, "提交 Email 后")

            print("等待密码页面加载并输入密码...")
            password_input = page.locator('input[name="password"]').first
            await password_input.wait_for(state="visible", timeout=15000)
            await password_input.fill(PASSWORD)

            print("点击继续提交按钮...")
            continue_btn = page.locator('form button[type="submit"]').first
            await continue_btn.click()

            await asyncio.sleep(5)
            
            print("正在跨越主页，直接强行访问目标服务器页面...")
            await page.goto("https://dash.zampto.net/server?id=6932", wait_until="domcontentloaded")

        print("已成功切入服务器管理页面，缓冲 5 秒等待页面后台 JS 渲染完毕...")
        await asyncio.sleep(5)

        # 清理干扰广告元素
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
            }""")
        except:
            pass

        # 定位真正的 Renew Server 按钮
        print("开始定位特定的 Renew Server 按钮...")
        renew_selectors = [
            'a[onclick*="handleServerRenewal(event, 6932)"]',
            'a[onclick*="handleServerRenewal"]',
            'a:has-text("Renew Server")'
        ]
        
        renew_link = None
        for sel in renew_selectors:
            try:
                locator = page.locator(sel).first
                if await locator.is_visible(timeout=3000):
                    renew_link = locator
                    print(f"✅ 成功锁定目标 Renew 元素选择器: [{sel}]")
                    break
            except:
                continue

        if not renew_link:
            print("⚠️ 组合选择器未能在第一现场抓到元素，尝试使用强力兜底策略等待...")
            renew_link = page.locator('a[onclick*="handleServerRenewal"]').first
            await renew_link.wait_for(state="visible", timeout=15000)

        print("点击最外层的 Renew Server 按钮，唤起安全验证弹窗...")
        await renew_link.click()
        await asyncio.sleep(4.0)

        # 🔗 执行全新升级的全局 Frames 穿透探测
        await check_and_solve_turnstile_safely(page, "点击 Renew 按钮弹出安全验证后")

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
