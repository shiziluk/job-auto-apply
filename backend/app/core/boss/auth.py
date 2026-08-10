"""
Boss直聘 - 登录认证模块
参考 JobClaw auth/browser_login.py + cookie_manager.py
实现：打开登录页 -> 用户扫码 -> 检测登录状态 -> 保存Cookie
"""
import os
import re
import json
from typing import Optional, Dict, Tuple

from app.core.base import BasePlatform


class BossAuthMixin(BasePlatform):
    """Boss直聘登录认证混入类"""

    platform = "boss"
    platform_name = "Boss直聘"
    base_url = "https://www.zhipin.com"
    login_url = "https://www.zhipin.com/web/user/?ka=header-login"
    home_url = "https://www.zhipin.com/web/geek/job-recommend"

    # ============ 公开接口 ============
    async def goto_login_page(self) -> bool:
        """打开登录页面，等待用户扫码"""
        self.log("正在打开Boss直聘登录页面...")
        try:
            # 先访问主页（会带上持久化profile里的登录态），再决定是否需要跳登录页
            await self.page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
            await self._human_stay(2, 3)

            # Boss风控：当前IP可能被判定异常，会先弹「安全验证」页（code=35），
            # 需要用户点击『点击按钮进行验证』完成滑块。检测到就提示并等待，最多60秒。
            cur = (self.page.url or "").lower()
            if "verify" in cur or "passport" in cur:
                self.log(
                    "检测到Boss安全验证页（当前IP可能异常）：请在弹出的窗口中点击『点击按钮进行验证』"
                    "完成滑块验证，验证通过后会自动继续"
                )
                import asyncio
                for _ in range(20):
                    cur = (self.page.url or "").lower()
                    if "verify" not in cur and "passport" not in cur:
                        break
                    await asyncio.sleep(3)
                await self._human_stay(1, 2)

            # 若profile里已是登录态，就不再跳登录页，避免“明明登录着却还让重新扫码”
            if await self.is_logged_in():
                self.log("检测到已处于登录状态，无需重新登录")
                return True

            await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
            await self._human_stay(2, 3)
            
            # Boss直聘登录页默认是短信验证码登录，需要切换到扫码登录
            self.log("尝试切换到APP扫码登录...")
            try:
                # 点击"APP扫码登录"切换按钮
                switch_selectors = [
                    ".btn-sign-switch.ewm-switch",
                    ".ewm-switch",
                    "[class*='ewm-switch']",
                    "[class*='sign-switch']",
                ]
                clicked = False
                for sel in switch_selectors:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        self.log(f"已点击扫码登录切换按钮: {sel}")
                        break
                
                if not clicked:
                    # 兜底：用文本匹配
                    await self.page.evaluate("""() => {
                        const els = document.querySelectorAll('div, span, a');
                        for (const el of els) {
                            const t = (el.innerText || '').trim();
                            if (t.includes('APP扫码登录') || t.includes('扫码登录')) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    clicked = True
                
                await self._human_stay(2, 3)
                
                # 等待二维码出现
                qr_selectors = [
                    ".qrcode-box canvas",
                    ".qr-box canvas", 
                    "canvas.qrcode",
                    "[class*='qr'] canvas",
                    ".ewm-box canvas",
                ]
                for sel in qr_selectors:
                    qr = await self.page.query_selector(sel)
                    if qr:
                        self.log(f"二维码已显示: {sel}")
                        break
            except Exception as e:
                self.log(f"切换扫码登录时出错(非致命): {e}")
            
            self.log("登录页面已打开，请在浏览器中用Boss直聘APP扫码登录")
            return True
        except Exception as e:
            self.log(f"打开登录页失败: {e}")
            return False

    async def wait_for_login(self, timeout: int = 180, check_interval: int = 3) -> Tuple[bool, str]:
        """等待用户完成扫码登录，轮询检测状态
        Returns: (success: bool, message: str)
        """
        import asyncio
        self.log(f"等待登录，超时时间: {timeout}秒")
        start_time = self._now()
        while self._now() - start_time < timeout:
            try:
                if await self.is_logged_in():
                    return True, "登录成功"
            except Exception as e:
                self.log(f"检测登录状态出错: {e}")
            # 检查页面是否已跳转到登录后页面
            try:
                cur_url = self.page.url
                if "login" not in cur_url and "user" not in cur_url and await self.is_logged_in():
                    return True, "登录成功"
            except Exception:
                pass
            await asyncio.sleep(check_interval)
        return False, "登录超时"

    async def is_logged_in(self) -> bool:
        """检测是否已登录（关键判断逻辑）"""
        try:
            # 方法0：验证页/登录页/注册页一律视为未登录（2026-08-10 修复：登录页URL /web/user/
            # 被误判为已登录，导致扫码窗口秒关、存下匿名cookies，后续搜索投递全部被Boss打回登录页）
            try:
                cur = (self.page.url or "").lower()
                if any(k in cur for k in ("verify", "passport", "/user/", "login")):
                    return False
            except Exception:
                pass

            # 方法1：检测Cookie中的关键token
            cookies = await self.browser.context.cookies(self.base_url)
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            # Boss直聘关键Cookie：wt2 / __zp_stoken__ / lastip 等
            has_token = any(k in cookie_dict and cookie_dict[k] for k in ["wt2", "__zp_stoken__", "t"])

            if not has_token:
                return False

            # 方法2（权威）：访问需要登录的API，检测返回结果
            # 正确接口：/wapi/zpuser/wap/getUserInfo.json（旧 /wapi/zpgeek/user/info.json 已失效，恒4404）
            # 注意：必须用页面内 fetch（带页面安全头），用 page.request 会缺安全头恒返回 code=7 误判未登录
            try:
                data = await self.page.evaluate("""async () => {
                    try {
                        const r = await fetch('/wapi/zpuser/wap/getUserInfo.json', {credentials: 'include'});
                        return await r.json();
                    } catch (e) { return {code: -1, message: String(e)}; }
                }""")
                if data:
                    code = data.get("code")
                    # code=0 且有用户数据 = 确定已登录
                    if code == 0 and data.get("zpData"):
                        return True
                    # code=401/403/5001~5003 等 = 确定未登录
                    if code in (401, 403, 5001, 5002, 5003):
                        return False
                    # 其他 code（含匿名 code=7、安全验证 code=35 等）一律视为未登录，
                    # 不再落入DOM误判（登录页的 .user-nav 会假阳性）
                    return False
            except Exception:
                # 网络异常/超时，不作权威判定，继续 DOM 和兜底逻辑
                pass
            # 方法3：检测页面上的用户头像/登录入口
            try:
                # 存在登录表单（短信验证码/扫码登录页特征）=> 确定未登录
                login_form = await self.page.query_selector(
                    ".sign-form, [class*='sign-form'], input[placeholder*='验证码'], input[placeholder*='手机号']"
                )
                if login_form:
                    return False
                # 如果页面上能找到登录按钮，说明没登录
                login_btn = await self.page.query_selector("a.btn-login, .nav-login-btn, [ka='header-login']")
                if login_btn:
                    return False
                # 能找到用户头像或用户菜单，说明已登录
                user_el = await self.page.query_selector(".user-nav, .nav-username, .user-avatar")
                if user_el:
                    return True
            except Exception:
                pass

            # 方法4（兜底）：匿名访问Boss也会下发wt2等token，不能作为已登录依据，一律判未登录
            return False
        except Exception:
            return False

    async def get_account_info(self) -> Dict:
        """获取当前登录的账号信息（昵称、头像、ID）"""
        info = {"account_name": "", "account_avatar": "", "account_id": ""}
        try:
            # 方式1：从页面内 fetch 获取（带页面安全头，
            # 比 page.request 更可靠：直接用 page.request 会缺少安全头而返回 code=7）
            try:
                data = await self.page.evaluate("""async () => {
                    try {
                        const r = await fetch('/wapi/zpuser/wap/getUserInfo.json', {credentials: 'include'});
                        return await r.json();
                    } catch (e) { return {code: -1, message: String(e)}; }
                }""")
                if data and data.get("code") == 0 and data.get("zpData"):
                    zp = data["zpData"]
                    info["account_name"] = zp.get("name") or zp.get("showName") or zp.get("nickName") or ""
                    info["account_avatar"] = zp.get("avatar") or zp.get("headImg") or zp.get("tinyAvatar") or ""
                    info["account_id"] = str(zp.get("userId") or zp.get("uid") or zp.get("encryptUserId") or "")
            except Exception:
                pass
        except Exception:
            pass

        # 方式2：从页面DOM获取（API失败时兜底）
        if not info["account_name"]:
            try:
                name_el = await self.page.query_selector(".user-nav .name, .nav-username, .user-info .name")
                if name_el:
                    info["account_name"] = (await name_el.inner_text()).strip()
            except Exception:
                pass
        return info

    # ============ 工具方法 ============
    def _now(self) -> float:
        import time
        return time.time()

    async def _human_stay(self, min_t: float = 0.5, max_t: float = 1.5, page_obj=None):
        """模拟人类停留：顺便滚动几下页面"""
        from app.core.base import async_random_sleep
        await async_random_sleep(min_t, max_t)
        try:
            # 随机滚动一下
            page = page_obj or self.page
            scroll_y = (await page.evaluate("() => window.scrollY")) or 0
            await page.evaluate(f"window.scrollTo(0, {scroll_y + 100})")
            await async_random_sleep(0.2, 0.5)
        except Exception:
            pass
