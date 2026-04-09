"""
PubMed Batch Downloader using NCBI E-utilities
Extracts: PMID, PMCID, DOI, Journal, Publication_types, Date, Author, Title, Abstract
Saves results in batched JSON files; logs to log/log_pubmed/

核心策略：双层自适应二分
  第一层：日期区间二分
    ① count ≤ MAX_PER_SEG → 直接 efetch（retstart 永远 < 9999）
    ② count > MAX_PER_SEG，区间可切 → 日期对半，递归
    ③ count > MAX_PER_SEG，单日无法再切 → 进入第二层

  第二层：PMID 范围二分（解决单日超限）
    在检索词中追加 AND minPMID:maxPMID[UID]，将 PMID 空间对半切
    递归直到每个区间 count ≤ MAX_PER_SEG
    不依赖 idlist 翻页，彻底绕开 NCBI 的 9999 硬限制

PMID 范围上界 PMID_MAX 设为 40,000,000（截至 2026 年的安全上界）
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import requests

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
CONFIG_PATH = Path(__file__).with_name("pubmed_config.json")


def load_credentials(config_path: Path) -> tuple[str, str]:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Missing PubMed config file: {config_path}"
        ) from exc

    email = str(config.get("email", "")).strip()
    api_key = str(config.get("api_key", "")).strip()

    if not email:
        raise ValueError(f"Missing 'email' in {config_path}")
    if not api_key:
        raise ValueError(f"Missing 'api_key' in {config_path}")

    return email, api_key


EMAIL, API_KEY = load_credentials(CONFIG_PATH)

BASE_QUERY = (
    "(((((((((((((((((leukocyte) OR (monocyte)) OR (lymphocyte)) OR (T cell)) "
    "OR (T follicular regulatory cell)) OR (T follicular helper cell)) OR (B cell)) "
    "OR (plasma cell)) OR (plasmablast)) OR (natural killer cell)) OR (granulocyte)) "
    "OR (basophil)) OR (eosinophil)) OR (neutrophil)) OR (macrophage)) OR (dendritic cell)) "
    "OR (mast cell))"
)

GLOBAL_START = date(2016, 1, 1)
GLOBAL_END   = date(2020, 12, 31)

# PMID 二分的初始范围（覆盖全部 PubMed 记录的安全上界）
PMID_MIN = 1
PMID_MAX = 99_999_999

OUTPUT_DIR  = Path("data/pubmed_output/2016-2020")
LOG_DIR     = Path("log/log_pubmed/2016-2020")
MAX_PER_SEG = 9000   # 叶子区间最大记录数（< NCBI 硬限 9999）
FETCH_BATCH = 500    # 每次 efetch 下载条数
SAVE_BATCH  = 5000   # 每个 JSON 文件最大记录数
SLEEP_SEC   = 0.11   # 请求间隔（API Key 允许 10 req/s）

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "pubmed_download.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 全局状态（跨递归共享）
# ─────────────────────────────────────────────
_buffer:     list[dict] = []
_file_index: int        = 141
_downloaded: int        = 0


# ─────────────────────────────────────────────
# HTTP 工具
# ─────────────────────────────────────────────
def request_with_retry(method: str, url: str, max_retries: int = 5, **kwargs) -> requests.Response:
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=60, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            wait = 2 ** attempt
            log.warning(f"Attempt {attempt}/{max_retries} failed: {exc}. Retry in {wait}s…")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {max_retries} retries: {url}")


# ─────────────────────────────────────────────
# 日期工具
# ─────────────────────────────────────────────
def fmt(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def mid_date(d1: date, d2: date) -> date:
    return d1 + (d2 - d1) // 2


# ─────────────────────────────────────────────
# 检索词构建
# ─────────────────────────────────────────────
def build_query(d_from: date, d_to: date, pmid_lo: int = None, pmid_hi: int = None) -> str:
    """
    构建检索词。
    可选追加 AND pmid_lo:pmid_hi[UID] 用于 PMID 范围二分。
    """
    q = (
        f'{BASE_QUERY} AND '
        f'("{fmt(d_from)}"[Date - Publication] : "{fmt(d_to)}"[Date - Publication])'
    )
    if pmid_lo is not None and pmid_hi is not None:
        q += f" AND {pmid_lo}:{pmid_hi}[UID]"
    return q


# ─────────────────────────────────────────────
# esearch with usehistory=y → (count, WebEnv, query_key)
# ─────────────────────────────────────────────
def esearch_history(query: str) -> tuple[int, str, str]:
    params = {
        "db": "pubmed",
        "term": query,
        "usehistory": "y",
        "retmax": 0,        # 只要 count + WebEnv，不要 idlist
        "retmode": "json",
        "email": EMAIL,
        "api_key": API_KEY,
    }
    resp   = request_with_retry("GET", BASE_URL + "esearch.fcgi", params=params)
    result = json.loads(resp.text, strict=False)["esearchresult"]
    return (
        int(result.get("count", 0)),
        result.get("webenv", ""),
        result.get("querykey", ""),
    )


# ─────────────────────────────────────────────
# efetch → XML 字符串
# ─────────────────────────────────────────────
def efetch_xml(web_env: str, query_key: str, retstart: int, retmax: int) -> str:
    params = {
        "db": "pubmed",
        "WebEnv": web_env,
        "query_key": query_key,
        "retstart": retstart,
        "retmax": retmax,
        "rettype": "abstract",
        "retmode": "xml",
        "email": EMAIL,
        "api_key": API_KEY,
    }
    return request_with_retry("GET", BASE_URL + "efetch.fcgi", params=params).text


# ─────────────────────────────────────────────
# 叶子下载：用 WebEnv 批量 efetch
# ─────────────────────────────────────────────
def fetch_leaf(web_env: str, query_key: str, count: int, label: str) -> None:
    global _downloaded
    for retstart in range(0, count, FETCH_BATCH):
        retmax  = min(FETCH_BATCH, count - retstart)
        xml_str = efetch_xml(web_env, query_key, retstart, retmax)
        records = parse_pubmed_xml(xml_str)
        _buffer.extend(records)
        _downloaded += len(records)
        flush_buffer()
        log.info(f"  {label} retstart={retstart:,} → {len(records)} | total={_downloaded:,}")
        time.sleep(SLEEP_SEC)


# ─────────────────────────────────────────────
# 第二层递归：PMID 范围二分（单日超限兜底）
#
# 在检索词中加 AND pmid_lo:pmid_hi[UID]，将 PMID 数值空间对半切。
# 不依赖 idlist 翻页，彻底规避 NCBI 9999 硬限制。
# ─────────────────────────────────────────────
def fetch_by_pmid_range(
    d: date,
    pmid_lo: int,
    pmid_hi: int,
    depth: int = 0,
) -> None:
    indent = "    " + "  " * depth
    query  = build_query(d, d, pmid_lo, pmid_hi)
    count, web_env, query_key = esearch_history(query)
    time.sleep(SLEEP_SEC)

    if count == 0:
        return

    if count <= MAX_PER_SEG:
        log.info(
            f"{indent}[{fmt(d)} PMID {pmid_lo}:{pmid_hi}] "
            f"{count:,} records → fetching…"
        )
        fetch_leaf(web_env, query_key, count, f"[{fmt(d)} PMID {pmid_lo}:{pmid_hi}]")

    elif pmid_lo == pmid_hi:
        # 单个 PMID 不可能有超过 1 条记录，理论上不会到达这里
        log.error(f"{indent}[{fmt(d)} PMID {pmid_lo}] unexpected count={count}, skipping.")

    else:
        mid = (pmid_lo + pmid_hi) // 2
        log.info(
            f"{indent}[{fmt(d)} PMID {pmid_lo}:{pmid_hi}] "
            f"{count:,} > {MAX_PER_SEG}, splitting at PMID {mid}"
        )
        fetch_by_pmid_range(d, pmid_lo, mid, depth + 1)
        fetch_by_pmid_range(d, mid + 1, pmid_hi, depth + 1)


# ─────────────────────────────────────────────
# 第一层递归：日期区间二分
# ─────────────────────────────────────────────
def fetch_range(d_from: date, d_to: date, depth: int = 0) -> None:
    indent = "  " * depth
    query  = build_query(d_from, d_to)
    count, web_env, query_key = esearch_history(query)
    time.sleep(SLEEP_SEC)

    if count == 0:
        log.info(f"{indent}[{fmt(d_from)} ~ {fmt(d_to)}] 0 records, skip.")
        return

    if count <= MAX_PER_SEG:
        # ① 叶子：直接 efetch
        log.info(f"{indent}[{fmt(d_from)} ~ {fmt(d_to)}] {count:,} records → fetching…")
        fetch_leaf(web_env, query_key, count, f"[{fmt(d_from)}~{fmt(d_to)}]")

    elif d_from == d_to:
        # ③ 单日超限 → PMID 范围二分
        log.warning(
            f"{indent}[{fmt(d_from)}] single day {count:,} > {MAX_PER_SEG}. "
            f"Switching to PMID-range bisection."
        )
        fetch_by_pmid_range(d_from, PMID_MIN, PMID_MAX, depth=0)

    else:
        # ② 日期对半，递归
        mid = mid_date(d_from, d_to)
        log.info(
            f"{indent}[{fmt(d_from)} ~ {fmt(d_to)}] {count:,} > {MAX_PER_SEG}, "
            f"splitting at {fmt(mid)} / {fmt(mid + timedelta(days=1))}"
        )
        fetch_range(d_from, mid, depth + 1)
        fetch_range(mid + timedelta(days=1), d_to, depth + 1)


# ─────────────────────────────────────────────
# XML 解析
# ─────────────────────────────────────────────
def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    records = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.error(f"XML parse error: {exc}")
        return records

    for article in root.findall(".//PubmedArticle"):

        # PMID
        pmid = _text(article.find(".//PMID"))
        if not pmid:
            continue

        # PMCID & DOI
        pmcid = doi = ""
        for aid in article.findall(".//ArticleIdList/ArticleId"):
            id_type = aid.get("IdType", "").lower()
            if id_type == "pmc":
                pmcid = (aid.text or "").strip()
            elif id_type == "doi":
                doi = (aid.text or "").strip()

        # Journal
        journal = _text(article.find(".//Journal/Title")) or \
                  _text(article.find(".//Journal/ISOAbbreviation"))

        # Publication Types
        # XML: <PublicationTypeList><PublicationType UI="...">Journal Article</PublicationType>...
        pub_types = [
            _text(pt)
            for pt in article.findall(".//PublicationTypeList/PublicationType")
            if _text(pt)
        ]
        publication_types = "; ".join(pub_types)

        # Date
        pub_date_el = article.find(".//Journal/JournalIssue/PubDate")
        if pub_date_el is not None:
            medline = _text(pub_date_el.find("MedlineDate"))
            if medline:
                date_str = medline
            else:
                parts = [
                    _text(pub_date_el.find("Year")),
                    _text(pub_date_el.find("Month")),
                    _text(pub_date_el.find("Day")),
                ]
                date_str = "-".join(p for p in parts if p)
        else:
            date_str = ""

        # Authors
        authors = []
        for au in article.findall(".//AuthorList/Author"):
            col = _text(au.find("CollectiveName"))
            if col:
                authors.append(col)
            else:
                last = _text(au.find("LastName"))
                fore = _text(au.find("ForeName")) or _text(au.find("Initials"))
                if last:
                    authors.append((last + " " + fore).strip())
        author = "; ".join(authors)

        # Title
        title = _text(article.find(".//ArticleTitle"))

        # Abstract
        abs_parts = []
        for abs_el in article.findall(".//AbstractText"):
            label = abs_el.get("Label")
            text  = "".join(abs_el.itertext()).strip()
            abs_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abs_parts).strip()

        records.append({
            "PMID":              pmid,
            "PMCID":             pmcid,
            "DOI":               doi,
            "Journal":           journal,
            "Publication_types": publication_types,
            "Date":              date_str,
            "Author":            author,
            "Title":             title,
            "Abstract":          abstract,
        })
    return records


# ─────────────────────────────────────────────
# 写 JSON
# ─────────────────────────────────────────────
def flush_buffer(force: bool = False) -> None:
    global _buffer, _file_index
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    while len(_buffer) >= SAVE_BATCH or (force and _buffer):
        chunk   = _buffer[:SAVE_BATCH]
        _buffer = _buffer[SAVE_BATCH:]
        path    = OUTPUT_DIR / f"pubmed_batch_{_file_index:04d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)
        log.info(f"→ Saved {len(chunk):,} records to {path}")
        _file_index += 1


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    log.info(f"Start: {fmt(GLOBAL_START)} ~ {fmt(GLOBAL_END)}")
    fetch_range(GLOBAL_START, GLOBAL_END)
    flush_buffer(force=True)
    log.info(
        f"Done. {_downloaded:,} records saved across "
        f"{_file_index - 1} file(s) in '{OUTPUT_DIR}/'."
    )


if __name__ == "__main__":
    main()
