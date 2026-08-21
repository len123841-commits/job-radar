#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable

SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SKILL_ROOT.parent.parent
DEFAULT_PROFILE = SKILL_ROOT / "assets" / "default_profile.yaml"
DEFAULT_BOSS_REPO = Path.home() / ".cache" / "job-radar" / "boss-zhipin-scraper"
UPSTREAM_BOSS_REPO = "https://github.com/eatmoreduck/boss-zhipin-scraper.git"
DEFAULT_OUTPUT_ROOT = Path.cwd() / "job-radar-output"
SUPPORTED_JOBSPY_SITES = {"linkedin", "indeed", "google", "zip_recruiter", "glassdoor"}
DEFAULT_SITES = ["linkedin", "indeed", "google", "boss"]
TIER_ORDER = ["tier_1_strong", "tier_2_potential", "tier_3_extended"]
TIER_LABELS = {
    "tier_1_strong": "Tier 1 强相关",
    "tier_2_potential": "Tier 2 可尝试",
    "tier_3_extended": "Tier 3 延展",
    "unclassified": "未分层",
}
PRIORITY_RANK = {"强推": 0, "可投": 1, "备选": 2}
PRIORITY_LABELS = ["强推", "可投", "备选"]
RESUME_PATTERNS = [
    "*简历*.html",
    "*简历*.pdf",
    "*简历*.docx",
    "*简历*.md",
    "*简历*.txt",
    "*resume*.html",
    "*resume*.pdf",
    "*resume*.docx",
    "*resume*.md",
    "*resume*.txt",
]
DEFAULT_HIGHLIGHTS = [
    "TikTok Gaming LIVE 海外运营",
    "UK/FR/DE/AU 多区域 Campaign 交付",
    "DE 活动增量 $130k→$320k，ROI +12pct",
    "站内信触达链路 0→1，累计触达近 50 万主播",
    "AI 违规初筛 Precision 95%、Recall 100%",
]


@dataclass
class SearchProfile:
    name: str
    search_terms: list[str] = field(default_factory=list)
    score_keywords: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    remote_ok: bool = True
    min_monthly_salary_k: float | None = None
    max_monthly_salary_k: float | None = None
    platforms: list[str] = field(default_factory=lambda: DEFAULT_SITES.copy())
    jobspy_results_per_search: int = 20
    boss_pages_per_keyword_city: int = 1
    hours_old: int = 168
    top_n: int = 50
    note: str = ""
    highlights: list[str] = field(default_factory=lambda: DEFAULT_HIGHLIGHTS.copy())
    direction_pool: dict[str, list[str]] = field(default_factory=dict)
    resume_path: str = ""
    resume_name: str = ""
    resume_keywords: list[str] = field(default_factory=list)
    resume_highlights: list[str] = field(default_factory=list)


class SkillError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(value)
    return ordered


def ensure_yaml_module():
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - user-facing guard
        raise SkillError("缺少 PyYAML。请先运行 `python3 scripts/ensure_deps.py` 安装运行依赖。") from exc
    return yaml


def normalize_tier_mapping(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            normalized[str(key)] = dedupe_keep_order(value)
        elif isinstance(value, str):
            normalized[str(key)] = [value.strip()] if value.strip() else []
    return normalized


def flatten_tier_mapping(mapping: dict[str, list[str]]) -> list[str]:
    flattened: list[str] = []
    for tier_key in TIER_ORDER:
        flattened.extend(mapping.get(tier_key, []))
    for tier_key, values in mapping.items():
        if tier_key not in TIER_ORDER:
            flattened.extend(values)
    return dedupe_keep_order(flattened)


def candidate_resume_dirs(profile_path: Path) -> list[Path]:
    profile_dir = profile_path.parent
    dirs = [WORKSPACE_ROOT, profile_dir, SKILL_ROOT / "assets", Path.cwd()]
    existing: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        resolved = str(directory.resolve())
        if resolved in seen or not directory.exists():
            continue
        seen.add(resolved)
        existing.append(directory)
    return existing


def find_latest_resume_file(profile_path: Path, explicit_resume_path: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_resume_path and explicit_resume_path.exists():
        candidates.append(explicit_resume_path)
    for directory in candidate_resume_dirs(profile_path):
        for pattern in RESUME_PATTERNS:
            candidates.extend([path for path in directory.glob(pattern) if path.is_file()])
    if not candidates:
        return None
    unique: dict[str, Path] = {}
    for path in candidates:
        unique[str(path.resolve())] = path
    return max(unique.values(), key=lambda item: item.stat().st_mtime)


def extract_text_from_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"<\s*br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</(p|div|li|section|h[1-6]|tr)>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return normalize_resume_text(unescape(raw))


def extract_text_from_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", " ", xml)
    return normalize_resume_text(unescape(xml))


def extract_text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        parts = [page.extract_text() or "" for page in reader.pages[:8]]
        return normalize_resume_text("\n".join(parts))
    except Exception:
        return ""


def load_resume_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return extract_text_from_html(path)
    if suffix in {".md", ".txt"}:
        return normalize_resume_text(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    return ""


def normalize_resume_text(text: str) -> str:
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\u00a0", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_resume_highlights(text: str, fallback: list[str]) -> list[str]:
    lines = [line.strip(" -•·") for line in text.splitlines()]
    selected: list[str] = []
    positive_markers = [
        "tiktok",
        "campaign",
        "creator",
        "global",
        "ai",
        "precision",
        "recall",
        "roi",
        "海外",
        "运营",
        "增长",
        "主播",
        "触达",
        "字节",
    ]
    blocked_markers = ["a4", "导出", "照片", "base64", "contenteditable", "qq.com", "@", "(+86)", "microsoft", "pdf"]
    for line in lines:
        lowered = line.lower()
        if len(line) < 12 or len(line) > 180:
            continue
        if any(marker in lowered for marker in blocked_markers):
            continue
        if any(marker in lowered for marker in positive_markers):
            selected.append(line)
    highlights = dedupe_keep_order(selected)[:6]
    if highlights:
        return highlights

    backup: list[str] = []
    for line in lines:
        lowered = line.lower()
        if len(line) < 12 or len(line) > 180:
            continue
        if any(marker in lowered for marker in blocked_markers):
            continue
        if re.search(r"\d", line):
            backup.append(line)
    return dedupe_keep_order(backup)[:5] or fallback[:5]


def extract_resume_keywords(text: str, profile: SearchProfile) -> list[str]:
    candidate_terms = dedupe_keep_order(
        profile.search_terms + profile.score_keywords + flatten_tier_mapping(profile.direction_pool) + DEFAULT_HIGHLIGHTS
    )
    haystack = f" {text.lower()} "
    hits = [term for term in candidate_terms if term and term.lower() in haystack]
    return dedupe_keep_order(hits)[:12]


def hydrate_profile_with_resume(profile: SearchProfile, profile_path: Path, explicit_resume_path: Path | None = None) -> SearchProfile:
    resume_path = find_latest_resume_file(profile_path, explicit_resume_path)
    if not resume_path:
        return profile
    resume_text = load_resume_text(resume_path)
    if not resume_text:
        profile.resume_path = str(resume_path)
        profile.resume_name = resume_path.name
        return profile
    profile.resume_path = str(resume_path)
    profile.resume_name = resume_path.name
    profile.resume_highlights = extract_resume_highlights(resume_text, profile.highlights)
    profile.highlights = dedupe_keep_order(profile.resume_highlights + profile.highlights)
    profile.resume_keywords = extract_resume_keywords(resume_text, profile)
    profile.score_keywords = dedupe_keep_order(profile.resume_keywords + profile.score_keywords)
    return profile


def load_profile(profile_path: Path, explicit_resume_path: Path | None = None) -> SearchProfile:
    yaml = ensure_yaml_module()
    if not profile_path.exists():
        raise SkillError(f"未找到配置文件：{profile_path}")
    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    candidate = raw.get("candidate", {})
    search = raw.get("search", {})
    output = raw.get("output", {})

    profile = SearchProfile(
        name=str(candidate.get("name") or "candidate").strip() or "candidate",
        search_terms=dedupe_keep_order(candidate.get("search_terms", [])),
        score_keywords=dedupe_keep_order(candidate.get("score_keywords", [])),
        cities=dedupe_keep_order(search.get("cities", [])),
        remote_ok=bool(search.get("remote_ok", True)),
        min_monthly_salary_k=_to_float(search.get("min_monthly_salary_k")),
        max_monthly_salary_k=_to_float(search.get("max_monthly_salary_k")),
        platforms=dedupe_keep_order(search.get("platforms", DEFAULT_SITES)),
        jobspy_results_per_search=int(search.get("jobspy_results_per_search", 20)),
        boss_pages_per_keyword_city=int(search.get("boss_pages_per_keyword_city", 1)),
        hours_old=int(search.get("hours_old", 168)),
        top_n=int(output.get("top_n", 50)),
        note=str(candidate.get("note") or "").strip(),
        highlights=dedupe_keep_order(candidate.get("highlights", DEFAULT_HIGHLIGHTS)),
        direction_pool=normalize_tier_mapping(candidate.get("direction_pool", {})),
    )
    if not profile.search_terms:
        raise SkillError("配置文件缺少 candidate.search_terms，至少提供一个搜索词。")
    if not profile.cities:
        raise SkillError("配置文件缺少 search.cities，至少提供一个城市或 remote。")
    if not profile.platforms:
        profile.platforms = DEFAULT_SITES.copy()
    if not profile.highlights:
        profile.highlights = DEFAULT_HIGHLIGHTS.copy()
    return hydrate_profile_with_resume(profile, profile_path, explicit_resume_path)


def apply_overrides(profile: SearchProfile, args: argparse.Namespace) -> SearchProfile:
    if args.keywords:
        profile.search_terms = dedupe_keep_order(split_csv_arg(args.keywords))
    if args.score_keywords:
        profile.score_keywords = dedupe_keep_order(split_csv_arg(args.score_keywords))
    if args.cities:
        profile.cities = dedupe_keep_order(split_csv_arg(args.cities))
    if args.sites:
        profile.platforms = dedupe_keep_order(split_csv_arg(args.sites))
    if args.min_salary_k is not None:
        profile.min_monthly_salary_k = float(args.min_salary_k)
    if args.max_salary_k is not None:
        profile.max_monthly_salary_k = float(args.max_salary_k)
    if args.hours_old is not None:
        profile.hours_old = int(args.hours_old)
    if args.results_per_search is not None:
        profile.jobspy_results_per_search = int(args.results_per_search)
    if args.boss_pages is not None:
        profile.boss_pages_per_keyword_city = int(args.boss_pages)
    if args.top_n is not None:
        profile.top_n = int(args.top_n)
    if args.remote_only:
        profile.remote_ok = True
        profile.cities = ["remote"]
    return profile


def split_csv_arg(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_search_plan(profile: SearchProfile) -> dict[str, Any]:
    cities = dedupe_keep_order(
        profile.cities + (["remote"] if profile.remote_ok and "remote" not in {c.lower() for c in profile.cities} else [])
    )
    sites = dedupe_keep_order(profile.platforms)
    jobspy_sites = [site for site in sites if site in SUPPORTED_JOBSPY_SITES]
    boss_enabled = "boss" in {site.lower() for site in sites}
    return {
        "profile_name": profile.name,
        "resume_name": profile.resume_name,
        "resume_path": profile.resume_path,
        "resume_keywords": profile.resume_keywords,
        "resume_highlights": profile.resume_highlights,
        "search_terms": profile.search_terms,
        "score_keywords": profile.score_keywords,
        "cities": cities,
        "platforms": sites,
        "jobspy_sites": jobspy_sites,
        "boss_enabled": boss_enabled,
        "jobspy_results_per_search": profile.jobspy_results_per_search,
        "boss_pages_per_keyword_city": profile.boss_pages_per_keyword_city,
        "hours_old": profile.hours_old,
        "min_monthly_salary_k": profile.min_monthly_salary_k,
        "max_monthly_salary_k": profile.max_monthly_salary_k,
        "direction_tier_sizes": {key: len(value) for key, value in profile.direction_pool.items()},
    }


def search_jobspy(profile: SearchProfile, plan: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    if not plan["jobspy_sites"]:
        return []
    try:
        from jobspy import scrape_jobs  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SkillError("缺少 python-jobspy。请先运行 `python3 scripts/ensure_deps.py` 安装依赖。") from exc

    results: list[dict[str, Any]] = []
    search_cities = [city for city in plan["cities"] if city.lower() != "remote"] or ["Remote"]
    if profile.remote_ok and "remote" in {city.lower() for city in plan["cities"]}:
        search_cities = dedupe_keep_order(search_cities + ["Remote"])

    for term in profile.search_terms:
        for city in search_cities:
            try:
                kwargs: dict[str, Any] = {
                    "site_name": plan["jobspy_sites"],
                    "search_term": term,
                    "location": city,
                    "results_wanted": profile.jobspy_results_per_search,
                    "hours_old": profile.hours_old,
                    "description_format": "markdown",
                    "linkedin_fetch_description": True,
                }
                if "google" in plan["jobspy_sites"]:
                    kwargs["google_search_term"] = f"{term} jobs in {city} since yesterday"
                jobs_df = scrape_jobs(**kwargs)
                rows = jobs_df.to_dict(orient="records") if hasattr(jobs_df, "to_dict") else []
            except Exception as exc:  # pragma: no cover
                warnings.append(f"JobSpy 抓取失败：关键词={term}，城市={city}，原因={exc}")
                continue
            for row in rows:
                standardized = standardize_jobspy_row(row, term, city, profile)
                if standardized:
                    results.append(standardized)
    return results


def standardize_jobspy_row(row: dict[str, Any], search_term: str, search_city: str, profile: SearchProfile) -> dict[str, Any] | None:
    title = clean_text(row.get("title"))
    company = clean_text(row.get("company"))
    url = clean_text(row.get("job_url")) or clean_text(row.get("job_url_direct"))
    if not title or not company or not url:
        return None
    city = clean_text(row.get("city"))
    state = clean_text(row.get("state"))
    location = ", ".join([part for part in [city, state] if part]) or clean_text(row.get("location")) or search_city
    description = clean_text(row.get("description"))
    interval = clean_text(row.get("interval"))
    min_amount = _to_float(row.get("min_amount"))
    max_amount = _to_float(row.get("max_amount"))
    min_monthly_k, max_monthly_k = convert_salary_to_monthly_k(min_amount, max_amount, interval)
    salary_display = format_salary_display(min_amount, max_amount, interval, row.get("currency"))
    base_job = {
        "source": clean_text(row.get("site")) or clean_text(row.get("site_name")) or "jobspy",
        "company": company,
        "title": title,
        "location": location,
        "salary_display": salary_display,
        "salary_min_monthly_k": min_monthly_k,
        "salary_max_monthly_k": max_monthly_k,
        "remote": bool(row.get("is_remote")) or "remote" in location.lower(),
        "jd_summary": summarize_text(description),
        "description": description,
        "apply_url": url,
        "search_term": search_term,
        "search_city": search_city,
        "published_at": pick_first_text(
            row,
            ["date_posted_human_readable", "date_posted", "date", "posted_at", "listed_at", "job_posted_at_datetime_utc"],
        ),
        "deadline": pick_first_text(row, ["deadline", "valid_through", "date_closing", "expire_at"]),
        "collected_at": utc_now_iso(),
    }
    return decorate_job(base_job, profile)


def search_boss(
    profile: SearchProfile,
    plan: dict[str, Any],
    warnings: list[str],
    repo_path: Path,
    bootstrap_boss: bool,
    output_dir: Path,
) -> list[dict[str, Any]]:
    if not plan["boss_enabled"]:
        return []

    repo_path = ensure_boss_repo(repo_path, bootstrap_boss)
    if not repo_path.exists():
        warnings.append(
            "未找到 boss-zhipin-scraper。请先运行 `python3 scripts/ensure_deps.py --with-boss`，或在命令中传 `--boss-repo-path`。"
        )
        return []

    script_path = repo_path / "scripts" / "boss_cdp_raw.py"
    if not script_path.exists():
        warnings.append(f"boss-zhipin-scraper 缺少脚本：{script_path}")
        return []

    raw_results: list[dict[str, Any]] = []
    boss_output_dir = output_dir / "boss-raw"
    boss_output_dir.mkdir(parents=True, exist_ok=True)
    search_cities = [city for city in plan["cities"] if city.lower() != "remote"]
    if not search_cities:
        warnings.append("BOSS 直聘不支持 remote-only 抓取，已跳过 BOSS 平台。")
        return []

    for term in profile.search_terms:
        for city in search_cities:
            safe_term = re.sub(r"[^\w\u4e00-\u9fff]+", "_", term).strip("_") or "keyword"
            safe_city = re.sub(r"[^\w\u4e00-\u9fff]+", "_", city).strip("_") or "city"
            jobs_file = boss_output_dir / f"boss_jobs_{safe_term}_{safe_city}.json"
            details_file = boss_output_dir / f"boss_details_{safe_term}_{safe_city}.json"
            if jobs_file.exists():
                jobs_file.unlink()
            if details_file.exists():
                details_file.unlink()
            cmd = [
                sys.executable,
                str(script_path),
                "--keyword",
                term,
                "--city",
                city,
                "--pages",
                str(profile.boss_pages_per_keyword_city),
                "--format",
                "json",
                "--output",
                str(jobs_file),
                "--detail-output",
                str(details_file),
            ]
            try:
                subprocess.run(cmd, check=True, cwd=str(repo_path))
            except subprocess.CalledProcessError as exc:  # pragma: no cover
                warnings.append(
                    f"BOSS 抓取失败：关键词={term}，城市={city}。常见原因是未准备本地登录态或当前环境无法访问 Chrome。原始错误：{exc}"
                )
                continue
            if not jobs_file.exists():
                jobs_file = latest_file(boss_output_dir, f"boss_jobs_{safe_term}_{safe_city}.json")
            if not details_file.exists():
                details_file = latest_file(boss_output_dir, f"boss_details_{safe_term}_{safe_city}.json")
            if not jobs_file:
                warnings.append(f"BOSS 抓取已执行但未发现输出文件：关键词={term}，城市={city}")
                continue
            raw_results.extend(load_boss_results(jobs_file, details_file, term, city, profile))
    return raw_results


def ensure_boss_repo(repo_path: Path, bootstrap_boss: bool) -> Path:
    if repo_path.exists():
        return repo_path
    if not bootstrap_boss:
        return repo_path
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", UPSTREAM_BOSS_REPO, str(repo_path)], check=True)
    return repo_path


def latest_file(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def load_boss_results(
    jobs_file: Path,
    details_file: Path | None,
    search_term: str,
    search_city: str,
    profile: SearchProfile,
) -> list[dict[str, Any]]:
    jobs_raw = json.loads(jobs_file.read_text(encoding="utf-8"))
    details_raw = json.loads(details_file.read_text(encoding="utf-8")) if details_file and details_file.exists() else []
    jobs_list = jobs_raw.get("jobs", []) if isinstance(jobs_raw, dict) else (jobs_raw if isinstance(jobs_raw, list) else [])
    details_by_id: dict[str, dict[str, Any]] = {}
    for detail in details_raw if isinstance(details_raw, list) else []:
        detail_id = str(detail.get("job_id") or detail.get("securityId") or detail.get("encryptId") or "").strip()
        if detail_id:
            details_by_id[detail_id] = detail

    standardized: list[dict[str, Any]] = []
    for raw in jobs_list:
        job_id = str(raw.get("job_id") or raw.get("securityId") or raw.get("encryptId") or "").strip()
        detail = details_by_id.get(job_id, {})
        title = (
            clean_text(raw.get("job_name"))
            or clean_text(raw.get("title"))
            or clean_text(raw.get("jobTitle"))
            or clean_text(detail.get("title"))
        )
        company = (
            clean_text(raw.get("brand_name"))
            or clean_text(raw.get("boss_name"))
            or clean_text(raw.get("company_name"))
            or clean_text(raw.get("company"))
            or clean_text(detail.get("company"))
        )
        url = (
            clean_text(raw.get("job_url"))
            or clean_text(raw.get("url"))
            or clean_text(raw.get("job_link"))
            or clean_text(detail.get("job_url"))
            or clean_text(detail.get("job_link"))
            or clean_text(detail.get("link"))
        )
        if not title or not company or not url:
            continue
        description = (
            clean_text(detail.get("job_desc"))
            or clean_text(detail.get("job_description"))
            or clean_text(detail.get("jd"))
            or clean_text(raw.get("job_desc"))
        )
        location = (
            clean_text(raw.get("city_name"))
            or clean_text(raw.get("city"))
            or clean_text(raw.get("location"))
            or clean_text(raw.get("job_area"))
            or clean_text(detail.get("location"))
            or search_city
        )
        salary_display = (
            clean_text(raw.get("salary_desc"))
            or clean_text(raw.get("salary"))
            or clean_text(raw.get("salaryDesc"))
            or clean_text(detail.get("salary"))
        )
        min_monthly_k, max_monthly_k = parse_boss_salary_monthly_k(salary_display)
        base_job = {
            "source": "boss",
            "company": company,
            "title": title,
            "location": location,
            "salary_display": salary_display,
            "salary_min_monthly_k": min_monthly_k,
            "salary_max_monthly_k": max_monthly_k,
            "remote": "remote" in location.lower(),
            "jd_summary": summarize_text(description),
            "description": description,
            "apply_url": url,
            "search_term": search_term,
            "search_city": search_city,
            "published_at": pick_first_text(
                raw,
                ["active_time_desc", "time_desc", "publish_time", "post_time", "更新时间", "job_valid_status", "boss_active_status"],
            ) or pick_first_text(detail, ["boss_active_status"]),
            "deadline": pick_first_text(raw, ["deadline", "end_time", "expire_time"]),
            "collected_at": utc_now_iso(),
        }
        standardized.append(decorate_job(base_job, profile))
    return standardized


def decorate_job(base_job: dict[str, Any], profile: SearchProfile) -> dict[str, Any]:
    title = clean_text(base_job.get("title"))
    description = clean_text(base_job.get("description"))
    location = clean_text(base_job.get("location"))
    direction_tier_key, direction_hits = detect_direction_tier(title, description, profile.direction_pool)
    matched_keywords = extract_matched_keywords(title, description, profile.score_keywords or profile.search_terms)
    score = score_job(
        title=title,
        description=description,
        profile=profile,
        min_monthly_k=_to_float(base_job.get("salary_min_monthly_k")),
        max_monthly_k=_to_float(base_job.get("salary_max_monthly_k")),
        remote_flag=bool(base_job.get("remote")),
        direction_tier_key=direction_tier_key,
        matched_keywords=matched_keywords,
    )
    apply_priority = classify_apply_priority(direction_tier_key, score)
    location_hit = detect_location_hit(location, profile)
    match_reason = build_match_reason(base_job, direction_tier_key, direction_hits, matched_keywords, location_hit, profile)
    outreach_message = build_outreach_message(base_job, direction_tier_key, direction_hits, matched_keywords, profile)
    suggested_channel = build_suggested_channel(base_job, direction_tier_key, apply_priority)
    decorated = {
        **base_job,
        "matched_keywords": matched_keywords,
        "direction_tier": TIER_LABELS.get(direction_tier_key, TIER_LABELS["unclassified"]),
        "direction_tier_key": direction_tier_key,
        "direction_tier_rank": tier_rank(direction_tier_key),
        "direction_hits": direction_hits,
        "score": score,
        "apply_priority": apply_priority,
        "location_hit": location_hit,
        "match_reason": match_reason,
        "suggested_channel": suggested_channel,
        "quick_apply_note": build_quick_apply_note(base_job, apply_priority, suggested_channel, direction_hits, matched_keywords),
        "cover_letter_hint": build_cover_letter_hint(title, description, direction_tier_key, matched_keywords),
        "outreach_message": outreach_message,
        "english_outreach_opener": build_english_outreach_opener(base_job, direction_tier_key, direction_hits, matched_keywords, profile),
    }
    return decorated


def filter_jobs(jobs: list[dict[str, Any]], profile: SearchProfile) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    allowed_cities = {city.lower() for city in profile.cities}
    if profile.remote_ok:
        allowed_cities.add("remote")

    for job in jobs:
        location = str(job.get("location") or "").lower()
        if allowed_cities and not any(city in location for city in allowed_cities if city != "remote"):
            if not (profile.remote_ok and (job.get("remote") or "remote" in location)):
                continue
        if not salary_in_range(job.get("salary_min_monthly_k"), job.get("salary_max_monthly_k"), profile):
            continue
        key = clean_text(job.get("apply_url")) or "|".join(
            [str(job.get("source")), str(job.get("company")), str(job.get("title")), str(job.get("location"))]
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        filtered.append(job)

    filtered.sort(
        key=lambda item: (
            item.get("direction_tier_rank", 99),
            PRIORITY_RANK.get(item.get("apply_priority", "备选"), 99),
            -int(item.get("score", 0)),
        )
    )
    return filtered


def salary_in_range(min_value: Any, max_value: Any, profile: SearchProfile) -> bool:
    min_salary = _to_float(min_value)
    max_salary = _to_float(max_value)
    if profile.min_monthly_salary_k is None and profile.max_monthly_salary_k is None:
        return True
    if min_salary is None and max_salary is None:
        return True
    low = min_salary if min_salary is not None else max_salary
    high = max_salary if max_salary is not None else min_salary
    if profile.max_monthly_salary_k is not None and low is not None and low > profile.max_monthly_salary_k:
        return False
    if profile.min_monthly_salary_k is not None and high is not None and high < profile.min_monthly_salary_k:
        return False
    return True


def detect_direction_tier(title: str, description: str, direction_pool: dict[str, list[str]]) -> tuple[str, list[str]]:
    haystack = f" {title.lower()} {description.lower()} "
    for tier_key in TIER_ORDER:
        terms = direction_pool.get(tier_key, [])
        hits = [term for term in terms if term and term.lower() in haystack]
        if hits:
            return tier_key, dedupe_keep_order(hits)[:3]
    return "unclassified", []


def tier_rank(direction_tier_key: str) -> int:
    if direction_tier_key in TIER_ORDER:
        return TIER_ORDER.index(direction_tier_key)
    return len(TIER_ORDER)


def score_job(
    title: str,
    description: str,
    profile: SearchProfile,
    min_monthly_k: float | None,
    max_monthly_k: float | None,
    remote_flag: bool,
    direction_tier_key: str,
    matched_keywords: list[str],
) -> int:
    score = 30
    haystack_title = f" {title.lower()} "
    haystack_desc = f" {description.lower()} "
    tier_bonus = {"tier_1_strong": 28, "tier_2_potential": 16, "tier_3_extended": 8}.get(direction_tier_key, 0)
    score += tier_bonus

    for keyword in matched_keywords[:6]:
        lowered = keyword.lower().strip()
        if lowered in haystack_title:
            score += 8
        elif lowered in haystack_desc:
            score += 4
    if remote_flag and profile.remote_ok:
        score += 4
    if salary_in_range(min_monthly_k, max_monthly_k, profile):
        score += 6
    return max(0, min(100, score))


def classify_apply_priority(direction_tier_key: str, score: int) -> str:
    if direction_tier_key == "tier_1_strong" and score >= 75:
        return "强推"
    if direction_tier_key in {"tier_1_strong", "tier_2_potential"} or score >= 58:
        return "可投"
    return "备选"


def detect_location_hit(location: str, profile: SearchProfile) -> str:
    lowered = location.lower()
    if profile.remote_ok and "remote" in lowered:
        return "remote"
    for city in profile.cities:
        if city.lower() != "remote" and city.lower() in lowered:
            return city
    return ""


def build_match_reason(
    job: dict[str, Any],
    direction_tier_key: str,
    direction_hits: list[str],
    matched_keywords: list[str],
    location_hit: str,
    profile: SearchProfile,
) -> str:
    reasons: list[str] = [TIER_LABELS.get(direction_tier_key, TIER_LABELS["unclassified"])]
    if direction_hits:
        reasons.append("命中方向：" + " / ".join(direction_hits[:2]))
    if matched_keywords:
        reasons.append("命中关键词：" + " / ".join(matched_keywords[:3]))
    if location_hit:
        reasons.append(f"地点匹配：{location_hit}")
    if salary_in_range(job.get("salary_min_monthly_k"), job.get("salary_max_monthly_k"), profile):
        reasons.append("薪资落在预期区间")
    return "；".join(reasons)


def build_suggested_channel(job: dict[str, Any], direction_tier_key: str, apply_priority: str) -> str:
    source = clean_text(job.get("source")).lower()
    title = clean_text(job.get("title")).lower()
    if source == "boss":
        return "找 HR"
    if apply_priority == "强推" and direction_tier_key == "tier_1_strong":
        return "先内推"
    if source == "linkedin" or any(token in title for token in ["manager", "lead", "global", "campaign"]):
        return "找 HR"
    return "直投"


def build_quick_apply_note(
    job: dict[str, Any], apply_priority: str, suggested_channel: str, direction_hits: list[str], matched_keywords: list[str]
) -> str:
    focus = "/".join(direction_hits[:2]) if direction_hits else (matched_keywords[0] if matched_keywords else "岗位方向")
    company = clean_text(job.get("company")) or "目标公司"
    if suggested_channel == "先内推":
        return f"先找内推，主打 {focus} 经验，再补中文打招呼语。"
    if suggested_channel == "找 HR":
        return f"先加 {company} HR，发中文打招呼语，附英文首句备用。"
    if apply_priority == "强推":
        return f"优先直投，投完立刻补一句与 {focus} 相关的亮点。"
    return f"可先直投，备注突出 {focus} 与当前简历经验匹配。"


def build_cover_letter_hint(title: str, description: str, direction_tier_key: str, matched_keywords: list[str]) -> str:
    haystack = f" {title.lower()} {description.lower()} "
    if any(token in haystack for token in ["cover letter", "motivation letter", "writing sample"]):
        return "JD 已明确提到 cover letter / writing sample，建议准备英文版。"
    if any(token in haystack for token in ["global", "campaign", "marketing", "partnership"]):
        return "建议准备 3-5 句英文 cover letter，突出多区域 campaign 与 ROI 提升成果。"
    if any(token in haystack for token in ["ai", "automation", "efficiency"]):
        return "建议准备 2-3 句项目摘要，突出 AI 提效与 Precision 95% / Recall 100%。"
    if direction_tier_key == "tier_1_strong":
        return "可先直接投递或直聊 HR，如对方追问再补充简短说明。"
    return "可先直投；若岗位偏 marketing / strategy，再补一版简短 cover letter。"


def build_outreach_message(
    job: dict[str, Any],
    direction_tier_key: str,
    direction_hits: list[str],
    matched_keywords: list[str],
    profile: SearchProfile,
) -> str:
    title = clean_text(job.get("title"))
    description = clean_text(job.get("description"))
    haystack = f" {title.lower()} {description.lower()} "
    focus_text = "/".join(direction_hits[:2]) if direction_hits else (matched_keywords[0] if matched_keywords else "运营")

    if any(token in haystack for token in ["creator", "live", "livestream", "主播", "达人", "tiktok"]):
        return (
            "你好，我目前在字节负责 TikTok Gaming LIVE 海外运营，长期做 Creator 增长和直播运营，也搭过站内信触达链路，累计触达近 50 万主播；"
            f"看到这个岗位和我在 {focus_text} 的实操经验很贴合，想进一步沟通。"
        )
    if any(token in haystack for token in ["campaign", "global", "marketing", "international", "海外"]):
        return (
            "你好，我目前在字节负责 TikTok Gaming LIVE 海外运营，做过 UK/FR/DE/AU 多区域 Campaign 交付，其中德国活动增量从 $130k 提升到 $320k、ROI 提升 12pct；"
            f"看到这个岗位和我在 {focus_text} 上的经验很匹配，想进一步沟通。"
        )
    if any(token in haystack for token in ["ai", "automation", "efficiency", "智能", "提效"]):
        return (
            "你好，我目前在字节做 TikTok Gaming LIVE 海外运营，也主导过 AI 运营提效项目，曾将违规初筛做到 Precision 95%、Recall 100%；"
            f"看到这个岗位和我在 {focus_text} 的经验很匹配，想进一步沟通。"
        )
    if any(token in haystack for token in ["growth", "content", "user growth", "community"]):
        return (
            "你好，我目前在字节负责 TikTok Gaming LIVE 海外运营，做过 Creator 增长和用户触达链路 0→1，累计触达近 50 万主播；"
            f"看到这个岗位和我在 {focus_text} 的增长运营经验很贴合，想进一步沟通。"
        )
    highlight = profile.highlights[0] if profile.highlights else "TikTok Gaming LIVE 海外运营"
    return f"你好，我目前在字节负责 {highlight}，也做过多区域 campaign、增长和 AI 提效项目；看到这个岗位和我在 {focus_text} 的经验较匹配，想进一步沟通。"


def build_english_outreach_opener(
    job: dict[str, Any],
    direction_tier_key: str,
    direction_hits: list[str],
    matched_keywords: list[str],
    profile: SearchProfile,
) -> str:
    title = clean_text(job.get("title"))
    description = clean_text(job.get("description"))
    haystack = f" {title.lower()} {description.lower()} "
    focus_text = "/".join(direction_hits[:2]) if direction_hits else (matched_keywords[0] if matched_keywords else "operations")
    if any(token in haystack for token in ["creator", "live", "livestream", "tiktok"]):
        return (
            "Hi, I’m currently leading TikTok Gaming LIVE overseas operations at ByteDance, with hands-on experience in creator growth and livestream operations,"
            f" and I believe my background in {focus_text} would be highly relevant to this role."
        )
    if any(token in haystack for token in ["campaign", "global", "marketing", "international"]):
        return (
            "Hi, I’m currently working on TikTok Gaming LIVE overseas operations at ByteDance and have led multi-market campaigns across the UK, FR, DE and AU,"
            f" so I believe my experience in {focus_text} would translate well to this role."
        )
    if any(token in haystack for token in ["ai", "automation", "efficiency"]):
        return (
            "Hi, I’m currently driving overseas operations for TikTok Gaming LIVE at ByteDance and have also led AI efficiency projects,"
            f" so I believe my background in {focus_text} would be a strong fit for this position."
        )
    primary_highlight = profile.highlights[0] if profile.highlights else "TikTok Gaming LIVE overseas operations"
    return (
        f"Hi, I’m currently working on {primary_highlight} at ByteDance, and I believe my experience in {focus_text} would be relevant to this role."
    )


def convert_salary_to_monthly_k(
    min_amount: float | None, max_amount: float | None, interval: str | None
) -> tuple[float | None, float | None]:
    if min_amount is None and max_amount is None:
        return None, None
    normalized_interval = (interval or "").strip().lower()
    if normalized_interval == "yearly":
        factor = 1 / 12 / 1000
    elif normalized_interval == "monthly":
        factor = 1 / 1000
    else:
        return None, None
    return (
        round(min_amount * factor, 2) if min_amount is not None else None,
        round(max_amount * factor, 2) if max_amount is not None else None,
    )


def parse_boss_salary_monthly_k(text: str) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    match = re.search(r"(?P<low>\d+(?:\.\d+)?)\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)\s*[Kk]", text)
    if match:
        return float(match.group("low")), float(match.group("high"))
    match = re.search(r"(?P<single>\d+(?:\.\d+)?)\s*[Kk]", text)
    if match:
        value = float(match.group("single"))
        return value, value
    return None, None


def format_salary_display(
    min_amount: float | None,
    max_amount: float | None,
    interval: str | None,
    currency: Any,
) -> str:
    if min_amount is None and max_amount is None:
        return "未知"
    currency_text = clean_text(currency) or ""
    if min_amount is not None and max_amount is not None:
        amount_text = f"{min_amount:g}-{max_amount:g}"
    else:
        amount = min_amount if min_amount is not None else max_amount
        amount_text = f"{amount:g}"
    suffix = f"/{interval}" if interval else ""
    return f"{currency_text}{amount_text}{suffix}".strip() or "未知"


def summarize_text(text: str, max_chars: int = 140) -> str:
    normalized = re.sub(r"\s+", " ", clean_text(text))
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def extract_matched_keywords(title: str, description: str, keywords: list[str]) -> list[str]:
    haystack = f" {title.lower()} {description.lower()} "
    matched: list[str] = []
    for keyword in keywords:
        candidate = keyword.strip()
        if candidate and candidate.lower() in haystack:
            matched.append(candidate)
    return dedupe_keep_order(matched)


def pick_first_text(record: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = record.get(key)
        text = clean_text(value)
        if text:
            return text
    return ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return re.sub(r"\s+", " ", text).strip()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def write_outputs(
    output_dir: Path,
    plan: dict[str, Any],
    filtered_jobs: list[dict[str, Any]],
    raw_jobs: list[dict[str, Any]],
    warnings: list[str],
    profile: SearchProfile,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "generated_at": utc_now_iso(),
        "profile": {
            "name": profile.name,
            "resume_name": profile.resume_name,
            "resume_path": profile.resume_path,
            "resume_keywords": profile.resume_keywords,
            "resume_highlights": profile.resume_highlights,
            "search_terms": profile.search_terms,
            "score_keywords": profile.score_keywords,
            "cities": profile.cities,
            "remote_ok": profile.remote_ok,
            "platforms": profile.platforms,
            "min_monthly_salary_k": profile.min_monthly_salary_k,
            "max_monthly_salary_k": profile.max_monthly_salary_k,
            "note": profile.note,
            "highlights": profile.highlights,
            "direction_pool": profile.direction_pool,
        },
        "plan": plan,
        "warnings": warnings,
        "raw_count": len(raw_jobs),
        "filtered_count": len(filtered_jobs),
        "jobs": filtered_jobs,
    }
    json_path = output_dir / f"job_radar_{timestamp}.json"
    md_path = output_dir / f"job_radar_{timestamp}.md"
    csv_path = output_dir / f"job_radar_{timestamp}.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload, profile), encoding="utf-8")
    write_csv(csv_path, filtered_jobs)
    return {"json": json_path, "markdown": md_path, "csv": csv_path}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "apply_priority",
        "direction_tier",
        "source",
        "title",
        "company",
        "apply_url",
        "location",
        "salary_display",
        "published_at",
        "quick_apply_note",
        "outreach_message",
        "english_outreach_opener",
        "cover_letter_hint",
        "jd_summary",
        "search_term",
        "search_city",
        "collected_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def render_markdown(payload: dict[str, Any], profile: SearchProfile) -> str:
    lines: list[str] = []
    lines.append(f"# 求职抓岗日报：{profile.name}")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(f"- 生成时间：{payload['generated_at']}")
    lines.append(f"- 搜索词：{', '.join(profile.search_terms)}")
    lines.append(f"- 城市：{', '.join(profile.cities)}")
    lines.append(f"- 平台：{', '.join(profile.platforms)}")
    if profile.resume_name:
        lines.append(f"- 本次使用简历：{profile.resume_name}")
    lines.append(f"- 原始岗位数：{payload['raw_count']}")
    lines.append(f"- 筛选后岗位数：{payload['filtered_count']}")
    lines.append("- 排序逻辑：优先看方向分层，再结合内部匹配得分与投递优先级排序")
    if profile.min_monthly_salary_k is not None or profile.max_monthly_salary_k is not None:
        lines.append(
            f"- 薪资过滤：{profile.min_monthly_salary_k or '不限'}K - {profile.max_monthly_salary_k or '不限'}K / 月"
        )
    if payload.get("warnings"):
        lines.append("")
        lines.append("## 运行提示")
        lines.append("")
        for warning in payload["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("## 推荐岗位表")
    lines.append("")
    lines.append("| 投递优先级 | 方向分层 | 平台 | 岗位 | 公司 | 投递链接 | 地点 | 薪资 | 发布时间 | 一键投递备注 | 中文打招呼语 | 英文首句 | cover letter 提示 | JD 摘要 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for job in payload["jobs"][: profile.top_n]:
        lines.append(
            "| {priority} | {tier} | {source} | {title} | {company} | [查看岗位]({url}) | {location} | {salary} | {published_at} | {quick_note} | {message_cn} | {message_en} | {cover_hint} | {summary} |".format(
                priority=escape_md(job.get("apply_priority", "")),
                tier=escape_md(job.get("direction_tier", "未分层") or "未分层"),
                source=escape_md(job.get("source", "")),
                title=escape_md(job.get("title", "")),
                company=escape_md(job.get("company", "")),
                location=escape_md(job.get("location", "")),
                salary=escape_md(job.get("salary_display", "未知")),
                published_at=escape_md(job.get("published_at", "未知") or "未知"),
                quick_note=escape_md(job.get("quick_apply_note", "暂无") or "暂无"),
                message_cn=escape_md(job.get("outreach_message", "暂无")),
                message_en=escape_md(job.get("english_outreach_opener", "暂无")),
                cover_hint=escape_md(job.get("cover_letter_hint", "暂无") or "暂无"),
                summary=escape_md(job.get("jd_summary", "暂无") or "暂无"),
                url=job.get("apply_url", "#"),
            )
        )
    lines.append("")
    lines.append("## 岗位详情")
    lines.append("")
    for index, job in enumerate(payload["jobs"][: profile.top_n], start=1):
        lines.append(f"### {index}. {job.get('company', '')}｜{job.get('title', '')}")
        lines.append("")
        lines.append(f"- 投递优先级：{job.get('apply_priority', '')}")
        lines.append(f"- 方向分层：{job.get('direction_tier', '') or '未分层'}")
        lines.append(f"- 平台：{job.get('source', '')}")
        lines.append(f"- 投递链接：{job.get('apply_url', '')}")
        lines.append(f"- 地点：{job.get('location', '')}")
        lines.append(f"- 薪资：{job.get('salary_display', '未知')}")
        lines.append(f"- 发布时间：{job.get('published_at', '未知') or '未知'}")
        lines.append(f"- 截止日期：{job.get('deadline', '未知') or '未知'}")
        lines.append(f"- 一键投递备注：{job.get('quick_apply_note', '暂无')}")
        lines.append(f"- 匹配说明：{job.get('match_reason', '暂无')}")
        lines.append(f"- cover letter 提示：{job.get('cover_letter_hint', '暂无')}")
        lines.append(f"- 中文打招呼语：{job.get('outreach_message', '暂无')}")
        lines.append(f"- 英文首句：{job.get('english_outreach_opener', '暂无')}")
        lines.append(f"- JD 摘要：{job.get('jd_summary', '') or '暂无'}")
        lines.append(f"- 投递链接：{job.get('apply_url', '')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def escape_md(text: str) -> str:
    normalized = str(text).replace("\n", " ")
    return normalized.replace("|", "\\|")


def cmd_plan(args: argparse.Namespace) -> int:
    profile = apply_overrides(load_profile(Path(args.profile), Path(args.resume_path) if args.resume_path else None), args)
    print(json.dumps(build_search_plan(profile), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    profile = apply_overrides(load_profile(Path(args.profile), Path(args.resume_path) if args.resume_path else None), args)
    plan = build_search_plan(profile)
    warnings: list[str] = []
    raw_jobs: list[dict[str, Any]] = []

    raw_jobs.extend(search_jobspy(profile, plan, warnings))
    raw_jobs.extend(
        search_boss(
            profile,
            plan,
            warnings,
            Path(args.boss_repo_path or DEFAULT_BOSS_REPO),
            bootstrap_boss=bool(args.bootstrap_boss),
            output_dir=Path(args.output_dir),
        )
    )
    filtered_jobs = filter_jobs(raw_jobs, profile)
    paths = write_outputs(Path(args.output_dir), plan, filtered_jobs, raw_jobs, warnings, profile)
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="求职抓岗 skill 运行器：聚合 JobSpy 与 BOSS 直聘抓取结果。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common_parent = argparse.ArgumentParser(add_help=False)
    common_parent.add_argument("--profile", default=str(DEFAULT_PROFILE), help="YAML 配置文件路径")
    common_parent.add_argument("--resume-path", help="可选：显式指定本次使用的最新简历文件路径")
    common_parent.add_argument("--keywords", help="逗号分隔的搜索词，覆盖配置文件")
    common_parent.add_argument("--score-keywords", help="逗号分隔的打分关键词，覆盖配置文件")
    common_parent.add_argument("--cities", help="逗号分隔的城市，覆盖配置文件")
    common_parent.add_argument("--sites", help="逗号分隔的平台，例如 linkedin,indeed,google,boss")
    common_parent.add_argument("--min-salary-k", type=float, help="月薪下限（K）")
    common_parent.add_argument("--max-salary-k", type=float, help="月薪上限（K）")
    common_parent.add_argument("--hours-old", type=int, help="只保留最近 N 小时的岗位")
    common_parent.add_argument("--results-per-search", type=int, help="JobSpy 每个搜索组合抓取的目标数量")
    common_parent.add_argument("--boss-pages", type=int, help="BOSS 每个关键词+城市抓取页数")
    common_parent.add_argument("--top-n", type=int, help="Markdown 详情中展示的岗位数量")
    common_parent.add_argument("--remote-only", action="store_true", help="仅抓取 remote 岗位")

    plan_parser = subparsers.add_parser("plan", parents=[common_parent], help="预览搜索计划")
    plan_parser.set_defaults(func=cmd_plan)

    search_parser = subparsers.add_parser("search", parents=[common_parent], help="执行抓取并输出摘要")
    default_output_dir = DEFAULT_OUTPUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    search_parser.add_argument("--output-dir", default=str(default_output_dir), help="输出目录")
    search_parser.add_argument(
        "--boss-repo-path",
        default=str(DEFAULT_BOSS_REPO),
        help="boss-zhipin-scraper 仓库路径，默认使用 ~/.cache/job-radar/boss-zhipin-scraper",
    )
    search_parser.add_argument(
        "--bootstrap-boss",
        action="store_true",
        help="如果缺少 boss-zhipin-scraper，则自动 clone 官方仓库后再执行",
    )
    search_parser.set_defaults(func=cmd_search)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except SkillError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
