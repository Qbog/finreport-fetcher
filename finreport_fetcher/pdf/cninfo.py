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


def _query_cninfo_announcements(code6: str, category: str, se_date: str):
    """直接调用 cninfo hisAnnouncement/query，拿到包含 adjunctUrl 的公告列表。"""

    category_map = {
        "年报": "category_ndbg_szsh;",
        "半年报": "category_bndbg_szsh;",
        "一季报": "category_yjdbg_szsh;",
        "三季报": "category_sjdbg_szsh;",
    }

    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    payload = {
        "pageNum": 1,
        "pageSize": 30,
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

    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    j = r.json()
    return j.get("announcements") or []


def find_and_download_period_pdf(
    code6: str,
    period_end: date,
    out_dir: Path,
    session: requests.Session | None = None,
) -> PdfResult:
    """尽量从巨潮公告中定位该报告期 PDF 并下载（使用接口里的 adjunctUrl）。

    注意：这是“尽力而为”实现；失败会返回 ok=False + note。
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()

    rp = ReportPeriod(period_end)
    cat = rp.category_cninfo
    if not cat:
        return PdfResult(ok=False, note="无法识别报告期类型（非标准季末/年末）")

    # 公告时间范围：宽松窗口（报告期所在年份 ~ 后两年）
    start = date(period_end.year, 1, 1)
    end = date(period_end.year + 2, 12, 31)
    se_date = f"{start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')}"

    try:
        anns = _query_cninfo_announcements(code6=code6, category=cat, se_date=se_date)
    except Exception as e:
        return PdfResult(ok=False, note=f"调用 cninfo 查询接口失败: {e}")

    if not anns:
        return PdfResult(ok=False, note="cninfo 返回公告列表为空")

    y = str(period_end.year)
    keyword = {
        "年报": "年度报告",
        "半年报": "半年度报告",
        "一季报": "第一季度报告",
        "三季报": "第三季度报告",
    }[cat]

    cand = []
    for a in anns:
        title = str(a.get("announcementTitle", ""))
        if keyword in title and y in title:
            cand.append(a)

    if not cand:
        for a in anns:
            title = str(a.get("announcementTitle", ""))
            if keyword in title:
                cand.append(a)

    if not cand:
        return PdfResult(ok=False, note=f"未匹配到 {period_end} 的定期报告公告（{cat}）")

    # 按公告时间倒序
    cand.sort(key=lambda x: x.get("announcementTime", 0), reverse=True)
    a = cand[0]

    title = str(a.get("announcementTitle", ""))
    adjunct = a.get("adjunctUrl")
    if not adjunct:
        return PdfResult(ok=False, title=title, note="公告缺少 adjunctUrl，无法定位 PDF")

    pdf_url = "http://static.cninfo.com.cn/" + str(adjunct).lstrip("/")

    pdf_path = out_dir / "report.pdf"
    try:
        r = sess.get(pdf_url, timeout=60)
        r.raise_for_status()
        pdf_path.write_bytes(r.content)
    except Exception as e:
        return PdfResult(ok=False, url=pdf_url, title=title, note=f"下载 PDF 失败: {e}")

    return PdfResult(ok=True, url=pdf_url, local_path=str(pdf_path), title=title)
