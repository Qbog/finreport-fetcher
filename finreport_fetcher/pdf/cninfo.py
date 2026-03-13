from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from ..utils.dates import ReportPeriod


@dataclass(frozen=True)
class PdfResult:
    ok: bool
    url: str | None = None
    local_path: str | None = None
    title: str | None = None
    note: str | None = None


def _build_cninfo_stock_param(code6: str) -> str:
    """cninfo 查询接口需要 stock 参数形如: "600519,gssh0600519"。

    这里复用 akshare 内置的股票代码映射（私有函数），失败则退化为 "600519,"。
    """

    try:
        from akshare.stock_feature.stock_disclosure_cninfo import __get_stock_json  # type: ignore

        m = __get_stock_json("沪深京")
        org = m.get(code6)
        if not org:
            return f"{code6},"
        return f"{code6},{org}"
    except Exception:
        return f"{code6},"


def _query_cninfo_announcements(code6: str, category: str, se_date: str, *, page_num: int = 1, page_size: int = 30):
    """直接调用 cninfo hisAnnouncement/query，拿到包含 adjunctUrl 的公告列表。"""

    category_map = {
        "年报": "category_ndbg_szsh;",
        "半年报": "category_bndbg_szsh;",
        "一季报": "category_yjdbg_szsh;",
        "三季报": "category_sjdbg_szsh;",
    }

    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    payload = {
        "pageNum": page_num,
        "pageSize": page_size,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": _build_cninfo_stock_param(code6),
        "searchkey": "",
        "secid": "",
        "category": category_map.get(category, ""),
        "trade": "",
        "seDate": se_date,
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
        "Referer": "http://www.cninfo.com.cn/",
        "Accept": "application/json, text/plain, */*",
    }

    r = requests.post(url, data=payload, headers=headers, timeout=20)
    r.raise_for_status()
    j = r.json()
    return j.get("announcements") or []


def find_and_download_period_pdf(
    code6: str,
    period_end: date,
    out_path: Path,
    session: requests.Session | None = None,
) -> PdfResult:
    """尽量从巨潮公告中定位该报告期 PDF 并下载（使用接口里的 adjunctUrl）。

    out_path: 目标 PDF 文件路径（使用不同文件名区分，不使用日期文件夹）。

    注意：这是“尽力而为”实现；失败会返回 ok=False + note。
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()

    rp = ReportPeriod(period_end)
    cat = rp.category_cninfo
    if not cat:
        return PdfResult(ok=False, note="无法识别报告期类型（非标准季末/年末）")

    # 公告时间范围：宽松窗口（报告期所在年份 ~ 后两年）
    start = date(period_end.year, 1, 1)
    end = date(period_end.year + 2, 12, 31)
    se_date = f"{start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')}"

    # 分页拉取，避免 pageSize=30 不够导致漏掉目标报告
    anns = []
    try:
        for pn in range(1, 11):  # 最多翻 10 页（300 条）
            page = _query_cninfo_announcements(code6=code6, category=cat, se_date=se_date, page_num=pn, page_size=30)
            if not page:
                break
            anns.extend(page)
            # early stop: if already have plenty and it's an old period, no need to keep paging
            if len(anns) >= 120:
                break
    except Exception as e:
        return PdfResult(ok=False, note=f"调用 cninfo 查询接口失败: {e}")

    if not anns:
        return PdfResult(ok=False, note="cninfo 返回公告列表为空")

    y = str(period_end.year)
    keywords = {
        "年报": ["年度报告", "年报"],
        "半年报": ["半年度报告", "半年报"],
        "一季报": ["第一季度报告", "一季度报告"],
        "三季报": ["第三季度报告", "三季度报告"],
    }[cat]

    def match_keyword(title: str) -> bool:
        return any(k in title for k in keywords)

    def is_summary(title: str) -> bool:
        # 巨潮里经常有：年度报告摘要/半年度报告摘要/...；用户希望下载全文而非摘要
        return "摘要" in title

    def is_full_text(title: str) -> bool:
        # 常见全文标识：全文 / 正文
        return ("全文" in title) or ("正文" in title)

    def is_noise(title: str) -> bool:
        # 排除“提示性公告/披露提示/说明”等非报告正文
        noise_words = ["提示", "披露", "公告", "说明", "问询", "回复"]
        return any(w in title for w in noise_words)

    # 1) 最优：同年 + 关键词 + 全文/正文，且非摘要，且非噪声
    cand = []
    for a in anns:
        title = str(a.get("announcementTitle", ""))
        if match_keyword(title) and y in title and (not is_summary(title)) and (not is_noise(title)) and is_full_text(title):
            cand.append(a)

    # 2) 次优：同年 + 关键词，且非摘要，且非噪声
    if not cand:
        for a in anns:
            title = str(a.get("announcementTitle", ""))
            if match_keyword(title) and y in title and (not is_summary(title)) and (not is_noise(title)):
                cand.append(a)

    # 3) 退一步：关键词 + 全文/正文，且非摘要，且非噪声
    if not cand:
        for a in anns:
            title = str(a.get("announcementTitle", ""))
            if match_keyword(title) and (not is_summary(title)) and (not is_noise(title)) and is_full_text(title):
                cand.append(a)

    # 4) 再退：关键词，且非摘要，且非噪声
    if not cand:
        for a in anns:
            title = str(a.get("announcementTitle", ""))
            if match_keyword(title) and (not is_summary(title)) and (not is_noise(title)):
                cand.append(a)

    # 不再兜底下载“摘要”（用户要求下载报表正文/全文而非摘要）
    if not cand:
        return PdfResult(ok=False, note=f"未匹配到 {period_end} 的定期报告PDF（已排除摘要）。")

    # 按公告时间倒序
    cand.sort(key=lambda x: x.get("announcementTime", 0), reverse=True)
    a = cand[0]

    title = str(a.get("announcementTitle", ""))
    adjunct = a.get("adjunctUrl")
    if not adjunct:
        return PdfResult(ok=False, title=title, note="公告缺少 adjunctUrl，无法定位 PDF")

    pdf_url = "http://static.cninfo.com.cn/" + str(adjunct).lstrip("/")

    try:
        r = sess.get(
            pdf_url,
            timeout=60,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
                "Referer": "http://www.cninfo.com.cn/",
                "Accept": "application/pdf,application/octet-stream,*/*",
            },
        )
        r.raise_for_status()
        out_path.write_bytes(r.content)
    except Exception as e:
        return PdfResult(ok=False, url=pdf_url, title=title, note=f"下载 PDF 失败: {e}")

    return PdfResult(ok=True, url=pdf_url, local_path=str(out_path), title=title)
