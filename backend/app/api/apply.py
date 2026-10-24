"""
职位搜索 & 投递 & 投递记录 查询 API
对接 Playwright 的 search_jobs / apply_batch 能力
"""
import os
import json
import time
import asyncio
import datetime
from typing import Optional, List, Dict, Any
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import (
    User, PlatformSession, Resume, ApplyTask, ApplyRecord, FilterRule,
)
from app.schemas import (
    JobSearchRequest, JobItem, ApplyJobsRequest, ResponseModel,
    PageResult, ApplyTaskCreate, ApplyTaskUpdate, ApplyTaskInfo,
    ApplyRecordInfo,
    FollowUpRunRequest,
)
from app.api.deps import get_current_user, get_page_params, make_page_result, paginate_query

router = APIRouter(tags=["职位搜索与投递"])

# ============ 全局投递任务状态（MVP内存版） ============
RUNNING_APPLY_TASKS: Dict[str, Dict] = {}

# 搜索级风控冷却：触发Boss安全验证后全局冷却，避免12个并发组合连环触发验证页
_SEARCH_RISK_AT = 0.0  # time.monotonic() 时间戳
_SEARCH_RISK_COOLDOWN_SECONDS = 300


def _search_risk_cooldown_active() -> bool:
    return time.monotonic() - _SEARCH_RISK_AT < _SEARCH_RISK_COOLDOWN_SECONDS


def _set_search_risk_cooldown():
    global _SEARCH_RISK_AT
    _SEARCH_RISK_AT = time.monotonic()


# ============ 1. 搜索职位 ============
@router.post("/job/search", response_model=ResponseModel[List[JobItem]])
async def search_jobs(
    req: JobSearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    调用Playwright搜索职位
    注意：此接口会阻塞等待（最多~30秒），建议配合loading状态
    """
    from app.core import BrowserContextManager, create_platform

    # 1. 取会话
    session = db.query(PlatformSession).filter(
        PlatformSession.id == req.session_id,
        PlatformSession.user_id == user.id,
        PlatformSession.platform == req.platform if hasattr(req, 'platform') else True
    ).first()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "平台会话不存在，请先登录")
    if not session.is_logged_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "会话未登录，请重新扫码登录")
    if not session.cookies:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cookie已丢失，请重新登录")

    # 2. 已投递的job_id集合（去重用）
    today = datetime.date.today()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    already_applied = set(
        r[0] for r in db.query(ApplyRecord.job_id).filter(
            ApplyRecord.user_id == user.id,
            ApplyRecord.platform == "boss",
            ApplyRecord.created_at >= today_start
        ).all() if r[0]
    )

    # 2.5 已投递过的公司集合（历史记录，过滤该公司下所有职位，避免重复投同一家公司；
    #     不限投递状态——凡发起过招呼的公司都不再推荐；删除投递记录后可恢复）
    applied_company_ids = set(
        r[0] for r in db.query(ApplyRecord.company_id).filter(
            ApplyRecord.user_id == user.id,
            ApplyRecord.platform == "boss",
            ApplyRecord.company_id.isnot(None),
        ).all() if r[0]
    )
    # 公司名集合：兼容历史投递记录没有company_id的情况（用名称过滤，名称匹配兜底）
    applied_company_names = set(
        r[0] for r in db.query(ApplyRecord.company_name).filter(
            ApplyRecord.user_id == user.id,
            ApplyRecord.platform == "boss",
            ApplyRecord.company_name.isnot(None),
            ApplyRecord.company_name != "",
        ).all() if r[0]
    )

    # 3. 黑白名单规则
    rules = db.query(FilterRule).filter(
        FilterRule.user_id == user.id, FilterRule.is_enabled == 1
    ).order_by(FilterRule.priority.desc()).all()
    rule_dicts = [
        {
            "rule_type": r.rule_type, "match_field": r.match_field,
            "match_mode": r.match_mode, "keywords": r.keywords,
        }
        for r in rules
    ]

    browser = None
    try:
        # 在独立线程+ProactorEventLoop中运行Playwright搜索
        search_result = await asyncio.to_thread(
            _run_search_sync,
            session.cookies or [],
            req.keywords,
            req.city_code,
            req.salary_min,
            req.salary_max,
            req.experience,
            req.education,
            req.company_scales,
            req.rest_policy,
            req.page,
            req.page_size,
            already_applied,
            applied_company_ids,
            applied_company_names,
            rule_dicts,
            req.headless,
            getattr(req, "jd_ai_check", True),
        )
        result = search_result
        return ResponseModel.success(data=result, message=f"抓取到 {len(result)} 个职位")

    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "安全验证" in msg or "风控" in msg:
            return ResponseModel.error(message=msg, code=400)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"搜索失败: {e}")


def _run_search_sync(cookies, keywords, city_code, salary_min, salary_max,
                     experience, education, company_scales, rest_policy, page, page_size,
                     already_applied, applied_company_ids, applied_company_names,
                     rule_dicts, headless=None, jd_ai_check=True):
    """在独立线程中运行搜索"""
    import asyncio
    import sys
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_do_search(
            cookies, keywords, city_code, salary_min, salary_max,
            experience, education, company_scales, rest_policy, page, page_size,
            already_applied, applied_company_ids, applied_company_names, rule_dicts, headless,
            jd_ai_check,
        ))
    finally:
        loop.close()


def _is_risk_controlled(page_obj) -> bool:
    """判断当前页面是否被目标站点风控拦截（安全验证/登录/空白页）"""
    try:
        cur = (page_obj.url or "").lower()
        if "verify" in cur or "passport" in cur or "about:blank" in cur:
            return True
    except Exception:
        pass
    return False


async def _check_risk_control(page_obj) -> None:
    """检测目标站点风控/安全验证，命中时抛出带操作指引的异常"""
    if not _is_risk_controlled(page_obj):
        return
    cur = (page_obj.url or "").lower()
    if "about:blank" in cur:
        raise RuntimeError("浏览器被目标站点风控拦截（页面被关闭），建议在「平台登录」页完成一次安全验证后再重试")
    raise RuntimeError("触发Boss安全验证（当前IP可能异常）：请在弹出的浏览器窗口中点击『点击按钮进行验证』完成滑块，验证通过后会自动继续")


async def _try_recover_risk(page_obj) -> bool:
    """尝试从风控页恢复：重新导航到Boss首页；恢复成功返回True"""
    try:
        await page_obj.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1.5)
        return not _is_risk_controlled(page_obj)
    except Exception:
        return False


async def _do_search(cookies, keywords, city_code, salary_min, salary_max,
                     experience, education, company_scales, rest_policy, page, page_size,
                     already_applied, applied_company_ids, applied_company_names,
                     rule_dicts, headless=None, jd_ai_check=True):
    """实际的搜索流程（支持多关键词/多城市：单个浏览器逐个搜索，按job_id去重合并）"""
    from app.core import BrowserContextManager, create_platform

    # 休息制度筛选归一化（双休/大小周/单休，可多选）
    rest_sel = []
    if isinstance(rest_policy, str):
        rest_sel = [x.strip() for x in rest_policy.split(",") if x.strip()]
    elif isinstance(rest_policy, (list, tuple)):
        rest_sel = [str(x).strip() for x in rest_policy if str(x).strip()]
    rest_sel = list(dict.fromkeys(rest_sel))

    # 关键词归一化为列表（去重保序，避免重复关键词重复搜索浪费名额）
    if isinstance(keywords, str):
        raw_kw = [k.strip() for k in keywords.split(",") if k.strip()]
    elif isinstance(keywords, (list, tuple)):
        raw_kw = []
        for k in keywords:
            if isinstance(k, str):
                raw_kw.extend([x.strip() for x in k.split(",") if x.strip()])
    else:
        raw_kw = []
    kw_list = list(dict.fromkeys(raw_kw))
    if not kw_list:
        kw_list = [""]

    # 城市归一化为列表（BOSS单次搜索只支持单个城市，多城市时逐个搜索再合并去重；空=全国）
    if isinstance(city_code, str):
        city_list = [c.strip() for c in city_code.split(",") if c.strip()]
    elif isinstance(city_code, (list, tuple)):
        city_list = [str(c).strip() for c in city_code if str(c).strip()]
    else:
        city_list = []
    if not city_list:
        city_list = [None]

    browser = None
    try:
        # 使用持久化profile（与登录同一用户数据目录）：登录态/指纹一致，规避Boss风控导致搜索失败
        browser = BrowserContextManager(headless=headless)
        await browser.start()
        page_obj = browser.page
        await page_obj.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(1)

        pf_check = create_platform("boss", browser)
        is_logged_in = await pf_check.is_logged_in()
        if not is_logged_in:
            try:
                await browser.context.add_cookies(cookies)
                await page_obj.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(2)
            except Exception:
                pass

        pf = create_platform("boss", browser)
        all_jobs = []
        seen = set()

        # 多关键词×多城市组合：先保证每个城市至少覆盖一个关键词，再按序补齐（上限12个组合防过度并发）
        combos = [(kw, city) for kw in kw_list for city in city_list]
        MAX_COMBOS = 12
        if len(combos) > MAX_COMBOS:
            city_first, extra, seen_city = [], [], set()
            for c in combos:
                if c[1] not in seen_city:
                    seen_city.add(c[1])
                    city_first.append(c)
                else:
                    extra.append(c)
            combos = (city_first + extra)[:MAX_COMBOS]

        combo_sem = asyncio.Semaphore(5)  # 并发标签页上限5个，避免触发Boss风控

        async def _do_search_once(tab, kw, city):
            return await pf.search_jobs(
                page_obj=tab,
                keywords=kw, city_code=city,
                salary_min=salary_min, salary_max=salary_max,
                experience=experience, education=education,
                company_scales=company_scales,
                rest_policy=rest_sel,
                page=page, page_size=page_size,
                already_applied_ids=already_applied,
                applied_company_ids=applied_company_ids,
                applied_company_names=applied_company_names,
                filter_rules=rule_dicts,
                jd_ai_check=jd_ai_check,
            )

        async def _search_one(kw, city):
            async with combo_sem:
                if _search_risk_cooldown_active():
                    print(f"[搜索] 风控冷却中（5分钟内触发过安全验证），跳过 关键词[{kw}] 城市[{city}]")
                    return []
                t0 = time.monotonic()
                try:
                    tab = await browser.context.new_page()
                    try:
                        jobs = await _do_search_once(tab, kw, city)
                        try:
                            await _check_risk_control(tab)
                        except RuntimeError as re_:
                            if headless:
                                _set_search_risk_cooldown()
                                raise
                            # 有头模式：等待用户手动完成滑块验证（最多120s），完成后自动重试一次
                            print(f"[搜索] 触发安全验证，请在弹出的浏览器窗口中手动完成滑块（最多等待120秒）...")
                            deadline = time.monotonic() + 120
                            solved = False
                            while time.monotonic() < deadline:
                                await asyncio.sleep(3)
                                try:
                                    if not _is_risk_controlled(tab):
                                        solved = True
                                        break
                                except Exception:
                                    pass
                            if not solved:
                                raise re_
                            print(f"[搜索] 滑块验证已通过，自动重试搜索...")
                            jobs = await _do_search_once(tab, kw, city)
                            await _check_risk_control(tab)
                        print(f"[搜索] 关键词[{kw}] 城市[{city}] 耗时{time.monotonic()-t0:.1f}s 得到{len(jobs)}个职位")
                        return jobs
                    finally:
                        try:
                            await tab.close()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[搜索] 关键词[{kw}] 城市[{city}] 失败: {e}")
                    return []

        results = await asyncio.gather(
            *[_search_one(kw, city) for kw, city in combos],
            return_exceptions=True,
        )
        # 指定休息制度时预留一点余量（最多120），补详情页识别休息制度后再严格过滤
        merge_cap = 120 if rest_sel else 100
        for jobs in results:
            if isinstance(jobs, Exception) or not jobs:
                continue
            for j in jobs:
                if len(all_jobs) >= merge_cap:
                    break
                if j.job_id not in seen:
                    seen.add(j.job_id)
                    all_jobs.append(j)

        # 补充休息制度：Boss列表接口不返回双休信息，只有详情页有；并发上限4个标签页，失败降级为未知
        sem = asyncio.Semaphore(4)

        async def _enrich_one(job, company_fallback=False):
            async with sem:
                try:
                    tab = await browser.context.new_page()
                    try:
                        job.rest_policy = await pf.enrich_rest_policy(job, page_obj=tab, company_fallback=True)
                    finally:
                        try:
                            await tab.close()
                        except Exception:
                            pass
                except Exception:
                    pass
        if rest_sel:
            # 并发补充休息制度；限制补充数量（每个详情页约2-4s，全量补充会拖慢搜索）
            unknown_rest = [j for j in all_jobs if not j.rest_policy]
            enrich_cap = min(len(unknown_rest), 10)
            await asyncio.gather(*[_enrich_one(j, company_fallback=True) for j in unknown_rest[:enrich_cap]], return_exceptions=True)
            # 只剔除确认不符合（单休/大小周）的；未知的保留，避免“0结果”，明确双休的排前
            excluded = [j for j in all_jobs if j.rest_policy and j.rest_policy not in rest_sel]
            kept = [j for j in all_jobs if not j.rest_policy or j.rest_policy in rest_sel]
            kept.sort(key=lambda j: 0 if j.rest_policy in rest_sel else 1)
            all_jobs = kept
            print("[\u641c\u7d22] \u4f11\u606f\u5236\u5ea6\u8fc7\u6ee4: \u6392\u9664%d\u4e2a\uff08\u8981\u6c42 %s\uff09\uff0c\u4fdd\u7559%d\u4e2a\uff08\u5176\u4e2d\u660e\u786e\u5339\u914d%d\u4e2a\uff09" % (len(excluded), "/".join(rest_sel), len(kept), sum(1 for j in kept if j.rest_policy in rest_sel)))
        else:
            # 默认：只补最相关前15条用于展示，失败降级为未知
            await asyncio.gather(*[_enrich_one(j) for j in all_jobs[:15]], return_exceptions=True)

        # JD级AI校验：Boss按JD匹配搜索词，标题通用的岗位（如"研发工程师"）先读JD
        # 确认是否AI应用开发岗；JD无AI关键词的一律剔除（避免芯片/嵌入式/化学等通用岗混入）
        jd_cands = [j for j in all_jobs if getattr(j, "need_jd_check", False)]
        if jd_cands:
            jd_cands = jd_cands[:15]
            sem_jd = asyncio.Semaphore(4)

            async def _jd_check_one(job):
                async with sem_jd:
                    try:
                        tab = await browser.context.new_page()
                        try:
                            ok = await pf.jd_has_ai(job, page_obj=tab)
                            if ok:
                                job.jd_ai_verified = True
                                job.match_reason = "JD含AI关键词，通过"
                            else:
                                job.match_reason = "JD无AI内容，剔除"
                        finally:
                            try:
                                await tab.close()
                            except Exception:
                                pass
                    except Exception:
                        job.match_reason = "JD校验失败，剔除"

            await asyncio.gather(*[_jd_check_one(j) for j in jd_cands], return_exceptions=True)
            _jd_total = len(jd_cands)
            _jd_pass = sum(1 for j in jd_cands if j.jd_ai_verified)
            all_jobs = [j for j in all_jobs if not getattr(j, "need_jd_check", False) or j.jd_ai_verified]
            print(f"[搜索] JD级AI校验: 候选{_jd_total} -> 通过{_jd_pass} 剔除{_jd_total - _jd_pass}")

        # 只返回最相关的前100条（BOSS搜索结果按相关度排序，前面的最相关）
        return [JobItem(**j.to_dict()) for j in all_jobs[:100]]
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


# ============ 2. 批量投递职位 ============
@router.post("/job/apply", response_model=ResponseModel)
async def apply_jobs(
    req: ApplyJobsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量投递职位（执行时异步后台运行，返回task_id用于查询进度）"""
    if not req.jobs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要投递的职位")

    session = db.query(PlatformSession).filter(
        PlatformSession.id == req.session_id,
        PlatformSession.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if not session.is_logged_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "会话未登录，请重新扫码登录")
    if not session.cookies:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cookie不存在")

    # 名额预检：今日剩余打招呼名额（按成功打招呼数计），用完直接拒绝，避免建任务后马上失败
    from sqlalchemy import func as _sa_f
    _today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    daily_limit = int(req.daily_limit or settings.BOSS_DAILY_LIMIT)
    today_ok = db.query(_sa_f.count(ApplyRecord.id)).filter(
        ApplyRecord.user_id == user.id,
        ApplyRecord.platform == "boss",
        ApplyRecord.status == "success",
        ApplyRecord.created_at >= _today_start,
    ).scalar() or 0
    remaining = max(0, daily_limit - int(today_ok))
    if remaining <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"今日打招呼名额已用完（{int(today_ok)}/{daily_limit}），请明天再试",
        )

    # 创建/复用DB投递任务记录，用于持久化进度（进程重启后仍可查询）
    now = datetime.datetime.now()
    if req.task_id:
        task_row = db.query(ApplyTask).filter(
            ApplyTask.id == req.task_id, ApplyTask.user_id == user.id
        ).first()
        if not task_row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "投递任务不存在")
    else:
        first_job = req.jobs[0]
        task_row = ApplyTask(
            user_id=user.id,
            resume_id=req.resume_id,
            task_name=f"{first_job.job_title or '批量投递'} 等{len(req.jobs)}个职位",
            platform="boss",
            apply_mode=req.apply_mode,
            greeting_template=req.greeting_template,
            status="running",
        )
        db.add(task_row)
        db.commit()
        db.refresh(task_row)

    db_task_id = task_row.id
    task_id = str(db_task_id)
    runtime = {
        "task_id": task_id, "status": "running",
        "total": len(req.jobs), "current": 0,
        "success": 0, "failed": 0, "skipped": 0,
        "results": [],
        "error": None,
        "created_at": now.timestamp(),
    }
    RUNNING_APPLY_TASKS[task_id] = runtime

    task_row.status = "running"
    task_row.last_run_at = now
    task_row.progress = runtime
    db.commit()

    cookies = session.cookies or []
    asyncio.create_task(_run_apply_background(
        task_id=task_id,
        db_task_id=db_task_id,
        user_id=user.id,
        cookies=cookies,
        jobs_req=req,
        headless=req.headless,
    ))

    return ResponseModel.success(data={"task_id": task_id, "total": len(req.jobs)},
                                  message=f"投递任务已启动，共 {len(req.jobs)} 个职位")


async def _run_apply_background(task_id, db_task_id, user_id, cookies, jobs_req, headless=None):
    """后台运行批量投递 - 在独立线程+ProactorEventLoop中运行"""
    await asyncio.to_thread(_run_apply_sync, task_id, db_task_id, user_id, cookies, jobs_req, headless)


def _run_apply_sync(task_id, db_task_id, user_id, cookies, jobs_req, headless=None):
    """同步入口：创建独立事件循环运行投递"""
    import asyncio
    import sys
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_do_apply(task_id, db_task_id, user_id, cookies, jobs_req, headless))
    except Exception as e:
        task = RUNNING_APPLY_TASKS.get(task_id)
        if task:
            task["status"] = "failed"
            task["error"] = str(e)
    finally:
        loop.close()


def _snapshot_runtime(task: Dict) -> Dict:
    """把内存运行时状态转成可持久化的快照（存入 apply_tasks.progress）"""
    if not task:
        task = {}
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status", "running"),
        "total": task.get("total", 0),
        "current": task.get("current", 0),
        "success": task.get("success", 0),
        "failed": task.get("failed", 0),
        "skipped": task.get("skipped", 0),
        "error": task.get("error"),
        "message": task.get("message"),
        "quota": task.get("quota"),
        "created_at": task.get("created_at"),
        "results": task.get("results", []),
    }


async def _do_apply(task_id, db_task_id, user_id, cookies, jobs_req, headless=None):
    """实际的投递流程"""
    from app.core import BrowserContextManager, create_platform, Job as CoreJob
    from app.core.base import ApplyResult

    task = RUNNING_APPLY_TASKS.get(task_id)
    browser = None
    db = None
    stopped = False
    quota_exhausted = False
    try:
        from app.database import SessionLocal
        from sqlalchemy import func as _sa_func
        db = SessionLocal()

        # ===== 今日打招呼名额：动态计算剩余名额，用完为止 =====
        daily_limit = int(getattr(jobs_req, "daily_limit", None) or settings.BOSS_DAILY_LIMIT)
        today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
        today_success = db.query(_sa_func.count(ApplyRecord.id)).filter(
            ApplyRecord.user_id == user_id,
            ApplyRecord.platform == "boss",
            ApplyRecord.status == "success",
            ApplyRecord.created_at >= today_start,
        ).scalar() or 0
        today_success = int(today_success)
        remaining_quota = max(0, daily_limit - today_success)
        if remaining_quota <= 0:
            raise RuntimeError(f"今日打招呼名额已用完（{today_success}/{daily_limit}），请明天再试")
        if task:
            task["quota"] = {"daily_limit": daily_limit, "today_used": today_success, "remaining": remaining_quota}
        print(f"[投递] 今日已打招呼{today_success}/{daily_limit}，剩余{remaining_quota}个名额，本次最多处理{len(jobs_req.jobs)}个")

        # 投递必须有头模式：被Boss风控拦截时，用户可在弹出的窗口里手动完成滑块验证
        browser = BrowserContextManager(headless=False)
        await browser.start()
        pf = create_platform("boss", browser)

        await browser.page.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(1)

        # 优先使用profile里已有的登录态；只有未登录时才注入DB保存的cookies
        # （避免用旧cookies覆盖profile里更新的登录态，导致每次都要求重新扫码）
        if not await pf.is_logged_in():
            try:
                await browser.context.add_cookies(cookies)
                await browser.page.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(1.5)
            except Exception:
                pass

        # 会话健康检查：被风控/未登录时，等待用户在弹出的窗口中扫码登录或完成滑块（最多90秒）
        risk_waited = 0
        while _is_risk_controlled(browser.page) or not await pf.is_logged_in():
            if risk_waited >= 90:
                raise RuntimeError("Boss会话未就绪：请在弹出的浏览器窗口中扫码登录或完成滑块验证后再重试")
            print(f"[投递] 等待Boss登录/验证... 已等待{risk_waited}s")
            await asyncio.sleep(3)
            risk_waited += 3
            try:
                await browser.page.bring_to_front()
            except Exception:
                pass

        # 扫码登录成功后：把新cookies同步回数据库会话，避免下次投递再扫码
        try:
            storage_state = await browser.context.storage_state()
            db.query(PlatformSession).filter(
                PlatformSession.id == jobs_req.session_id,
                PlatformSession.user_id == user_id,
            ).update({
                "cookies": storage_state.get("cookies", []),
                "local_storage": [o for o in storage_state.get("origins", []) if o.get("localStorage")] or None,
                "session_storage": [o for o in storage_state.get("origins", []) if o.get("sessionStorage")] or None,
                "is_logged_in": True,
                "last_check_at": datetime.datetime.now(),
                "last_login_at": datetime.datetime.now(),
            })
            db.commit()
        except Exception as e:
            print(f"[投递] 同步cookies到数据库失败: {e}")

        total = len(jobs_req.jobs)
        consecutive_risk = 0
        for idx, j in enumerate(jobs_req.jobs, 1):
            task = RUNNING_APPLY_TASKS.get(task_id)
            if not task or task.get("status") == "stopped":
                stopped = True
                break
            task["current"] = idx

            # 单职位投递前检查风控：命中时尝试恢复；连续多次恢复失败才中断任务，单个失败不拖垮整批
            if _is_risk_controlled(browser.page):
                recovered = await _try_recover_risk(browser.page)
                if not recovered:
                    consecutive_risk += 1
                    if consecutive_risk >= 3:
                        raise RuntimeError("触发Boss安全验证：请在弹出的浏览器窗口中手动完成滑块验证后再重试")
                    fail_result = ApplyResult(
                        job_id=j.job_id, success=False, status="failed",
                        message="触发Boss安全验证，未通过验证，跳过该职位",
                    )
                    task["results"].append(fail_result.to_dict())
                    task["failed"] += 1
                    continue
                consecutive_risk = 0

            # 投递前标题方向终检（title_filter: strict=AI开发严格 / loose=宽松 / None=不校验）
            title_filter = getattr(jobs_req, "title_filter", None)
            _skip_reason = None
            if title_filter == "strict" and hasattr(pf, "_is_irrelevant_title") and pf._is_irrelevant_title(j.job_title or ""):
                # 搜索阶段已读JD确认AI内容（jd_ai_verified）的通用标题岗位放行
                if not getattr(j, "jd_ai_verified", False):
                    _skip_reason = "标题方向不符（非AI应用开发岗），跳过"
            elif title_filter == "loose" and hasattr(pf, "_is_loose_irrelevant_title") and pf._is_loose_irrelevant_title(j.job_title or ""):
                _skip_reason = "标题方向不符（含排除词或无关岗位），跳过"
            if _skip_reason:
                skip_result = ApplyResult(job_id=j.job_id, success=False, status="skipped", message=_skip_reason)
                task["results"].append(skip_result.to_dict())
                task["skipped"] += 1
                try:
                    db.add(ApplyRecord(
                        user_id=user_id, task_id=db_task_id, platform="boss",
                        job_id=j.job_id, job_title=j.job_title, job_url=j.job_url,
                        company_id=j.company_id, company_name=j.company_name,
                        company_size=j.company_size, company_industry=j.company_industry,
                        salary_min=j.salary_min, salary_max=j.salary_max,
                        city=j.city, area=j.area, experience=j.experience, education=j.education,
                        hr_name=j.hr_name, hr_title=j.hr_title, hr_active_days=j.hr_active_days,
                        is_headhunter=1 if j.is_headhunter else 0,
                        status="skipped", error_msg=_skip_reason,
                        applied_at=datetime.datetime.now(),
                    ))
                    db.commit()
                except Exception as e:
                    print(f"[ERROR] 写入投递记录失败: {e}")
                continue

            core_job = CoreJob(
                platform=j.platform, job_id=j.job_id,
                job_title=j.job_title, job_url=j.job_url,
                company_name=j.company_name or "",
                hr_name=j.hr_name or "",
            )
            try:
                result = await pf.apply_job(
                    core_job,
                    greeting_template=jobs_req.greeting_template,
                    resume_id=str(jobs_req.resume_id) if jobs_req.resume_id else None,
                    rest_policy=getattr(jobs_req, "rest_policy", None),
                )
            except Exception as e:
                result = ApplyResult(job_id=j.job_id, success=False, status="failed", message=str(e))

            task["results"].append(result.to_dict())
            if result.success:
                task["success"] += 1
                today_success += 1
                # 名额动态消耗：达到今日上限（用完为止）立即停止，不再继续投
                if today_success >= daily_limit:
                    quota_exhausted = True
                    print(f"[投递] 今日打招呼名额已用完（{daily_limit}/{daily_limit}），自动停止")
            elif result.status in ("skipped", "duplicate"):
                task["skipped"] += 1
            else:
                task["failed"] += 1

            # 持久化运行时进度
            try:
                row = db.query(ApplyTask).filter(ApplyTask.id == db_task_id).first()
                if row:
                    row.status = "running"
                    row.total_applied = task["success"] + task["failed"] + task["skipped"]
                    row.total_success = task["success"]
                    row.total_failed = task["failed"]
                    row.progress = _snapshot_runtime(task)
                    db.commit()
            except Exception as e:
                print(f"[ERROR] 更新任务进度失败: {e}")

            try:
                rec = ApplyRecord(
                    user_id=user_id,
                    task_id=db_task_id,
                    platform="boss",
                    job_id=j.job_id,
                    job_title=j.job_title,
                    job_url=j.job_url,
                    company_id=j.company_id,
                    company_name=j.company_name,
                    company_size=j.company_size,
                    company_industry=j.company_industry,
                    salary_min=j.salary_min, salary_max=j.salary_max,
                    city=j.city, area=j.area,
                    experience=j.experience, education=j.education,
                    hr_name=j.hr_name, hr_title=j.hr_title,
                    hr_active_days=j.hr_active_days,
                    is_headhunter=1 if j.is_headhunter else 0,
                    status=result.status,
                    error_msg=result.message,
                    greeting_sent=result.greeting_sent,
                    applied_at=datetime.datetime.now(),
                )
                db.add(rec)
                db.commit()
            except Exception as e:
                print(f"[ERROR] 写入投递记录失败: {e}")

            if quota_exhausted:
                break

            if idx < total:
                delay_min = settings.BOSS_APPLY_DELAY_MIN
                delay_max = settings.BOSS_APPLY_DELAY_MAX
                await asyncio.sleep(__import__("random").uniform(delay_min, delay_max))

        task = RUNNING_APPLY_TASKS.get(task_id)
        if task:
            task["status"] = "stopped" if stopped else "done"
            if quota_exhausted:
                task["message"] = f"今日打招呼名额已用完（{daily_limit}/{daily_limit}），自动停止"
            task["quota"] = {"daily_limit": daily_limit, "today_used": today_success,
                             "remaining": max(0, daily_limit - today_success)}
        try:
            row = db.query(ApplyTask).filter(ApplyTask.id == db_task_id).first()
            if row:
                row.status = "paused" if stopped else "completed"
                row.last_run_at = datetime.datetime.now()
                row.total_applied = (task or {}).get("success", 0) + (task or {}).get("failed", 0) + (task or {}).get("skipped", 0)
                row.total_success = (task or {}).get("success", 0)
                row.total_failed = (task or {}).get("failed", 0)
                row.progress = _snapshot_runtime(task)
                db.commit()
        except Exception as e:
            print(f"[ERROR] 完成任务写入失败: {e}")
    except Exception as e:
        task = RUNNING_APPLY_TASKS.get(task_id)
        if task:
            task["status"] = "failed"
            task["error"] = str(e)
        if db is not None:
            try:
                row = db.query(ApplyTask).filter(ApplyTask.id == db_task_id).first()
                if row:
                    row.status = "failed"
                    row.progress = _snapshot_runtime(task)
                    db.commit()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


@router.get("/job/apply/status/{task_id}")
def get_apply_status(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """查询后台投递进度（内存优先，进程重启后回退DB持久化进度）"""
    t = RUNNING_APPLY_TASKS.get(str(task_id))
    if t:
        return ResponseModel.success(data=t)
    try:
        row = db.query(ApplyTask).filter(
            ApplyTask.id == int(task_id), ApplyTask.user_id == user.id
        ).first()
    except (TypeError, ValueError):
        row = None
    if row and row.progress:
        data = dict(row.progress)
        data.setdefault("task_id", str(row.id))
        return ResponseModel.success(data=data)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或已完成")


@router.post("/job/apply/stop/{task_id}")
def stop_apply_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = RUNNING_APPLY_TASKS.get(str(task_id))
    if t:
        t["status"] = "stopped"
    try:
        row = db.query(ApplyTask).filter(
            ApplyTask.id == int(task_id), ApplyTask.user_id == user.id
        ).first()
        if row and row.status == "running":
            row.status = "paused"
            if row.progress:
                row.progress["status"] = "stopped"
            db.commit()
    except (TypeError, ValueError):
        pass
    return ResponseModel.success(message="已发送停止信号")


# ============ 3. 投递任务 CRUD ============
@router.get("/apply/tasks", response_model=ResponseModel[PageResult[ApplyTaskInfo]])
def list_apply_tasks(user=Depends(get_current_user), db=Depends(get_db), pp=Depends(get_page_params)):
    page, size = pp
    q = db.query(ApplyTask).filter(ApplyTask.user_id == user.id).order_by(ApplyTask.updated_at.desc())
    items, total, _ = paginate_query(q, db, page, size)
    return ResponseModel.success(data=make_page_result(items, total, page, size))


@router.post("/apply/task", response_model=ResponseModel[ApplyTaskInfo])
def create_apply_task(data: ApplyTaskCreate, user=Depends(get_current_user), db=Depends(get_db)):
    data.user_id = user.id
    obj = ApplyTask(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return ResponseModel.success(data=obj)


@router.put("/apply/task/{tid}", response_model=ResponseModel[ApplyTaskInfo])
def update_apply_task(tid: int, data: ApplyTaskUpdate, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(ApplyTask).filter(ApplyTask.id == tid, ApplyTask.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return ResponseModel.success(data=obj)


@router.post("/apply/task/{tid}/delete", response_model=ResponseModel)
def delete_apply_task(tid: int, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(ApplyTask).filter(ApplyTask.id == tid, ApplyTask.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    db.delete(obj); db.commit()
    return ResponseModel.success(message="已删除")


# ============ 4. 投递记录 查询/更新 ============
@router.get("/apply/records", response_model=ResponseModel[PageResult[ApplyRecordInfo]])
def list_apply_records(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    keyword: Optional[str] = None,
    follow_status: Optional[str] = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
    pp=Depends(get_page_params),
):
    page, size = pp
    q = db.query(ApplyRecord).filter(ApplyRecord.user_id == user.id)
    if status:
        q = q.filter(ApplyRecord.status == status)
    if follow_status:
        # 跟进状态筛选：none=无回复 / replied=HR已回复 / interviewed=已约面 / rejected=已拒 / offer=已拿Offer
        q = q.filter(ApplyRecord.follow_up_status == follow_status)
    if platform:
        q = q.filter(ApplyRecord.platform == platform)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            (ApplyRecord.company_name.like(kw)) | (ApplyRecord.job_title.like(kw))
        )
    q = q.order_by(ApplyRecord.applied_at.desc().nullslast(), ApplyRecord.created_at.desc())
    items, total, _ = paginate_query(q, db, page, size)
    return ResponseModel.success(data=make_page_result(items, total, page, size))


@router.get("/apply/stats")
def get_apply_stats(user=Depends(get_current_user), db=Depends(get_db)):
    """投递统计（首页看板用）"""
    from sqlalchemy import func
    total = db.query(func.count(ApplyRecord.id)).filter(ApplyRecord.user_id == user.id).scalar() or 0
    today = datetime.date.today()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    today_count = db.query(func.count(ApplyRecord.id)).filter(
        ApplyRecord.user_id == user.id, ApplyRecord.created_at >= today_start
    ).scalar() or 0
    replied = db.query(func.count(ApplyRecord.id)).filter(
        ApplyRecord.user_id == user.id, ApplyRecord.follow_up_status.in_(["replied", "interviewed", "offer"])
    ).scalar() or 0
    interviewed = db.query(func.count(ApplyRecord.id)).filter(
        ApplyRecord.user_id == user.id, ApplyRecord.follow_up_status.in_(["interviewed", "offer"])
    ).scalar() or 0
    today_success = db.query(func.count(ApplyRecord.id)).filter(
        ApplyRecord.user_id == user.id,
        ApplyRecord.platform == "boss",
        ApplyRecord.status == "success",
        ApplyRecord.created_at >= today_start,
    ).scalar() or 0
    daily_limit = settings.BOSS_DAILY_LIMIT
    return ResponseModel.success(data={
        "totalApplied": total, "todayApplied": today_count,
        "todaySuccess": int(today_success),
        "dailyLimit": int(daily_limit),
        "remaining": max(0, int(daily_limit) - int(today_success)),
        "replied": replied, "interviewed": interviewed,
    })


@router.get("/job/keywords")
def get_job_keywords():
    """Boss搜索关键词词表同步：前端建议词与后端过滤词表单一来源"""
    from app.core.boss.scraper import BossScraperMixin
    ai_words = list(BossScraperMixin.TITLE_AI_WORDS)
    job_words = list(BossScraperMixin.TITLE_JOB_WORDS)
    exclude_words = list(BossScraperMixin.TITLE_EXCLUDE_WORDS)

    def _gen(ai: str, job: str) -> str:
        return f"{ai}{job}"

    suggestions = []
    for ai in ["AI", "大模型", "LLM", "RAG", "Agent", "AIGC", "NLP", "多模态", "机器学习", "深度学习", "人工智能"]:
        for job in ["应用开发", "应用开发工程师", "应用工程师", "应用研发", "开发工程师", "算法工程师", "工程师"]:
            s = _gen(ai, job)
            if s not in suggestions:
                suggestions.append(s)
    # 补充常用写法
    extra = [
        "AI 应用工程师", "AI 应用开发", "AI 应用开发工程师", "AI 应用研发",
        "AI Agent 开发", "AI Agent 工程师", "Agent 开发工程师", "AI 智能体开发",
        "大模型应用开发", "大模型应用工程师", "大模型应用开发工程师",
        "RAG 开发", "RAG 工程师", "RAG 应用开发", "检索增强开发",
        "AI 后端开发", "AI 后端工程师", "AI 全栈开发", "AIGC 开发工程师",
        "NLP 工程师", "NLP 开发", "机器学习工程师", "深度学习工程师", "多模态算法工程师",
        # 2026-08-10 三城市市场标题词频学习新增（全栈12/43、Python高频、智能体/大模型）
        "全栈开发", "全栈开发工程师", "AI 全栈工程师", "Python 开发", "Python 开发工程师",
        "Python 工程师", "智能体开发", "智能体开发工程师", "Python 大模型", "Python 大模型开发",
        # 2026-08-11 第22-24轮搜索验证新增（经验≤1年方向均有效）
        "AI 应用", "智能应用", "智能应用开发", "AI 研发", "人工智能工程师",
        "AIGC 开发", "AI 编程", "AI 编程开发",
    ]
    for s in extra:
        if s not in suggestions:
            suggestions.append(s)
    return ResponseModel.success(data={
        "suggestions": suggestions,
        "ai_words": ai_words,
        "job_words": job_words,
        "exclude_words": exclude_words,
    })


@router.put("/apply/record/{rid}/follow")
def update_follow(rid: int, data: dict, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(ApplyRecord).filter(ApplyRecord.id == rid, ApplyRecord.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "记录不存在")
    if "follow_up_status" in data:
        obj.follow_up_status = data["follow_up_status"]
    if "follow_up_remark" in data:
        obj.follow_up_remark = data["follow_up_remark"]
    db.commit()
    return ResponseModel.success(message="已更新")


# ============ 9. 自动跟进 ============
@router.post("/apply/followup/run", response_model=ResponseModel)
async def run_followup(
    req: FollowUpRunRequest,
    user: User = Depends(get_current_user),
):
    """
    执行一次自动跟进扫描：
    打开Boss聊天页 -> 抓取会话 -> 匹配投递记录 -> 更新跟进状态
    默认有头模式（可在弹出的浏览器窗口处理滑块/扫码）
    """
    from app.services.followup_service import run_followup_scan_sync
    try:
        result = await asyncio.to_thread(
            run_followup_scan_sync, user.id, req.session_id, req.headless, req.force
        )
        msg = f"跟进扫描完成：匹配{result.get('matched', 0)}条，更新{result.get('updated', 0)}条"
        if result.get("error"):
            msg = f"跟进扫描未完成：{result['error']}"
        return ResponseModel.success(data=result, message=msg)
    except Exception as e:
        return ResponseModel.error(message=f"跟进扫描失败: {e}")


@router.get("/apply/followup/status")
def get_followup_status(user: User = Depends(get_current_user)):
    """最近一次自动跟进扫描的结果"""
    from app.services.followup_service import get_last_scan
    return ResponseModel.success(data=get_last_scan())
