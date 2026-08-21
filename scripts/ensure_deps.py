#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOSS_REPO = Path.home() / ".cache" / "job-radar" / "boss-zhipin-scraper"
UPSTREAM_BOSS_REPO = "https://github.com/eatmoreduck/boss-zhipin-scraper.git"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def pip_install(packages: list[str]) -> None:
    if not packages:
        return
    run([sys.executable, "-m", "pip", "install", "-U", *packages])


def ensure_git() -> None:
    if shutil.which("git"):
        return
    raise SystemExit("❌ 当前环境缺少 git，无法下载 boss-zhipin-scraper。")


def ensure_boss_repo(repo_path: Path) -> Path:
    ensure_git()
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    if repo_path.exists():
        run(["git", "pull", "--ff-only"], cwd=repo_path)
    else:
        run(["git", "clone", "--depth", "1", UPSTREAM_BOSS_REPO, str(repo_path)])
    return repo_path


def ensure_boss_runtime_compat(repo_path: Path) -> None:
    script_path = repo_path / "scripts" / "boss_cdp_raw.py"
    if not script_path.exists():
        return
    content = script_path.read_text(encoding="utf-8")
    original = content
    header = "#!/usr/bin/env python3\nfrom __future__ import annotations\n\n"
    if content.startswith("#!/usr/bin/env python3\n") and "from __future__ import annotations" not in content[:120]:
        content = content.replace("#!/usr/bin/env python3\n", header, 1)
    content = content.replace(
        "websocket.create_connection(ws_url, timeout=60)",
        "websocket.create_connection(ws_url, timeout=60, suppress_origin=True)",
    )
    if content != original:
        script_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="安装求职抓岗 skill 的运行依赖。")
    parser.add_argument("--skip-jobspy", action="store_true", help="跳过 python-jobspy 安装")
    parser.add_argument("--with-boss", action="store_true", help="额外下载并安装 boss-zhipin-scraper")
    parser.add_argument(
        "--boss-repo-path",
        default=str(DEFAULT_BOSS_REPO),
        help="boss-zhipin-scraper 的缓存目录，默认 ~/.cache/job-radar/boss-zhipin-scraper",
    )
    args = parser.parse_args()

    packages = ["PyYAML"]
    if not args.skip_jobspy:
        packages.append("python-jobspy")
    pip_install(packages)

    if args.with_boss:
        repo_path = ensure_boss_repo(Path(args.boss_repo_path).expanduser())
        ensure_boss_runtime_compat(repo_path)
        requirements = repo_path / "requirements.txt"
        if requirements.exists():
            run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
        print(f"✅ boss-zhipin-scraper 已就绪：{repo_path}")

    print("✅ 运行依赖安装完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
