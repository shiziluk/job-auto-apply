"""
自动跟进服务：扫描 Boss 聊天页 -> 匹配投递记录 -> 更新跟进状态
- 供 API（POST /api/apply/followup/run）与后台周期任务共用
- 只在检测到 HR 新消息时更新状态；none 保持 none；已推进状态只升不降
"""
import asyncio
import datetime
import re
import sys
import time
from typing import Dict, Optional

from app.core import BrowserContextManager, create_platform

# 状态优先级：数字越大越接近终态；只允许升级，不允许回退
STATUS_PRIORITY = {"none": 0, "replied": 1, "rejected": 2, "interviewed": 3, "offer": 4}

_LAST_SCAN: Dict = {}
# 账号级风控冷却：Boss 403 code=32 限制访问时记录到期时间（datetime），到期前不再开浏览器
_RISK_UNTIL: Optional[datetime.datetime] = None

# 风控403页里的恢复时间文案，如“将于 2026-08-11 18:10 恢复”
_RESTORE_RE = re.compile(r"将于\s*(\d{4}-\d{2}-\d{2})\s*(\d{1,2}:\d{2})\s*恢复")


async def _parse_restore_time(page_obj) -> Optional[datetime.datetime]:
    """从风控403页解析恢复时间；解析失败返回None"""
    try:
        text = (await page_obj.evaluate("() => document.body.innerText || ''")) or ""
    except Exception:
        return None
    text = text.replace("\u00a0", " ")
    m = _RESTORE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def get_last_scan() -> Dict:
    """最近一次跟进扫描的结果（供状态接口查询）"""
    return dict(_LAST_SCAN)


def run_followup_scan_sync(user_id: int, session_id: Optional[int] = None,
                           headless: Optional[bool] = None, force: bool = False) -> Dict:
    """同步入口：在独立线程+ProactorEventLoop 中运行扫描（与搜索/投递同模式）
    force=True 时忽略风控冷却，立即重新检测（用户手动点击"自动跟进"时使用）"""
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_followup_scan(user_id, session_id, headless, force))
    finally:
        loop.close()


def _is_risk_controlled(page_obj) -> bool:
    try:
        cur = (page_obj.url or "").lower()
        if "verify" in cur or "passport" in cur or "about:blank" in cur:
            return True
    except Exception:
        pass
    return False


async def run_followup_scan(user_id: int, session_id: Optional[int] = None,
                            headless: Optional[bool] = None, force: bool = False) -> Dict:
    """执行一次自动跟进扫描，返回统计信息。
    注意：不要先访问Boss首页做登录预检——首页会触发 code=32 风控页（403），
    直接打开聊天页（实测可正常加载会话列表）。
    force=True：忽略冷却，立即开浏览器重新检测（用户手动点击"自动跟进"时使用；
    若客服已提前解封，可用此参数绕过冷却）。
    """
    from app.database import SessionLocal
    from app.models import ApplyRecord, PlatformSession

    global _RISK_UNTIL
    t0 = time.monotonic()
    db = SessionLocal()
    browser = None
    try:
        # 0. 账号级风控冷却期内直接跳过，不再开浏览器打扰用户（force=True 时忽略）
        now = datetime.datetime.now()
        if not force and _RISK_UNTIL and now < _RISK_UNTIL:
            result = {
                "scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                "risk_blocked": True, "cooldown_until": _RISK_UNTIL.isoformat(timespec="seconds"),
                "error": f"Boss账号被风控临时限制访问，冷却至 {_RISK_UNTIL:%m-%d %H:%M} 自动恢复",
                "elapsed": round(time.monotonic() - t0, 1),
                "run_at": now.isoformat(timespec="seconds"),
            }
            _LAST_SCAN.clear()
            _LAST_SCAN.update(result)
            return result

        # 1. 找到已登录的 Boss 会话
        q = db.query(PlatformSession).filter(PlatformSession.user_id == user_id)
        if session_id:
            q = q.filter(PlatformSession.id == session_id)
        session = q.filter(PlatformSession.platform == "boss").order_by(PlatformSession.id.desc()).first()
        if not session:
            return {"scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                    "risk_blocked": False, "error": "未找到Boss平台会话，请先登录"}
        if not session.is_logged_in:
            return {"scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                    "risk_blocked": False, "error": "Boss会话未登录，请先扫码登录"}
        cookies = session.cookies or []

        # 2. 启动浏览器（默认有头：若弹滑块/需扫码，窗口保留等待用户处理）
        browser = BrowserContextManager(headless=False if headless is None else headless)
        await browser.start()
        pf = create_platform("boss", browser)

        # 3. profile里若没有登录token，才注入DB保存的cookies（避免覆盖profile里更新的登录态）
        try:
            ctx_cookies = await browser.context.cookies("https://www.zhipin.com")
            has_token = any(c.get("name") in ("wt2", "__zp_stoken__") and c.get("value") for c in ctx_cookies)
        except Exception:
            has_token = False
        if not has_token and cookies:
            try:
                await browser.context.add_cookies(cookies)
            except Exception as e:
                print(f"[跟进] 注入cookies失败: {e}")

        # 4. 直接抓取聊天会话（内部已处理风控检测：verify/passport 直接返回空）
        sessions = await pf.fetch_chat_sessions()

        # 5. 空结果时区分原因：滑块验证->等待用户处理；登录页->提示扫码；其余重试一次
        cur_url = ""
        try:
            cur_url = (browser.page.url or "").lower()
        except Exception:
            pass
        risk_blocked = False
        if not sessions:
            if "code=32" in cur_url or "403" in cur_url:
                # Boss账号级风控：403 访问受限页（“账户存在异常行为，将于 xx 恢复”）
                restore = await _parse_restore_time(browser.page)
                if restore:
                    _RISK_UNTIL = restore
                    print(f"[跟进] 账号被Boss风控限制访问，冷却至 {restore} 自动恢复")
                    return {"scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                            "risk_blocked": True, "cooldown_until": restore.isoformat(timespec="seconds"),
                            "error": f"Boss账号被风控临时限制访问（将于 {restore:%m-%d %H:%M} 恢复），自动跟进暂停，到期自动恢复"}
                risk_blocked = True
                return {"scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                        "risk_blocked": True,
                        "error": "Boss账号被风控限制访问（403），请登录Boss直聘网页端查看解封时间"}
            if "verify" in cur_url or "security" in cur_url:
                # 风控滑块：保留窗口等用户处理（最多60秒），完成后重试一次
                risk_blocked = True
                waited = 0
                while waited < 60 and _is_risk_controlled(browser.page):
                    print(f"[跟进] 检测到安全验证页，等待用户完成滑块... {waited}s")
                    await asyncio.sleep(3)
                    waited += 3
                    try:
                        await browser.page.bring_to_front()
                    except Exception:
                        pass
                if not _is_risk_controlled(browser.page):
                    sessions = await pf.fetch_chat_sessions()
            elif "passport" in cur_url or "login" in cur_url:
                # 登录页：等待用户扫码（最多60秒）
                print("[跟进] 检测到登录页，等待用户扫码登录...")
                waited = 0
                while waited < 60:
                    try:
                        if not _is_risk_controlled(browser.page) and await pf.is_logged_in():
                            sessions = await pf.fetch_chat_sessions()
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(3)
                    waited += 3
                    try:
                        await browser.page.bring_to_front()
                    except Exception:
                        pass
                if not sessions:
                    return {"scanned": 0, "matched": 0, "updated": 0, "by_status": {},
                            "risk_blocked": False,
                            "error": "Boss会话未就绪：请在弹出的浏览器窗口中扫码登录后重试"}

        # 6. 登录就绪后同步cookies回数据库，避免下次再扫码
        try:
            storage_state = await browser.context.storage_state()
            db.query(PlatformSession).filter(PlatformSession.id == session.id).update({
                "cookies": storage_state.get("cookies", []),
                "local_storage": [o for o in storage_state.get("origins", []) if o.get("localStorage")] or None,
                "session_storage": [o for o in storage_state.get("origins", []) if o.get("sessionStorage")] or None,
                "is_logged_in": True,
                "last_check_at": datetime.datetime.now(),
            })
            db.commit()
        except Exception as e:
            print(f"[跟进] 同步cookies到数据库失败: {e}")

        # 7. 拉取投递记录并匹配更新
        records = db.query(ApplyRecord).filter(
            ApplyRecord.user_id == user_id,
            ApplyRecord.platform == "boss",
        ).all()
        matched = 0
        updated = 0
        by_status = {}
        for rec in records:
            hit = None
            for s in sessions:
                if pf._match_record(s, rec.company_name or "", rec.hr_name or ""):
                    hit = s
                    break
            if hit is None:
                continue
            matched += 1
            new_status = pf._detect_session_status(hit, own_greeting=rec.greeting_sent or "")
            if new_status == "none":
                continue
            old_status = rec.follow_up_status or "none"
            if STATUS_PRIORITY.get(new_status, 1) < STATUS_PRIORITY.get(old_status, 0):
                continue  # 不降级
            remark = pf._build_remark(new_status, hit)
            if new_status != old_status or (remark and remark != (rec.follow_up_remark or "")):
                rec.follow_up_status = new_status
                rec.follow_up_remark = remark
                rec.updated_at = datetime.datetime.now()
                updated += 1
            by_status[new_status] = by_status.get(new_status, 0) + 1

        db.commit()
        result = {
            "scanned": len(sessions),
            "records": len(records),
            "matched": matched,
            "updated": updated,
            "by_status": by_status,
            "risk_blocked": risk_blocked,
            "elapsed": round(time.monotonic() - t0, 1),
            "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        _LAST_SCAN.clear()
        _LAST_SCAN.update(result)
        if _RISK_UNTIL:
            _RISK_UNTIL = None
        print(f"[跟进] 扫描完成: {result}")
        return result

    finally:
        db.close()
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
