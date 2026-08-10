"""
Boss直聘 - 职位搜索与抓取模块
参考 JobClaw scraper/boss.py + boss_push 油猴脚本的筛选逻辑
实现：搜索条件组装URL -> 抓取列表页 -> 解析成统一Job对象 -> 应用黑白名单过滤
"""
import re
import json
import time
import asyncio
import unicodedata
from typing import List, Optional, Dict
from urllib.parse import urlencode, quote

# joblist API 直取全局节奏控制：避免短时间大量请求触发Boss「您的环境存在异常」风控(code:37)
_JOBLIST_API_MIN_INTERVAL = 2.5
_JOBLIST_API_LAST_CALL = 0.0
_JOBLIST_CHALLENGE_UNTIL = 0.0  # 触发code:37后全局冷却截止时间，避免连环风控
_JOBLIST_API_FAST_ENABLED = True  # 置False可临时关闭API直取，走页面加载路径

from app.core.base import BasePlatform, Job


class BossScraperMixin(BasePlatform):
    """Boss直聘职位抓取混入类"""

    search_base_url = "https://www.zhipin.com/web/geek/job"

    # Boss直聘城市编码（常用）
    CITY_CODES = {
        "深圳": "101280600", "广州": "101280100", "北京": "101010100",
        "上海": "101020100", "杭州": "101210100", "成都": "101270100",
        "武汉": "101200100", "西安": "101110100", "南京": "101190100",
        "重庆": "101040100", "苏州": "101190400", "长沙": "101250100",
    }

    # 经验编码
    EXP_CODES = {0: "", 1: "102", 2: "103", 3: "104", 4: "105", 5: "106", 6: "107"}
    # 学历编码
    EDU_CODES = {0: "", 1: "202", 2: "203", 3: "204", 4: "205"}
    # 公司规模编码（BOSS搜索页 scale 参数，实测 301=0-20人 / 302=20-99人）
    SCALE_CODES = {1: "301", 2: "302", 3: "303", 4: "304", 5: "305", 6: "306"}
    # 薪资编码
    SALARY_CODES = {
        (None, None): "",
        (0, 3): "401", (3, 5): "402", (5, 10): "403",
        (10, 15): "404", (15, 20): "405", (20, 30): "406",
        (30, 50): "407", (50, 999): "408",
    }

    # 标题相关度白名单（严格模式=AI开发类关键词）：
    # 含「AI相关词」或「开发/工程岗位词」之一即算相关；两个词都没有的（如销售/运营/
    # 产品经理/标注/工艺工程师/普工等）剔除。放宽AND为OR是因为Boss搜索返回的合法
    # AI开发岗标题未必带AI字样（如 Python开发工程师 / 算法工程师 / 后端工程师）。
    TITLE_AI_WORDS = [
        "ai", "人工智能", "大模型", "llm", "agent", "智能体", "gpt", "aigc",
        "深度学习", "机器学习", "nlp", "多模态", "计算机视觉", "数据智能",
        "rag", "检索增强", "大语言模型", "langchain", "prompt", "embedding",
        "知识库", "向量", "微调", "智能应用", "agentic",
    "vibe", "vibe coding", "ai coding", "ai编程", "编程助手",
    "智能编程", "代码生成", "copilot", "cursor",
    ]
    TITLE_JOB_WORDS = [
        "开发", "工程师", "研发", "算法", "应用", "架构", "程序",
        "后端", "前端", "全栈", "运维", "数据分析", "数据科学", "数据挖掘",
        "软件", "系统", "平台", "客户端", "服务端", "嵌入式", "数据",
    ]

    # 标题排除词：即使命中AI/开发词，只要含这些非开发岗特征词也一律剔除
    # （标注/评测/产品经理/运营/销售/客服/顾问/专员/测试/工艺/设备/质量等都不是AI应用开发岗）
    TITLE_EXCLUDE_WORDS = [
        "标注", "评测", "产品经理", "产品师", "运营", "销售", "客服", "顾问",
        "专员", "主播", "助教", "文员", "人事", "财务", "行政", "设计师",
        "助理", "测试", "实习", "产品负责人", "独立开发者", "讲师", "部署",
        "实施", "驻场", "现场", "交付", "猎头", "管培生", "电销", "电话销售",
        "咨询", "培训", "教务", "招生", "推广", "客户代表", "影视",
        "分析师", "售前", "客户成功", "审核", "质检", "商务", "训练师",
        "用户增长", "文案", "媒介", "售后", "技术支持", "录入", "管理员",
        "硬件", "机械", "电气", "工艺", "设备", "质量", "结构", "土木",
        "材料", "化工", "生物", "医药", "护理", "会计", "出纳", "文秘",
        "测评", "储备",
    # 2026-08-09 历史投递复盘补充：硬件/芯片/光学/嵌入式/新能源/汽车电子等非AI应用开发岗
    "硬件", "光学", "射频", "芯片", "嵌入式", "电池", "光伏", "热管理",
    "电推", "体系", "fpga", "光模块", "硅光", "智能驾驶", "数字ic",
    "ic设计", "驱动开发", "电镜",
    ]

    # 算法/研究向岗位词：算法/深度学习/机器学习/多模态/图像/框架等属于模型研发，
    # 不是AI应用开发岗。标题命中这些词时一律剔除，除非标题明确带「应用」
    # （如 多模态应用开发工程师 / NLP应用工程师）才放行。
    ALGO_RESEARCH_WORDS = [
        "算法", "深度学习", "机器学习", "多模态", "计算机视觉", "图像",
        "3dgs", "nerf", "nlp", "自然语言", "感知", "框架", "推理",
        "训练", "蒸馏", "调优", "量化", "研究员", "研究", "博士", "论文",
        "模型优化", "加速",
    ]

    # JD级AI校验关键词：Boss搜索按JD内容匹配，标题常为通用开发岗（如"研发工程师"）。
    # 这类岗位需读JD确认是否AI应用开发方向；命中以下任一关键词即视为AI相关。
    JD_AI_PATTERNS = [
        "大模型", "人工智能", "智能体", "大语言模型", "深度学习", "机器学习",
        "多模态", "计算机视觉", "自然语言处理", "知识库", "微调", "检索增强",
        "向量数据库", "智能应用", "提示词", "智能问答", "智能助理", "智能助手",
        "AIGC", "RAG", "LangChain", "Prompt", "MCP", "Agent", "GPT", "LLM",
        "ai", "agentic", "embedding", "transformer", "nlp",
    "vibe coding", "ai coding", "copilot", "cursor", "智能编程", "代码生成",
    ]


    # 关键词岗位类型判断：仅当关键词属于开发/工程类岗位时启用「AI+开发词」严格标题过滤；
    # 搜 销售/AI产品经理/运营 等非开发岗时跳过该过滤，保留Boss按关键词返回的职位（多岗位场景）
    # 宽松模式相关性词：非开发类关键词（销售/AI产品经理等）跳过严格标题过滤后，
    # 仍要求标题至少含一个岗位相关词，避免"校招生岗位/保底薪资"等无意义标题混入
    LOOSE_RELEVANT_WORDS = [
        "ai", "agent", "智能体", "大模型", "人工智能", "llm", "应用", "开发",
        "工程师", "算法", "研发", "工程", "数据", "训练",
        "销售", "产品", "经理", "客户", "顾问", "运营", "市场", "商务",
        "讲师", "课程", "老师", "主播", "客服", "专员", "助理", "管培",
        "BD", "渠道", "推广", "增长", "用户", "内容", "策划", "跟单",
        "采购", "外贸", "招商", "招生", "教务", "文员", "人事", "财务",
        "行政", "前台", "营业", "店长", "导购", "店员", "服务员", "骑手",
        "配送", "司机", "保洁", "保安", "厨师", "仓管", "普工", "操作工",
        "带货", "电商",
    ]

    DEV_ROLE_KEYWORDS = [
        "开发", "工程师", "研发", "算法", "程序", "后端", "前端",
        "全栈", "运维", "架构", "测试", "数据科学", "数据挖掘",
    ]

    # 非开发岗关键词特征：关键词含这些词时（如 AI产品经理/销售运营），即使含AI词也走宽松过滤
    NON_DEV_ROLE_WORDS = [
        "销售", "产品经理", "产品师", "运营", "客服", "顾问", "市场",
        "助理", "专员", "管培", "讲师", "培训", "教务", "招生", "推广",
        "客户代表", "主播", "设计",
    ]

    @staticmethod
    def _is_dev_role_keywords(keywords) -> bool:
        """关键词是否属于AI开发/工程类岗位（决定是否启用严格标题过滤）
        规则：1) 含开发岗位词（开发/工程师/算法等）→ 严格
              2) 含AI相关词（ai/大模型/agent等）且不含非开发岗词 → 严格（AI Agent/大模型应用等）
              3) 其余（销售/AI产品经理/运营等）→ 宽松
        """
        if isinstance(keywords, (list, tuple)):
            joined = " ".join(str(k) for k in keywords)
        else:
            joined = str(keywords or "")
        joined = joined.lower()
        if any(k in joined for k in BossScraperMixin.DEV_ROLE_KEYWORDS):
            return True
        if any(k in joined for k in BossScraperMixin.TITLE_AI_WORDS):
            return not any(k in joined for k in BossScraperMixin.NON_DEV_ROLE_WORDS)
        return False

    # ---------- 公开接口 ----------
    async def search_jobs(
        self,
        keywords: str,
        city_code: Optional[str] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        experience=0,
        education=0,
        page: int = 1,
        page_size: int = 30,
        company_scales: str = "",  # 逗号分隔的公司规模编码
        industries: str = "",     # 逗号分隔的行业编码
        skip_inactive_days: Optional[int] = None,
        skip_headhunter: bool = True,
        skip_internship: bool = True,
        rest_policy: Optional[list] = None,  # 休息制度筛选：双休/大小周/单休（可多选）
        filter_rules: Optional[List[Dict]] = None,  # 黑白名单规则列表
        already_applied_ids: Optional[set] = None,  # 已投递的job_id集合
        applied_company_ids: Optional[set] = None,  # 已投递过的公司ID集合（该公司下职位全部剔除）
        applied_company_names: Optional[set] = None,  # 已投递过的公司名称集合（历史记录兜底）
        page_obj=None,  # 指定搜索用的标签页（支持多关键词并行搜索）；默认用self.page
        jd_ai_check: bool = False,  # 标题通用的开发岗（无AI词）先读JD确认AI内容再保留
        **kwargs
    ) -> List[Job]:
        """
        搜索并解析职位列表
        """
        skip_inactive_days = skip_inactive_days or self.skip_inactive_days

        # 1. 构造搜索URL
        search_url = self._build_search_url(
            query=keywords, city_code=city_code,
            salary_min=salary_min, salary_max=salary_max,
            experience=experience, education=education,
            company_scales=company_scales,
            page=page
        )
        self.log(f"访问搜索页: {search_url}")

        page = page_obj or self.page

        # 1.8 API直取快路径：直调joblist接口（约0.5s/页），成功则跳过页面加载/滚动直达过滤；失败自动回退页面加载
        jobs = []
        if _JOBLIST_API_FAST_ENABLED:
            jobs = await self._search_jobs_fast(
                page_obj=page, query=keywords, city=city_code,
                experience=experience, education=education,
                company_scales=company_scales,
                salary_min=salary_min, salary_max=salary_max,
                page_size=page_size, target_count=90,
            )
        if jobs:
            self.log(f"joblist API直取成功: {len(jobs)} 个职位，跳过页面加载")

        # 1.5 拦截页面自身的 joblist 接口（油猴思路）：数据干净（明文薪资），规避DOM改版和字体混淆
        # 每个page独立注册监听器与捕获列表，支持多关键词并行搜索
        if not hasattr(self, "_joblist_capture_lists"):
            self._joblist_capture_lists = {}
        if page not in self._joblist_capture_lists:
            self._joblist_capture_lists[page] = []

            async def _capture_joblist(resp, _page=page):
                try:
                    if "joblist.json" not in resp.url:
                        return
                    data = await resp.json()
                    job_list = ((data or {}).get("zpData") or {}).get("jobList") or []
                    if job_list:
                        self._joblist_capture_lists[_page].append(job_list)
                except Exception:
                    pass

            page.on("response", _capture_joblist)
        if not jobs:
            captured_api = self._joblist_capture_lists[page]

            # 2. 访问列表页
            _t_goto = time.monotonic()
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                self.log(f"搜索页加载超时，尝试继续: {e}")
            print(f"[慢路径] goto耗时{time.monotonic()-_t_goto:.1f}s, URL={page.url[:80]}")
        
            await self._human_stay(0.3, 0.5, page_obj=page)

            # 检测是否被反爬重定向
            cur_url = page.url
            if "about:blank" in cur_url or "login" in cur_url.lower():
                self.log(f"页面被重定向到 {cur_url}，可能需要登录或触发反爬")
                # 尝试重新访问
                await self._human_stay(1, 2, page_obj=page)
                try:
                    await page.goto(search_url, wait_until="networkidle", timeout=60000)
                    await self._human_stay(0.3, 0.5, page_obj=page)
                except Exception:
                    pass
        
            # 检测验证码
            try:
                has_captcha = await page.evaluate("""() => {
                    const text = document.body.innerText || '';
                    return text.includes('安全验证') || text.includes('滑动验证') || 
                           text.includes('请完成验证') || !!document.querySelector('[class*="captcha"], [class*="verify"]');
                }""")
                if has_captcha:
                    self.log("检测到验证码！请手动完成验证后继续...")
                    # 等待用户手动处理验证码（最多4秒，无头模式下上层会快速报风控错误）
                    for _ in range(2):
                        await self._human_stay(2, 2, page_obj=page)
                        has_captcha = await page.evaluate("""() => {
                            const text = document.body.innerText || '';
                            return text.includes('安全验证') || text.includes('滑动验证') || 
                                   text.includes('请完成验证');
                        }""")
                        if not has_captcha:
                            break
            except Exception:
                pass

            # 2.5 等接口首次数据返回（安全验证页会自动跳回搜索页）；joblist接口通常1-2次轮询即命中
            for _ in range(8):
                if captured_api:
                    break
                await self._human_stay(0.2, 0.4, page_obj=page)

            # 3. 滚动加载更多（触发接口分页加载）
            # 滚动加载量随 page_size 而定：小批量搜索不浪费时间关等大数量加载
            scroll_cap = max(30, min(60, int(page_size or 30) * 2))
            _t_scroll = time.monotonic()
            await self._scroll_to_load_all(max_items=scroll_cap, page_obj=page)
            print(f"[慢路径] 滚动耗时{time.monotonic()-_t_scroll:.1f}s, 捕获列表数={len(captured_api)}")

            # 4. 解析：优先用接口数据（明文薪资，无字体混淆），失败回退DOM
            _t_parse = time.monotonic()
            jobs = []
            if captured_api:
                jobs = self._parse_joblist_api(captured_api)
                self.log(f"接口获取到 {len(jobs)} 个职位")
            if not jobs:
                jobs = await self._parse_job_list(page_obj=page)
                print(f"[慢路径] 解析耗时{time.monotonic()-_t_parse:.1f}s -> {len(jobs)} 个职位")
                self.log(f"DOM解析到 {len(jobs)} 个职位")

            # 4.5 首轮为空时重试一次（多城市切换/风控页偶发导致 joblist 接口未返回）
            if not jobs:
                self.log("首轮未抓到职位，重试一次搜索页加载")
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    await self._human_stay(0.3, 0.5, page_obj=page)
                except Exception as e:
                    self.log(f"重试加载搜索页失败: {e}")
                for _ in range(8):
                    if captured_api:
                        break
                    await self._human_stay(0.2, 0.4, page_obj=page)
                await self._scroll_to_load_all(max_items=100, page_obj=page)
                if captured_api:
                    jobs = self._parse_joblist_api(captured_api)
                    self.log(f"重试后接口获取到 {len(jobs)} 个职位")
                if not jobs:
                    jobs = await self._parse_job_list(page_obj=page)
                    self.log(f"重试后DOM解析到 {len(jobs)} 个职位")

        # 5. 本地过滤
        result = []
        jd_candidates = []  # 标题通用（无AI词）的开发岗，待上层读JD确认AI内容
        whitelist_count = 0
        blacklist_count = 0
        inactive_count = 0
        headhunter_count = 0
        internship_count = 0
        duplicate_count = 0
        irrelevant_count = 0
        applied_company_count = 0
        rest_policy_count = 0
        exp_count = 0
        scale_count = 0
        salary_count = 0

        # 5.9/5.10 默认严格过滤开关：仅当用户【未显式指定】经验/公司规模时套用默认偏好
        # （经验≤1-3年、公司≥100人）；用户在前端手动选择了经验/规模时，完全以用户选择为准
        def _is_filter_unset(v):
            if v is None:
                return True
            if isinstance(v, str):
                return not v.strip() or v.strip() == "0"
            if isinstance(v, (list, tuple)):
                return not any(str(x).strip() and str(x).strip() != "0" for x in v)
            return v == 0

        user_exp_unset = _is_filter_unset(experience)
        user_scale_unset = _is_filter_unset(company_scales)

        for job in jobs:
            # 5.1 已投递去重：今日已投过的职位不再出现在结果（用户要求已投职位/公司不再展示）
            if already_applied_ids and job.job_id in already_applied_ids:
                job.is_applied = True
                job.match_reason = "已投递过，跳过"
                duplicate_count += 1
                continue

            # 5.2 实习过滤（含元/天、日结等临时岗，下沉到搜索阶段过滤）
            if skip_internship and (job.is_internship or self._is_daily_rate_salary(job.salary_text)):
                job.match_reason = "黑名单：实习/日结临时岗"
                internship_count += 1
                continue

            # 5.3 猎头过滤
            if skip_headhunter and job.is_headhunter:
                job.match_reason = "黑名单：猎头岗位"
                headhunter_count += 1
                continue

            # 5.4 HR不活跃过滤
            if skip_inactive_days > 0 and job.hr_active_days is not None and job.hr_active_days > skip_inactive_days:
                job.match_reason = f"HR {job.hr_active_days}天未活跃，跳过"
                inactive_count += 1
                continue

            # 5.5 黑白名单规则
            rule_res = self._apply_filter_rules(job, filter_rules or [])
            if rule_res == "blacklist":
                blacklist_count += 1
                continue
            if rule_res == "whitelist":
                whitelist_count += 1

            # 5.6 标题相关度过滤：开发/工程类关键词启用严格过滤（AI+开发词）；
            #     其他关键词启用宽松过滤（排除词 + 至少含一个岗位相关词）
            if self._is_dev_role_keywords(keywords):
                if self._is_irrelevant_title(job.job_title):
                    # Boss按JD匹配搜索词，标题常为通用开发岗（如"研发工程师"）。
                    # 启用JD校验时这类岗位不直接剔除，标记后读JD确认AI内容
                    if jd_ai_check and self._is_generic_dev_title(job.job_title) and len(jd_candidates) < 8:
                        job.match_reason = "标题通用，待JD校验"
                        job.need_jd_check = True
                        jd_candidates.append(job)
                        continue
                    irrelevant_count += 1
                    continue
            elif self._is_loose_irrelevant_title(job.job_title):
                irrelevant_count += 1
                continue

            # 5.7 已投递公司过滤：该公司下所有职位不再推荐，避免重复投同一家公司
            if (applied_company_ids and job.company_id and job.company_id in applied_company_ids) or \
                    (applied_company_names and job.company_name and job.company_name in applied_company_names):
                applied_company_count += 1
                continue

            # 5.8 休息制度预过滤：明确已知的休息制度不满足要求时直接剔除；
            #     未知（空）的职位保留，交给上层补详情页信息后再严格过滤
            rest_sel = rest_policy or []
            if isinstance(rest_sel, str):
                rest_sel = [x.strip() for x in rest_sel.split(",") if x.strip()]
            if rest_sel and job.rest_policy and job.rest_policy not in rest_sel:
                job.match_reason = "休息制度不符，跳过"
                rest_policy_count += 1
                continue

            # 5.9 经验要求默认过滤：仅在用户未指定经验时生效（只要3年以内的岗位：
            #     经验不限/在校应届/1年以内/1-3年）；用户手动选了经验则以用户选择为准
            if user_exp_unset and job.experience and re.match(
                    r"^(3-5年|5-10年|10年以上|3年以上|5年以上)", job.experience):
                job.match_reason = f"经验要求过高（{job.experience}），跳过"
                exp_count += 1
                continue

            # 5.10 公司规模默认过滤：仅在用户未指定规模时生效（只要100人及以上公司，
            #      排除0-20人/20-99人等小公司）；用户手动选了规模则以用户选择为准
            if user_scale_unset and job.company_size and re.match(
                    r"^(0-20人|20-99人|少于|1-49人|50-99人)", job.company_size):
                job.match_reason = f"公司规模过小（{job.company_size}），跳过"
                scale_count += 1
                continue

            # 5.11 薪资下限过滤：用户指定了薪资下限时，剔除明显低于下限的职位（Boss区间匹配会带出低薪岗）
            if salary_min and job.salary_min is not None and int(job.salary_min) < int(salary_min):
                job.match_reason = f"薪资低于要求（{job.salary_min}K < {salary_min}K），跳过"
                salary_count += 1
                continue
            result.append(job)

        if jd_candidates:
            result.extend(jd_candidates)
        _summary = (
            f"过滤完成: 候选{len(result)} | "
            f"白名单命中{whitelist_count} | 黑名单排除{blacklist_count} | "
            f"猎头{headhunter_count} | 实习{internship_count} | "
            f"HR不活跃{inactive_count} | 重复{duplicate_count} | "
            f"标题不相关{irrelevant_count} | 已投公司{applied_company_count} | "
            f"休息制度不符{rest_policy_count} | 经验过高{exp_count} | 规模过小{scale_count} | 薪资过低{salary_count}"
        )
        self.log(_summary)
        print(f"[过滤] {_summary}")
        return result

    async def get_job_detail(self, job: Job) -> Job:
        """抓取职位详情页（含完整JD）"""
        try:
            await self.page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await self._human_stay(1, 2)
            # 提取JD
            desc_el = await self.page.query_selector(
                ".job-sec-text, .job-detail-section .text, .detail-content"
            )
            if desc_el:
                job.job_desc = (await desc_el.inner_text()).strip()
            # 重新补全HR/公司信息
            await self._enrich_job_from_detail(job)
        except Exception as e:
            self.log(f"获取详情失败 {job.job_id}: {e}")
        return job

    async def enrich_rest_policy(self, job: Job, page_obj=None, company_fallback: bool = False) -> str:
        """打开职位详情页识别休息制度（双休/大小周/单休），识别不到返回空串。
        Boss列表接口不返回休息信息；JD/详情页未识别且 company_fallback=True 时，
        再访问公司主页的「工作时间及福利」区块（公司级福利）兜底参考。"""
        page = page_obj or self.page
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await self._human_stay(0.15, 0.3, page_obj=page)
            text = await page.evaluate("() => document.body.innerText") or ""
            # 优先从职位描述(JD)区域提取文本：JD里更可能写明"周末双休/做五休二"等作息信息
            jd = ""
            for sel in (".job-sec-text", ".job-detail-section .text", ".detail-content", ".job-detail-section"):
                try:
                    el = await page.query_selector(sel)
                    if el:
                        jd = (await el.inner_text()) or ""
                        if jd.strip():
                            break
                except Exception:
                    continue
            res = self._detect_rest_policy([jd, text]) if jd.strip() else self._detect_rest_policy([text])
            if res:
                return res
            # 详情页未识别 → 公司主页「工作时间及福利」区块兜底（公司级作息）
            if company_fallback and job.company_id:
                try:
                    await page.goto(f"{self.base_url}/gongsi/{job.company_id}.html", wait_until="domcontentloaded", timeout=30000)
                    await self._human_stay(0.15, 0.3, page_obj=page)
                    for _ in range(4):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(0.3)
                    ctext = await page.evaluate("() => document.body.innerText") or ""
                    cres = self._detect_rest_policy([ctext])
                    if cres:
                        return cres
                except Exception as e:
                    self.log(f"补充公司页休息制度失败 {job.job_id}: {e}")
            return ""
        except Exception as e:
            self.log(f"补充休息制度失败 {job.job_id}: {e}")
            return ""

    # ---------- 内部方法 ----------
    def _build_search_url(self, **kw) -> str:
        """构造Boss直聘搜索URL（支持经验/学历多选，逗号拼接）"""
        params = {}
        if kw.get("query"):
            params["query"] = kw["query"]
        city = kw.get("city_code") or "100010000"  # 全国
        if isinstance(city, (list, tuple, set)):  # 防御：多城市时取第一个（API层已按城市拆分逐个搜索）
            city = str(city[0]) if city else "100010000"
        # 经验/学历多选：前端值(1-6/1-4) -> Boss编码，逗号拼接
        exp_val = kw.get("experience") or 0
        edu_val = kw.get("education") or 0
        exp_list = exp_val if isinstance(exp_val, (list, tuple, set)) else ([exp_val] if exp_val else [])
        edu_list = edu_val if isinstance(edu_val, (list, tuple, set)) else ([edu_val] if edu_val else [])
        exp_codes = [self.EXP_CODES[int(x)] for x in exp_list if int(x) in self.EXP_CODES]
        edu_codes = [self.EDU_CODES[int(x)] for x in edu_list if int(x) in self.EDU_CODES]
        if exp_codes:
            params["experience"] = ",".join(exp_codes)
        if edu_codes:
            params["degree"] = ",".join(edu_codes)
        # 公司规模多选：接受前端值(1-6)或Boss原始编码(301-306)
        scale_val = kw.get("company_scales") or ""
        scale_list = scale_val if isinstance(scale_val, (list, tuple, set)) else ([scale_val] if scale_val else [])
        scale_codes = []
        for x in scale_list:
            sx = str(x).strip()
            if not sx:
                continue
            if sx in self.SCALE_CODES.values():
                scale_codes.append(sx)
            elif int(x) in self.SCALE_CODES:
                scale_codes.append(self.SCALE_CODES[int(x)])
        if scale_codes:
            params["scale"] = ",".join(scale_codes)
        # 薪资范围：BOSS的salary参数只能选单个档位，把用户区间映射到最贴近的薪资档
        salary_min = kw.get("salary_min")
        salary_max = kw.get("salary_max")
        if salary_min is not None or salary_max is not None:
            salary_code = self._pick_salary_code(salary_min, salary_max)
            if salary_code:
                params["salary"] = salary_code
        url = f"{self.search_base_url}?city={city}"
        if params:
            url += "&" + urlencode(params)
        if kw.get("page", 1) > 1:
            url += f"&page={kw['page']}"
        return url

    def _pick_salary_code(self, salary_min, salary_max) -> str:
        """把用户薪资区间映射到BOSS单个薪资档（SALARY_CODES）
        - 区间落在某个档内：选完全包含的最大档
        - 只有下限：选下限>=min的最低档；只有上限：选上限<=max的最高档
        """
        if salary_min is not None and salary_max is not None:
            contained = [c for (lo, hi), c in self.SALARY_CODES.items()
                         if c and lo >= salary_min and hi <= salary_max]
            if contained:
                return contained[-1]
            # 没有完全包含的档，选与用户区间重叠最大的档
            best = max(
                ((min(salary_max, hi) - max(salary_min, lo)), c)
                for (lo, hi), c in self.SALARY_CODES.items()
                if c and min(salary_max, hi) > max(salary_min, lo)
            )
            return best[1]
        if salary_min is not None:
            for (lo, hi), c in self.SALARY_CODES.items():
                if c and lo >= salary_min:
                    return c
            return "408"
        if salary_max is not None:
            best = ""
            for (lo, hi), c in self.SALARY_CODES.items():
                if c and hi <= salary_max:
                    best = c
            return best
        return ""

    async def _scroll_to_load_all(self, max_items: int = 0, page_obj=None):
        """滚动页面触发Boss的动态加载；max_items>0时捕获到足够数量即提前停止（每页约15条）"""
        page = page_obj or self.page
        prev_height = 0
        for _ in range(5):  # 最多滚动5次
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._human_stay(0.15, 0.3, page_obj=page)
            if max_items > 0:
                captured_count = sum(len(x) for x in (self._joblist_capture_lists.get(page) or []))
                if captured_count >= max_items:
                    break
            cur_height = await page.evaluate("() => document.body.scrollHeight")
            if cur_height == prev_height:
                break
            prev_height = cur_height
        # 滚回顶部
        await page.evaluate("window.scrollTo(0, 0)")

    def _parse_joblist_api(self, captured: List[List[Dict]]) -> List[Job]:
        """从页面自身 joblist 接口响应构建Job列表（字段干净，薪资为明文）"""
        jobs = []
        seen = set()
        for job_list in captured:
            for item in job_list:
                jid = str(item.get("encryptJobId") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                job = Job(platform=self.platform, job_id=jid)
                job.job_title = item.get("jobName") or ""
                job.job_url = f"{self.base_url}/job_detail/{jid}.html"
                job.company_name = item.get("brandName") or ""
                job.company_id = str(item.get("encryptBrandId") or item.get("brandId") or "")
                job.company_size = item.get("brandScaleName") or ""
                job.company_industry = item.get("brandIndustry") or item.get("industry") or ""
                job.salary_text = item.get("salaryDesc") or ""
                self._parse_salary(job)
                if self._is_daily_rate_salary(job.salary_text):
                    job.is_internship = True
                job.city = item.get("cityName") or ""
                area = item.get("areaDistrict") or ""
                district = item.get("businessDistrict") or ""
                job.area = (area + " · " + district) if (area and district) else (area or district)
                job.experience = item.get("jobExperience") or ""
                job.education = item.get("jobDegree") or ""
                labels = item.get("jobLabels") or []
                skills = item.get("skills") or []
                # jobLabels 里通常只是 经验+学历 的重复，前端已单独展示这两项，标签里剔除避免冗余
                job.tags = [l for l in labels if l and l != job.experience and l != job.education][:5]
                if not job.tags and skills:
                    job.tags = skills[:5]
                # 休息制度：从福利标签/每周工作天数描述里识别双休/大小周/单休
                job.rest_policy = self._detect_rest_policy(
                    list(item.get("welfareList") or []) + ([item.get("daysPerWeekDesc")] if item.get("daysPerWeekDesc") else [])
                )
                # HR信息
                job.hr_name = item.get("bossName") or ""
                job.hr_title = item.get("bossTitle") or ""
                job.hr_active_days = 0 if item.get("bossOnline") else None
                # 猎头/实习判断
                if item.get("goldHunter") or item.get("proxyJob"):
                    job.is_headhunter = True
                if "实习" in self._normalize_title(job.job_title):
                    job.is_internship = True
                if any(k in job.company_name for k in ["猎头", "人力", "咨询", "人力资源", "派遣", "外包"]):
                    job.is_headhunter = True
                jobs.append(job)
        return jobs

    def _boss_codes(self, values, code_map) -> List[str]:
        """把前端值(1-6等)或Boss原始编码(102/301等)归一化为Boss编码列表（供API直取body用）"""
        vals = values if isinstance(values, (list, tuple, set)) else ([values] if values else [])
        codes = []
        for x in vals:
            sx = str(x).strip()
            if not sx:
                continue
            try:
                ix = int(x)
            except (ValueError, TypeError):
                ix = None
            if ix is not None and ix in code_map:
                codes.append(code_map[ix])
            elif sx in code_map.values():
                codes.append(sx)
        return codes

    async def _fetch_joblist_api_page(self, page_obj, query, city, page, page_size=30,
                                      experience="", education="", company_scales="",
                                      salary_min=None, salary_max=None):
        """页面内 fetch 直调 joblist 接口（与Boss搜索页同款POST body）。
        返回 (job_list, has_more) 或 None（风控/异常，调用方应回退页面加载）。"""
        global _JOBLIST_API_LAST_CALL, _JOBLIST_CHALLENGE_UNTIL
        now = time.monotonic()
        if now < _JOBLIST_CHALLENGE_UNTIL:
            await asyncio.sleep(_JOBLIST_CHALLENGE_UNTIL - now)
            now = time.monotonic()
        wait = _JOBLIST_API_MIN_INTERVAL - (now - _JOBLIST_API_LAST_CALL)
        if wait > 0:
            await asyncio.sleep(wait)
        _JOBLIST_API_LAST_CALL = time.monotonic()

        exp_codes = ",".join(self._boss_codes(experience, self.EXP_CODES))
        edu_codes = ",".join(self._boss_codes(education, self.EDU_CODES))
        scale_codes = ",".join(self._boss_codes(company_scales, self.SCALE_CODES))
        salary_code = ""
        if salary_min is not None or salary_max is not None:
            salary_code = self._pick_salary_code(salary_min, salary_max) or ""
        city = str(city or "")
        q = quote(query or "", safe="")
        parts = [
            f"page={page}", f"pageSize={min(int(page_size or 30), 30)}",
            f"city={city}", f"query={q}",
            "expectInfo=", "multiSubway=", "multiBusinessDistrict=", "position=", "jobType=",
        ]
        if salary_code:
            parts.append(f"salary={salary_code}")
        if exp_codes:
            parts.append(f"experience={quote(exp_codes, safe='')}")
        if edu_codes:
            parts.append(f"degree={quote(edu_codes, safe='')}")
        if scale_codes:
            parts.append(f"scale={quote(scale_codes, safe='')}")
        parts += ["industry=", "stage=", "scene=1", "encryptExpectId="]
        body = "&".join(parts)
        referer = f"https://www.zhipin.com/web/geek/jobs?query={q}&city={city}"
        js = """async ({body, referer}) => {
            const r = await fetch('/wapi/zpgeek/search/joblist.json?_=' + Date.now(), {
                method: 'POST', credentials: 'include',
                headers: {
                    'Accept': 'application/json, text/plain, */*',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': referer
                },
                body: body
            });
            let data = null;
            try { data = await r.json(); } catch (e) {}
            const code = (data || {}).code;
            const zp = (data || {}).zpData || {};
            return { code: code, jobList: zp.jobList || [], hasMore: !!zp.hasMore };
        }"""
        try:
            res = await page_obj.evaluate(js, {"body": body, "referer": referer})
        except Exception as e:
            self.log(f"joblist API直取异常: {e}")
            return None
        if not res or res.get("code") != 0:
            _JOBLIST_CHALLENGE_UNTIL = time.monotonic() + 8.0
            self.log(f"joblist API直取返回code={res.get('code') if res else 'None'}（风控限频，全局冷却8s）")
            return None
        return res.get("jobList") or [], bool(res.get("hasMore"))

    async def _fetch_joblist_api_with_retry(self, page_obj, query, city, page, page_size=30,
                                           experience="", education="", company_scales="",
                                           salary_min=None, salary_max=None):
        """API直取+重试：返回 (job_list, has_more) 或 None。
        code:37（您的环境存在异常）是临时风控，导航刷新验证状态+冷却后重试一次。"""
        for attempt in range(2):
            res = await self._fetch_joblist_api_page(
                page_obj, query, city, page=page, page_size=page_size,
                experience=experience, education=education,
                company_scales=company_scales, salary_min=salary_min, salary_max=salary_max,
            )
            if res is not None:
                return res
            try:
                await page_obj.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            await asyncio.sleep(6)
        return None

    async def _search_jobs_fast(self, page_obj, query, city, experience, education,
                                company_scales, salary_min, salary_max,
                                page_size=30, target_count=90) -> List[Job]:
        """API直取快路径：直调joblist接口拉取1-2页职位；失败返回[]由调用方回退页面加载"""
        jobs = []
        t_start = time.monotonic()
        try:
            cur = (page_obj.url or "") if hasattr(page_obj, "url") else ""
            if "zhipin.com" not in cur:
                await page_obj.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(0.3)
            t0 = time.monotonic()
            page1, has_more = await self._fetch_joblist_api_with_retry(
                page_obj, query, city, page=1, page_size=page_size,
                experience=experience, education=education,
                company_scales=company_scales, salary_min=salary_min, salary_max=salary_max,
            ) or (None, False)
            if not page1:
                return []
            jobs = self._parse_joblist_api([page1])
            print(f"[API直取] {query}@{city} page1: {len(jobs)} 个职位, 接口耗时{time.monotonic()-t0:.1f}s")
            # 首页充足时不再取第2页（避免多余请求触发限频）；仅稀疏结果补一页
            if len(jobs) < min(target_count, 15) and has_more:
                page2, _ = await self._fetch_joblist_api_with_retry(
                    page_obj, query, city, page=2, page_size=page_size,
                    experience=experience, education=education,
                    company_scales=company_scales, salary_min=salary_min, salary_max=salary_max,
                ) or (None, False)
                if page2:
                    more = self._parse_joblist_api([page2])
                    seen = {j.job_id for j in jobs}
                    jobs.extend(j for j in more if j.job_id not in seen)
                    self.log(f"API直取 page2: 累计 {len(jobs)} 个职位")
        except Exception as e:
            print(f"[API直取] {query}@{city} 失败({e})，回退页面加载，总耗时{time.monotonic()-t_start:.1f}s")
            return []
        print(f"[API直取] {query}@{city} 成功，总耗时{time.monotonic()-t_start:.1f}s，返回{len(jobs)}个")
        return jobs

    async def _parse_job_list(self, page_obj=None) -> List[Job]:
        """从DOM解析职位列表"""
        page = page_obj or self.page
        jobs = []
        try:
            # Boss直聘列表项的各种选择器（Boss经常改类名，多备几个）
            selectors = [
                "ul.rec-job-list li.job-card-box",
                "li.job-card-box",
                ".job-list-box li.job-card-wrapper",
                ".job-list .job-card-wrap",
                ".search-job-result .job-card-wrapper",
                "li.job-card-wrapper",
                "[class*='job-card-wrapper']",
                ".job-card-wrapper",
                "[class*='job-card']",
                ".job-list-box li",
                ".search-job-result li",
                ".position-list li",
            ]
            cards = []
            used_sel = ""
            for sel in selectors:
                cards = await page.query_selector_all(sel)
                if cards:
                    used_sel = sel
                    break

            if not cards:
                self.log("所有选择器都未匹配到职位卡片")
                return []

            self.log(f"使用选择器 '{used_sel}' 匹配到 {len(cards)} 个卡片")

            # 新版页面（li.job-card-box）：一次 evaluate 批量提取，避免逐卡调用慢速解析
            if used_sel in ("ul.rec-job-list li.job-card-box", "li.job-card-box"):
                try:
                    raw_items = await page.evaluate("""() => {
                        const items = [];
                        const cards = document.querySelectorAll('li.job-card-box');
                        for (const card of cards) {
                            const link = card.querySelector("a[href*='/job_detail/']");
                            const href = link ? (link.getAttribute('href') || '') : '';
                            const m = href.match(/job_detail\/([\w.]+)\.html/);
                            const title = link ? (link.innerText || '').trim() : '';
                            const salaryEl = card.querySelector('.job-salary, .salary');
                            const salary = salaryEl ? (salaryEl.innerText || '').trim() : '';
                            const locEl = card.querySelector('.company-location');
                            const loc = locEl ? (locEl.innerText || '').trim() : '';
                            const boss = card.querySelector('.boss-info .boss-name, span.boss-name');
                            const company = boss ? (boss.innerText || '').trim() : '';
                            const tags = Array.from(card.querySelectorAll('.tag-list li')).map(t => (t.innerText || '').trim());
                            items.push({
                                job_id: m ? m[1] : '',
                                job_url: href.startsWith('/') ? 'https://www.zhipin.com' + href : href,
                                job_title: title.split('\\n')[0],
                                salary_text: salary,
                                location: loc,
                                company_name: company,
                                experience: tags[0] || '',
                                education: tags[1] || '',
                                tags: tags.slice(2),
                            });
                        }
                        return items;
                    }""")
                    for item in raw_items:
                        try:
                            j = Job(platform=self.platform, job_id=item.get("job_id") or "")
                            j.job_url = item.get("job_url") or ""
                            j.job_title = item.get("job_title") or ""
                            j.salary_text = self._decode_salary_glyphs(item.get("salary_text") or "")
                            self._parse_salary(j)
                            if self._is_daily_rate_salary(j.salary_text):
                                j.is_internship = True
                            j.company_name = item.get("company_name") or ""
                            j.experience = item.get("experience") or ""
                            j.education = item.get("education") or ""
                            j.tags = [t for t in (item.get("tags") or []) if t]
                            j.rest_policy = self._detect_rest_policy(j.tags)
                            loc_parts = [p for p in re.split(r"[\s·|/\\]+", item.get("location") or "") if p]
                            if loc_parts:
                                j.city = loc_parts[0]
                                j.area = loc_parts[1] if len(loc_parts) > 1 else ""
                            if "实习" in self._normalize_title(j.job_title):
                                j.is_internship = True
                            if j.job_id:
                                jobs.append(j)
                        except Exception as e:
                            self.log(f"批量解析单条出错: {e}")
                    if jobs:
                        self.log(f"批量提取到 {len(jobs)} 个职位")
                        return jobs
                except Exception as e:
                    self.log(f"批量提取失败，回退逐卡解析: {e}")

            # 旧版页面/批量失败：逐卡解析
            for card in cards:
                try:
                    job = await self._parse_single_card(card)
                    if job and job.job_id:
                        jobs.append(job)
                except Exception as e:
                    self.log(f"解析单条卡片出错: {e}")
        except Exception as e:
            self.log(f"解析列表失败: {e}")
        return jobs

    async def _parse_single_card(self, card) -> Job:
        """解析单个职位卡片DOM -> Job对象"""
        j = Job(platform=self.platform, job_id="")

        # 1. 链接和job_id
        try:
            link_el = await card.query_selector("a.job-card-left, a[href*='/job_detail/']")
            if link_el:
                href = await link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = self.base_url + href
                j.job_url = href
                m = re.search(r"job_detail/([\w.]+)\.html", href)
                if m:
                    j.job_id = m.group(1)
        except Exception:
            pass

        # 2. 职位名称（优先取链接文本，避免匹配到含薪资的容器 .job-title）
        try:
            title_el = await card.query_selector("a[href*='/job_detail/'], a.job-name, .job-name, .job-title")
            if title_el:
                j.job_title = (await title_el.inner_text()).strip().split("\n")[0].strip()
                if "实习" in self._normalize_title(j.job_title):
                    j.is_internship = True
        except Exception:
            pass

        # 3. 薪资文本（新版页面用字体混淆数字，需解码）
        try:
            salary_el = await card.query_selector(".salary, .job-salary")
            if salary_el:
                j.salary_text = self._decode_salary_glyphs((await salary_el.inner_text()).strip())
                self._parse_salary(j)
                if self._is_daily_rate_salary(j.salary_text):
                    j.is_internship = True
        except Exception:
            pass

        # 4. 经验/学历（新版页面在 .tag-list，旧版在 .job-info）
        try:
            info_el = await card.query_selector(".tag-list, .job-info-area, .job-info")
            if info_el:
                text = (await info_el.inner_text()).strip()
                parts = re.split(r"[\s·|/\\]+", text)
                for p in parts:
                    if not p:
                        continue
                    if "经验" in p or re.search(r"\d+年", p):
                        if not j.experience:
                            j.experience = p
                    elif re.search(r"大专|本科|硕士|博士|学历不限", p):
                        if not j.education:
                            j.education = p
        except Exception:
            pass

        # 4b. 城市/区域（新版页面在 .company-location，如 "杭州·西湖区·西溪"）
        try:
            loc_el = await card.query_selector(".company-location, .job-location, .job-area")
            if loc_el:
                loc_text = (await loc_el.inner_text()).strip()
                loc_parts = re.split(r"[\s·|/\\]+", loc_text)
                for p in loc_parts:
                    if not p:
                        continue
                    if not j.city:
                        j.city = p
                    elif not j.area:
                        j.area = p
            else:
                # 旧版页面：从 .job-info 里提取城市
                info_el = await card.query_selector(".job-info-area, .job-info")
                if info_el:
                    text = (await info_el.inner_text()).strip()
                    for p in re.split(r"[\s·|/\\]+", text):
                        if "区" in p or p in ["深圳", "广州", "北京", "上海", "杭州"]:
                            if not j.city:
                                j.city = p
                            elif not j.area:
                                j.area = p
                            break
        except Exception:
            pass

        # 5. 公司名/规模/行业
        try:
            company_el = await card.query_selector(".company-name, .comp-name a, .boss-info .boss-name, span.boss-name")
            if company_el:
                j.company_name = (await company_el.inner_text()).strip()
            info_el = await card.query_selector(".company-info, .comp-tag-list")
            if info_el:
                tags = await info_el.query_selector_all("li, span")
                tag_texts = []
                for t in tags:
                    tag_texts.append((await t.inner_text()).strip())
                # Boss顺序一般是：规模 / 行业 / 融资
                for t in tag_texts:
                    if "人" in t or re.match(r"\d+-\d+", t):
                        j.company_size = t
                    else:
                        if not j.company_industry:
                            j.company_industry = t
                if not j.company_size and len(tag_texts) >= 2:
                    j.company_size = tag_texts[0]
                    j.company_industry = " ".join(tag_texts[1:])
                # 猎头判断
                company_lower = j.company_name.lower()
                if any(k in j.company_name or k in company_lower for k in ["猎头", "人力", "咨询", "人力资源", "派遣", "外包"]):
                    j.is_headhunter = True
        except Exception:
            pass

        # 6. HR信息 + 活跃状态
        try:
            hr_el = await card.query_selector(".info-public, .boss-info, .hr-info")
            if hr_el:
                hr_text = (await hr_el.inner_text()).strip()
                hr_parts = re.split(r"[\s·|]+", hr_text, maxsplit=1)
                j.hr_name = hr_parts[0] if hr_parts else ""
                j.hr_title = hr_parts[1] if len(hr_parts) > 1 else ""
                if "猎头" in j.hr_title or "猎头" in j.hr_name:
                    j.is_headhunter = True
            # HR活跃时间
            active_el = await card.query_selector(".boss-time, .hr-active, .icon-info-public em, .job-card-footer")
            if active_el:
                j.hr_active_text = (await active_el.inner_text()).strip()
                j.hr_active_days = self._parse_active_days(j.hr_active_text)
        except Exception:
            pass

        # 7. 职位技能标签
        try:
            tag_els = await card.query_selector_all(".job-card-footer .tag-list li, .job-card-body .tag-list li")
            if tag_els:
                for t in tag_els:
                    txt = (await t.inner_text()).strip()
                    if txt and txt not in j.tags:
                        j.tags.append(txt)
        except Exception:
            pass

        # 休息制度：从卡片标签里识别双休/大小周/单休
        j.rest_policy = self._detect_rest_policy(j.tags)
        return j

    def _decode_salary_glyphs(self, text: str) -> str:
        """解码Boss直聘新版页面的字体混淆数字（0xE031-0xE03A 对应 0-9）"""
        if not text:
            return text
        out = []
        for ch in text:
            cp = ord(ch)
            if 0xE031 <= cp <= 0xE03A:
                out.append(chr(ord("0") + (cp - 0xE031)))
            else:
                out.append(ch)
        return "".join(out)

    def _parse_salary(self, job: Job):
        """解析薪资文本 -> 数值"""
        text = job.salary_text
        if not text:
            return
        # "15-25K·14薪" / "20-40K" / "面议"
        if "面议" in text:
            return
        m = re.search(r"(\d+)(?:\.(\d+))?-(\d+)(?:\.(\d+))?K", text)
        if m:
            job.salary_min = int(m.group(1))
            job.salary_max = int(m.group(3))
        m2 = re.search(r"(\d+)薪", text)
        if m2:
            job.salary_months = int(m2.group(1))

    def _parse_active_days(self, text: str) -> Optional[int]:
        """解析HR活跃文本 -> 天数"""
        if not text:
            return None
        if re.search(r"刚刚|今天|今日|在线", text):
            return 0
        if "昨天" in text:
            return 1
        m = re.search(r"(\d+)\s*天", text)
        if m:
            return int(m.group(1))
        return None

    def _apply_filter_rules(self, job: Job, rules: List[Dict]) -> str:
        """应用黑白名单规则: return 'whitelist'/'blacklist'/None"""
        text_parts = []
        for field in ["company_name", "job_title", "city", "tags", "hr_title"]:
            v = getattr(job, field, None)
            if isinstance(v, list):
                text_parts.extend(v)
            elif v:
                text_parts.append(str(v))
        text = " ".join(text_parts).lower()

        whitelist_hit = False
        for r in rules:
            if r.get("match_mode") == "contains":
                keywords = [k.strip().lower() for k in (r.get("keywords") or "").split(",") if k.strip()]
                if not keywords:
                    continue
                if any(k in text for k in keywords):
                    if r.get("rule_type") == "whitelist":
                        whitelist_hit = True
                        job.match_reason = "白名单：命中关键词"
                    elif r.get("rule_type") == "blacklist":
                        job.match_reason = f"黑名单：{r.get('rule_name') or '命中关键词'}"
                        return "blacklist"
        return "whitelist" if whitelist_hit else None

    def _is_loose_irrelevant_title(self, title: str) -> bool:
        """宽松模式标题过滤（非开发类关键词：销售/AI产品经理/运营等）：
        不套用严格排除词（否则会误杀 销售顾问/客户经理/AI产品经理 等正常岗位），
        仅要求标题至少含一个岗位相关词，过滤"校招补录/保底薪资/一单20+"等无意义标题"""
        if not title:
            return False
        t = self._normalize_title(title).lower()
        return not any(w in t for w in self.LOOSE_RELEVANT_WORDS)

    def _is_irrelevant_title(self, title: str) -> bool:
        """标题相关度白名单（严格模式=AI应用开发方向）：
        1) 先归一化标题（Boss字体混淆的U+2F00部首字形/兼容字 -> 标准汉字）；
        2) 含排除词（标注/评测/产品经理/运营/测试/工艺/设备等非开发岗特征）直接剔除；
        3) 必须【同时】含AI相关词（AI/大模型/Agent/智能体/LLM/RAG/Prompt等）与
           开发/工程岗位词（开发/工程师/应用/后端等）才算相关——单有开发词而无AI词
           （如嵌入式/芯片/射频/光学/软件工程师）不是AI应用开发岗，单有AI词而无
           岗位词（如AI健康管理师）也不是开发岗；
        4) 算法/研究向岗位拦截：标题含 算法/深度学习/机器学习/多模态/图像/框架 等词
           属于模型研发而非AI应用开发，一律剔除（除非标题明确带「应用」二字）。
        """
        if not title:
            return False
        t = self._normalize_title(title).lower()
        if any(w in t for w in self.TITLE_EXCLUDE_WORDS):
            return True
        if not (
            any(w in t for w in self.TITLE_AI_WORDS)
            and any(w in t for w in self.TITLE_JOB_WORDS)
        ):
            return True
        if any(w in t for w in self.ALGO_RESEARCH_WORDS):
            if "应用" not in t:
                return True
        return False

    def _is_generic_dev_title(self, title: str) -> bool:
        """标题是通用开发岗（含开发/工程词但无AI词、无排除词、非算法研究岗）：
        可能是Boss按JD匹配返回的AI应用开发岗（标题未体现AI），需读JD二次确认"""
        if not title:
            return False
        t = self._normalize_title(title).lower()
        if any(w in t for w in self.TITLE_EXCLUDE_WORDS):
            return False
        if any(w in t for w in self.ALGO_RESEARCH_WORDS):
            return False
        if any(w in t for w in self.TITLE_AI_WORDS):
            return False
        return any(w in t for w in self.TITLE_JOB_WORDS)

    # JD级AI校验：强词（明确AI应用开发方向）单个即算；普通词需累计≥2次才算，
    # 避免JD里只提一次"AI"的电机/嵌入式/化工等通用岗混入
    JD_AI_STRONG_WORDS = [
        "大模型", "大语言模型", "智能体", "agentic", "langchain", "mcp",
        "提示词", "prompt", "微调", "向量数据库", "检索增强", "智能问答",
        "智能助理", "智能助手", "aigc", "llm", "gpt", "rag",
    "vibe coding", "ai coding", "智能编程", "代码生成", "编程助手",
    "copilot", "cursor", "claude code",
    ]
    JD_AI_MEDIUM_WORDS = [
        "ai", "agent", "人工智能", "深度学习", "机器学习", "多模态", "nlp",
        "transformer", "embedding", "智能应用", "知识库", "计算机视觉",
    "claude", "ai编程",
    ]

    @classmethod
    def _jd_has_ai_keywords(cls, text: str) -> bool:
        """JD文本是否含AI应用开发相关关键词（标题通用岗位的二次确认）。
        强词命中1个即通过；普通词每个1分、累计≥2分通过；避免只提一次AI的通用岗混入"""
        if not text:
            return False
        low = text.lower()
        for pat in cls.JD_AI_STRONG_WORDS:
            if pat in low:
                return True
        score = 0
        for pat in cls.JD_AI_MEDIUM_WORDS:
            try:
                if re.search(re.escape(pat), low):
                    score += 1
            except Exception:
                if pat in low:
                    score += 1
            if score >= 2:
                return True
        return False

    async def jd_has_ai(self, job, page_obj=None) -> bool:
        """打开职位详情页，检查JD是否含AI应用开发关键词（用于标题通用的岗位）"""
        page = page_obj or self.page
        try:
            await page.goto(job.job_url, wait_until="domcontentloaded", timeout=30000)
            await self._human_stay(0.15, 0.3, page_obj=page)
            jd = ""
            for sel in (".job-sec-text", ".job-detail-section .text", ".detail-content", ".job-detail-section"):
                try:
                    el = await page.query_selector(sel)
                    if el:
                        jd = (await el.inner_text()) or ""
                        if jd.strip():
                            break
                except Exception:
                    continue
            if not jd.strip():
                jd = await page.evaluate("() => document.body.innerText") or ""
            return self._jd_has_ai_keywords(jd)
        except Exception:
            return False

    @staticmethod
    def _is_daily_rate_salary(text: str) -> bool:
        """按天/按小时结算的薪资（元/天、元/时、日结等）→ 实习/兼职/临时岗特征，搜索阶段直接过滤"""
        if not text:
            return False
        return any(k in text for k in ["元/天", "元/时", "元/小时", "日结", "按天", "天结"])

    @staticmethod
    @staticmethod
    def _detect_rest_policy(texts) -> str:
        """从标签/福利/JD文本中识别休息制度：双休/大小周/单休，识别不到返回空串
        注意顺序：先判大小周（"单双休"同时含"单休"/"双休"子串，必须优先）"""
        if not texts:
            return ""
        joined = " ".join(str(t) for t in texts)
        if "大小周" in joined or "单双休" in joined:
            return "大小周"
        if ("单休" in joined or "做六休一" in joined or "上六休一" in joined
                or "六天工作" in joined or "六天制" in joined):
            return "单休"
        if ("双休" in joined or "周末双休" in joined or "六日双休" in joined
                or "双休日" in joined or "做五休二" in joined or "上五休二" in joined
                or "五天工作" in joined):
            return "双休"
        return ""

    @staticmethod
    def _normalize_title(title: str) -> str:
        """归一化职位标题：Boss直聘字体混淆会把汉字替换成U+2F00部首字形或兼容字
        （如「应⽤开发实习⽣」里的⽤/⽑），NFKC可还原为标准汉字，保证关键词匹配可靠。"""
        if not title:
            return ""
        return unicodedata.normalize("NFKC", title)

    async def _enrich_job_from_detail(self, job: Job):
        """从详情页补充信息"""
        try:
            company_el = await self.page.query_selector(".company-info .company-name")
            if company_el and not job.company_name:
                job.company_name = (await company_el.inner_text()).strip()
        except Exception:
            pass
