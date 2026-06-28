import os
import sys
import time
import json
import requests
import platform
from pathlib import Path
from seleniumbase import SB

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
        requests.post(text_url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)

        if screenshot_path and os.path.exists(screenshot_path):
            photo_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(screenshot_path, "rb") as photo:
                requests.post(
                    photo_url, data={"chat_id": TG_CHAT_ID}, files={"photo": photo}, timeout=15
                )
    except Exception as e:
        print(f"发送 TG 通知失败: {e}")


def handle_turnstile_safely(sb, description=""):
    """
    通过 SeleniumBase 的 UC 专属底层驱动，100% 解决机房 IP 下不自动打勾的 Managed 挑战。
    """
    print(f"🔄 [检查开始] 正在检查是否触发 CF Turnstile 人机验证 ({description})...")
    time.sleep(2.5)
    try:
        # 使用你提到的经典隐藏凭证输入框断言
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result:
            print("🔍 [元素探测] 经隐藏输入框深描，当前现场没有挂载或阻挡的 CF 验证。")
            return False

        print("💡 [技术突破] 确信 CF 验证码在场！正在调用 SeleniumBase GUI 焦点投射过盾...")
        sb.uc_gui_click_captcha()
        print("⏳ [点击完成] 物理级点击已踩下，留出 8 秒等待绿勾判定与接口凭证同步...")
        time.sleep(8)
        return True
    except Exception as e:
        print(f"ℹ️ [拦截提示] 尝试 SB 底层穿透敲击时发生跳过: {e}")
    return False


def run_automation():
    print("正在启动带有 SeleniumBase-UC 守护的全局高级自适应浏览器实例...")
    
    # 保持与原有逻辑一致的 Headless 及反爬配置
    opts = {
        "uc": True, 
        "test": True, 
        "locale": "zh", 
        "headed": False,
        "timeout_multiplier": 0.5
    }

    # 兼容 Linux 无头环境的虚拟显示支持
    display = None
    if platform.system().lower() == "linux" and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(1920, 1080))
            display.start()
            os.environ["DISPLAY"] = display.new_display_var
            print("[INFO] Linux 环境下虚拟显示成功挂载。")
        except Exception as e:
            print(f"[WARN] 挂载虚拟显示发生跳过 (可能已具备环境): {e}")

    with SB(**opts) as sb:
        try:
            # 统一控制加载超时与 1920x1080 视口分辨率
            sb.driver.set_page_load_timeout(30)
            sb.driver.set_window_size(1920, 1080)

            has_logged_in = False

            # 优先尝试 Cookie 注入免登录 (完美移植原生判定与同步空间逻辑)
            if ZAMPTO_COOKIES_JSON:
                print("📦 发现配置了本地持久化 Cookies 凭证，正在尝试免登录直接切入...")
                try:
                    # 先导航至同域名激活上下文
                    sb.uc_open_with_reconnect("https://dash.zampto.net", reconnect_time=5.0)
                    cookies_list = json.loads(ZAMPTO_COOKIES_JSON)
                    
                    for cookie in cookies_list:
                        # 转换 Playwright Cookie 键名以适配 Selenium 格式
                        if 'sameSite' in cookie:
                            if cookie['sameSite'] not in ["Strict", "Lax", "None"]:
                                cookie['sameSite'] = "Lax"
                        sb.driver.add_cookie(cookie)
                        
                    print("✅ 凭证数据成功同步至隔离上下文空间。")
                    
                    # 免登录跳转
                    sb.open("https://dash.zampto.net/server?id=6932")
                    time.sleep(3)
                    
                    current_url = sb.get_current_url()
                    if "sign-in" not in current_url and "google" not in current_url:
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
                sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5.0)
                time.sleep(4)

                # 如果初次进入发现被拦截或者加载异常，原地重刷页面
                content_before = sb.get_page_source().lower()
                if "verify you are human" in content_before or "clerk" not in content_before:
                    print("⚠️ 监测到页面存在初次 CF 拦截或渲染不全，正在启动抗风控二次强制冲刷...")
                    sb.refresh()
                    time.sleep(4)

                print("📸 正在截取【初始登录页面】视图以供分析...")
                sb.save_screenshot(DEBUG_LOGIN_PATH)
                send_telegram_notification("🔍 调试通知：这是输入 EMAIL 前的初始登录页面截图", DEBUG_LOGIN_PATH)

                handle_turnstile_safely(sb, "刚进入登录页")

                print("输入 Email...")
                target_input = 'input[name="identifier"]'
                sb.wait_for_element_present(target_input, timeout=15)
                sb.type(target_input, EMAIL)

                print("点击真实登录提交按钮...")
                login_btn_selectors = [
                    'button[name="submit"][type="submit"]',
                    'form button[type="submit"]:has-text("登录")',
                    'form button[type="submit"]:has-text("Continue")',
                    'button[type="submit"]'
                ]
                
                real_login_btn = None
                for selector in login_btn_selectors:
                    if sb.is_element_visible(selector):
                        real_login_btn = selector
                        print(f"🎯 成功锁定登录按钮选择器: {selector}")
                        break
                        
                if not real_login_btn:
                    real_login_btn = 'button[type="submit"]'  # 强力兜底选择器

                sb.click(real_login_btn)
                time.sleep(4)
                
                print("📸 正在截取【提交 Email 后】的过渡页面视图...")
                sb.save_screenshot(DEBUG_LOGIN_PATH)
                send_telegram_notification("🔍 调试通知：这是点击提交 EMAIL 后的状态截图", DEBUG_LOGIN_PATH)

                handle_turnstile_safely(sb, "提交 Email 后")

                print("等待密码页面加载并输入密码...")
                password_input = 'input[name="password"]'
                sb.wait_for_element_present(password_input, timeout=15)
                sb.type(password_input, PASSWORD)

                print("点击继续提交按钮...")
                sb.click('form button[type="submit"]')
                time.sleep(5)
                
                print("正在跨越主页，直接强行访问目标服务器页面...")
                sb.open("https://dash.zampto.net/server?id=6932")

            print("已成功切入服务器管理页面，缓冲 5 秒等待页面后台 JS 渲染完毕...")
            time.sleep(5)

            # 清理干扰广告元素
            try:
                sb.execute_script("""
                    document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
                """)
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
                if sb.is_element_visible(sel):
                    renew_link = sel
                    print(f"✅ 成功锁定目标 Renew 元素选择器: [{sel}]")
                    break

            if not renew_link:
                print("⚠️ 组合选择器未能在第一现场抓到元素，尝试使用强力兜底策略等待...")
                renew_link = 'a[onclick*="handleServerRenewal"]'
                sb.wait_for_element_present(renew_link, timeout=15)

            print("点击最外层的 Renew Server 按钮，唤起安全验证弹窗...")
            sb.click(renew_link)
            time.sleep(4.0)

            # 🔗 调用 SB 核心黑科技，隔空越过跨域 iframe 沙箱强行点下人机复选框
            handle_turnstile_safely(sb, "点击 Renew 按钮弹出安全验证后")

            print("等待 8 秒让续期业务后台确认结果...")
            time.sleep(8)

            # 再次清理广告
            try:
                sb.execute_script("""
                    document.querySelectorAll('ins.adsbygoogle, iframe[id*="google"]').forEach(el => el.remove());
                """)
            except:
                pass

            # 5. 截图并发送通知
            print("正在截取操作结果图...")
            sb.save_screenshot(SCREENSHOT_PATH)

            success_msg = "Zampto 续期脚本执行完毕。请通过下方截图确认最终续期状态。"
            send_telegram_notification(success_msg, SCREENSHOT_PATH)

        except Exception as e:
            error_msg = f"脚本运行发生异常: {str(e)}"
            print(error_msg)
            try:
                sb.save_screenshot(SCREENSHOT_PATH)
                send_telegram_notification(f"❌ 续期失败！\n错误信息: {error_msg}", SCREENSHOT_PATH)
            except:
                send_telegram_notification(f"❌ 续期失败且无法截图！\n错误信息: {error_msg}")
        finally:
            if display:
                display.stop()


if __name__ == "__main__":
    run_automation()
