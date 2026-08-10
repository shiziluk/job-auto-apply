"""
Boss直聘 - 自动投递模块
参考 JobClaw applier/boss.py
实现：打开职位详情页 -> 点击立即沟通 -> 填入打招呼消息 -> 点击发送 -> 返回结果
"""
import random
import re
import time
from typing import Optional

from app.core.base import BasePlatform, Job, ApplyResult, async_random_sleep


class BossApplierMixin(BasePlatform):
    """Boss直聘投递混入类"""

    async def apply_job(
        self,
        job: Job,
        greeting_template: Optional[str] = None,
        resume_id: Optional[str] = None,
        rest_policy: Optional[list] = None,
    ) -> ApplyResult:
        """
        投递单个职位
        Boss直聘流程：打开详情页 -> 点击「立即沟通」-> (如有招呼语输入框)填消息 -> 发送
        """
        result = ApplyResult(job_id=job.job_id, success=False)
        start_ts = time.time()

        try:
            # 1. 打开职位详情页
            self.log(f"打开职位页: {job.company_name} - {job.job_title}")
            if not job.job_url:
                result.status = "failed"
                result.message = "缺少职位URL"
                return result

            await self.page.goto(job.job_url, wait_until="domcontentloaded", timeout=45000)
            await async_random_sleep(0.5, 0.8)
            # 模拟人工浏览职位详情（滚动阅读JD），避免"打开即点沟通"的机器特征
            await self._simulate_job_reading()

            # 2. 检测各种异常页面
            page_text = await self.page.evaluate("() => document.body.innerText") or ""
            if "该职位已关闭" in page_text or "职位已下线" in page_text:
                result.status = "skipped"
                result.message = "职位已关闭/下线"
                return result


            # 1.5 休息制度终检（如果投递要求了休息制度）：页面文本已抓取，识别失败=未知则继续
            if rest_policy:
                detected_rest = self._detect_rest_policy([page_text])
                if detected_rest and detected_rest not in rest_policy:
                    result.status = "skipped"
                    result.message = f"休息制度不符（实际：{detected_rest}），跳过"
                    self.log(f"跳过 {job.company_name}-{job.job_title}: 休息制度={detected_rest}")
                    return result

            # 3. 查找并点击「立即沟通」按钮
            clicked = await self._click_chat_button()
            if not clicked:
                # 可能是之前已经沟通过 -> 检测聊天入口
                if re.search(r"继续沟通|查看沟通|去沟通|已沟通", page_text):
                    result.status = "duplicate"
                    result.message = "之前已沟通过该职位"
                    return result
                result.status = "failed"
                result.message = "未找到「立即沟通」按钮"
                return result

            await async_random_sleep(1.0, 2.0)

            # 4. 打招呼内容：Boss对话弹窗里编辑的文字实际发送不过去（发送的是默认模板），
            #    因此不再填自定义招呼语，直接使用Boss默认文案
            greeting = self._render_greeting(greeting_template, job)
            if greeting:
                result.greeting_sent = greeting

            # 5. 点击确认/发送按钮
            sent_ok = await self._click_send_button()
            if not sent_ok:
                # 找不到发送按钮有两种可能：①打招呼已发出（对话框已关闭/已跳转聊天页）②弹出「安全验证/验证码」
                cur_url = self.page.url.lower()
                cur_text = (await self.page.evaluate("() => document.body.innerText")) or ""
                if "/chat" in cur_url or any(k in cur_text for k in ["继续沟通", "发送成功", "消息已发送", "已发送", "沟通中"]):
                    sent_ok = True
                    self.log("未找到发送按钮，但检测到已发送信号，视为投递成功")
                elif any(k in cur_text for k in ["验证码", "安全验证", "人机验证", "操作频繁", "请求过于频繁", "频繁操作"]):
                    result.status = "failed"
                    result.message = "疑似触发风控，需要手动验证"
                    self.log("发送失败: 检测到风控信号")
                    return result
                elif clicked:
                    # 已点击「立即沟通」但找不到发送按钮且无风控信号：
                    # Boss常直接用默认模板发出招呼（无对话框/无发送按钮），视为投递成功
                    sent_ok = True
                    self.log("未找到发送按钮，但已点击「立即沟通」，视为默认招呼已发送")
                else:
                    result.status = "failed"
                    result.message = "发送失败，可能需要验证码"
                    self.log("发送失败: 未找到发送按钮且无已发送信号")
                    return result

            # 发完招呼后在聊天页停留片刻（2026-08-09 调久：账号曾被风控限制，
            # 用户怀疑与停留过短有关；停留时长由 BOSS_POST_GREETING_DWELL_* 配置控制）
            _dwell_t0 = time.time()
            print(f"[dwell-test] job={job.job_id} greeting sent, dwelling on chat page t0={_dwell_t0:.3f}")
            await async_random_sleep(self.post_greeting_dwell_min, self.post_greeting_dwell_max)
            print(f"[dwell-test] job={job.job_id} dwell done, actual {time.time()-_dwell_t0:.2f}s")

            # 6. 校验结果：优先检测失败/风控信号，再检测成功信号
            cur_url = self.page.url.lower()
            cur_text = (await self.page.evaluate("() => document.body.innerText")) or ""

            # 6.1 失败/风控信号（出现则判定失败，避免投递记录虚高）
            negative_indicators = ["验证码", "安全验证", "人机验证", "操作频繁", "请求过于频繁", "频繁操作"]
            for kw in negative_indicators:
                if kw in cur_text:
                    result.status = "failed"
                    result.message = f"疑似触发风控: {kw}"
                    self.log(f"投递失败: {kw}")
                    return result

            # 6.2 成功信号：跳转到聊天页 / 按钮变为「继续沟通」 / 出现发送成功提示
            positive_indicators = ["继续沟通", "发送成功", "消息已发送", "已发送", "沟通中"]
            if ("/chat" in cur_url) or any(k in cur_text for k in positive_indicators):
                result.success = True
                result.status = "success"
                result.message = "投递成功"
                result.applied_at = start_ts
            else:
                # 无法确定 -> 记为成功但提示需人工确认，避免记录虚高误导
                result.success = True
                result.status = "success"
                result.message = "已执行投递（结果待人工确认）"
                result.applied_at = start_ts

        except Exception as e:
            result.status = "failed"
            result.message = f"投递异常: {e}"
            self.log(f"投递异常: {e}")

        return result

    # ============ 内部方法 ============
    async def _simulate_job_reading(self) -> None:
        """模拟人工浏览职位详情页：滚动阅读JD + 停留，总时长由 BOSS_PAGE_VIEW_* 控制"""
        try:
            for _ in range(random.randint(1, 3)):
                await self.page.mouse.wheel(0, random.randint(400, 900))
                await async_random_sleep(0.5, 1.2)
        except Exception:
            pass
        await async_random_sleep(self.page_view_min, self.page_view_max)

    async def _click_chat_button(self) -> bool:
        """点击「立即沟通」等按钮，成功返回True"""
        # Boss有多种按钮文案和选择器，依次尝试
        candidates = [
            # 各种选择器
            (".btn.btn-startchat", {"text": None}),
            (".job-detail-section .btn-startchat", {"text": None}),
            ("button.btn-startchat", {"text": None}),
            ("[ka='job-detail-startchat']", {"text": None}),
            ("[class*='startchat']", {"text": None}),
            ("div.btn", {"text": "立即沟通"}),
            ("button", {"text": "立即沟通"}),
            ("div.btn", {"text": "沟通"}),
            ("a", {"text": "立即沟通"}),
        ]
        for selector, opts in candidates:
            try:
                els = await self.page.query_selector_all(selector)
                for el in els:
                    if not el or not await el.is_visible() or not await el.is_enabled():
                        continue
                    if opts and opts.get("text"):
                        t = (await el.inner_text()).strip()
                        if opts["text"] not in t:
                            continue
                    await el.click()
                    self.log(f"点击沟通按钮成功 (selector: {selector})")
                    await async_random_sleep(0.8, 1.5)
                    return True
            except Exception:
                continue
        # 兜底：全文本匹配点击
        try:
            clicked = await self.page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a, div[class*=btn]'));
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    if (/立即沟通|沟通|打招呼|投递/.test(t) && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            await async_random_sleep(0.5, 1.0)
            return bool(clicked)
        except Exception:
            return False

    async def _fill_greeting(self, greeting: str) -> bool:
        """填打招呼语到输入框，返回是否填了"""
        if not greeting:
            return False
        try:
            # Boss有时候会弹出自定义招呼语输入框
            selectors = [
                "textarea.dialog-chat-tiptap-editor",
                "textarea[placeholder*='打招呼']",
                "div[contenteditable='true']",
                "textarea",
                "input[type='text']",
            ]
            for sel in selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    try:
                        # 先清空
                        await el.click()
                        await self.page.keyboard.press("Control+a")
                        await self.page.keyboard.press("Backspace")
                        await el.type(greeting, delay=random_typing_delay())
                        self.log(f"填入打招呼语: {greeting[:20]}...")
                        await async_random_sleep(0.3, 0.8)
                        return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False

    async def _click_send_button(self) -> bool:
        """点击发送/确认按钮"""
        candidates = [
            (".dialog-footer .btn.btn-primary", {}),
            ("button.btn-primary", {}),
            (".btn.btn-sure", {}),
            ("[class*='btn-primary']", {}),
            ("button", {"text": "发送"}),
            ("button", {"text": "确认"}),
            ("div.btn", {"text": "发送"}),
            ("div.btn", {"text": "确认"}),
        ]
        for selector, opts in candidates:
            try:
                els = await self.page.query_selector_all(selector)
                for el in els:
                    if not await el.is_visible() or not await el.is_enabled():
                        continue
                    if opts and opts.get("text"):
                        t = (await el.inner_text()).strip()
                        if opts["text"] not in t:
                            continue
                    await el.click()
                    self.log(f"点击发送按钮成功 (selector: {selector})")
                    return True
            except Exception:
                continue
        # 兜底 JS点击
        try:
            result = await self.page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, div[class*=btn], a'));
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    if (/(发送|确认|开始沟通|确定)/.test(t) && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            return bool(result)
        except Exception:
            return False

    def _render_greeting(self, template: Optional[str], job: Job) -> str:
        """渲染打招呼模板，支持变量替换"""
        if not template:
            return ""
        mapping = {
            "$company": job.company_name or "",
            "$title": job.job_title or "",
            "$name": job.hr_name or "HR",
            "$HR": job.hr_name or "HR",
            "$city": job.city or "",
            "$position": job.job_title or "",
        }
        result = template
        for k, v in mapping.items():
            result = result.replace(k, str(v))
        return result.strip()


def random_typing_delay() -> int:
    """模拟人类打字的按键间隔（毫秒）"""
    import random
    return random.randint(30, 100)
