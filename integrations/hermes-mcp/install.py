#!/usr/bin/env python3
"""Install the MistakeMate Hermes skill and local MCP bridge for one user.

Run this from a checked-out MistakeMate repository.  It is safe to let Hermes
run it after the user supplies the MistakeMate URL and one freshly created
Hermes token.  Existing MCP configuration is never replaced without --replace.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install MistakeMate control for Hermes")
    parser.add_argument("--url", required=True, help="MistakeMate URL, e.g. http://192.168.1.20:8080")
    parser.add_argument("--token", required=True, help="A one-time-visible mmh_ token created in MistakeMate account settings")
    parser.add_argument("--hermes-bin", default="hermes", help="Hermes executable (default: hermes)")
    parser.add_argument("--replace", action="store_true", help="Replace an existing mistakemate MCP entry")
    parser.add_argument("--skip-test", action="store_true", help="Register files and MCP without running hermes mcp test")
    parser.add_argument("--dry-run", action="store_true", help="Show installation locations without changing anything")
    return parser.parse_args()


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    source_server = root / "hermes-mcp" / "server.py"
    source_skill = root / "hermes-skill"
    if not source_server.is_file() or not (source_skill / "SKILL.md").is_file():
        raise SystemExit("安装文件不完整，请从 MistakeMate 仓库的 integrations 目录运行此脚本。")
    if not args.token.startswith("mmh_"):
        raise SystemExit("令牌格式不正确：请在 MistakeMate 的账户设置中重新创建 Hermes 令牌。")

    hermes_home = Path.home() / ".hermes"
    bridge_dir = hermes_home / "integrations" / "mistakemate-mcp"
    skill_dir = hermes_home / "skills" / "mistakemate-control"
    server_path = bridge_dir / "server.py"

    print(f"MCP 脚本：{server_path}")
    print(f"Hermes skill：{skill_dir}")
    if args.dry_run:
        print("演练模式：未复制文件、未修改 Hermes MCP 配置。")
        return

    listed = subprocess.run([args.hermes_bin, "mcp", "list"], text=True, capture_output=True)
    if "mistakemate" in listed.stdout.lower() or "mistakemate" in listed.stderr.lower():
        if not args.replace:
            raise SystemExit("已发现名为 mistakemate 的 MCP 配置。未复制文件或修改配置；确认更新请加 --replace 后重试。")
        run([args.hermes_bin, "mcp", "remove", "mistakemate"])

    bridge_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_server, server_path)
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    shutil.copytree(source_skill, skill_dir)

    run([
        args.hermes_bin, "mcp", "add", "mistakemate",
        "--command", sys.executable,
        "--env", f"MISTAKEMATE_URL={args.url.rstrip('/')}", f"MISTAKEMATE_TOKEN={args.token}",
        "--args", str(server_path),
    ])
    if not args.skip_test:
        run([args.hermes_bin, "mcp", "test", "mistakemate"])
    print("安装完成。请重新开启 Hermes 会话，然后使用 /mistakemate-control。")


if __name__ == "__main__":
    main()
