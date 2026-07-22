#!/usr/bin/env python3
"""Generate release notes for auto upstream build."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


def api_get(url: str, token: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "auto-upstream-build",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code}: {body[:300]}") from exc


def first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0].strip() if text else ""


def main() -> int:
    upstream = os.environ["UPSTREAM_REPO"]
    token = os.environ["GH_TOKEN"]
    latest_tag = os.environ["LATEST_TAG"]
    latest_commit = os.environ["LATEST_COMMIT"]
    previous_tag = (os.environ.get("PREVIOUS_TAG") or "").strip()
    notes_path = os.environ["NOTES_PATH"]
    short_commit = latest_commit[:7]

    release_body = ""
    try:
        release = api_get(f"https://api.github.com/repos/{upstream}/releases/tags/{latest_tag}", token)
        release_body = (release.get("body") or "").strip()
    except Exception:
        release_body = ""

    tag_message = ""
    try:
        ref = api_get(f"https://api.github.com/repos/{upstream}/git/ref/tags/{latest_tag}", token)
        obj = ref.get("object") or {}
        if obj.get("type") == "tag":
            tag_obj = api_get(f"https://api.github.com/repos/{upstream}/git/tags/{obj.get('sha')}", token)
            tag_message = (tag_obj.get("message") or "").strip()
    except Exception:
        tag_message = ""

    commits = []
    compare_url = ""
    if previous_tag:
        compare_url = f"https://github.com/{upstream}/compare/{previous_tag}...{latest_tag}"
        try:
            compare = api_get(
                f"https://api.github.com/repos/{upstream}/compare/{previous_tag}...{latest_tag}",
                token,
            )
            commits = compare.get("commits") or []
        except Exception:
            commits = []

    if not commits:
        try:
            commits = api_get(
                f"https://api.github.com/repos/{upstream}/commits?sha={latest_commit}&per_page=30",
                token,
            )
        except Exception:
            commits = []

    categories = [
        ("feat", "新功能"),
        ("fix", "问题修复"),
        ("perf", "性能优化"),
        ("refactor", "重构调整"),
        ("docs", "文档"),
        ("chore", "杂项"),
        ("ci", "CI"),
        ("other", "其他更新"),
    ]
    buckets = {key: [] for key, _ in categories}
    type_re = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?!?:\s+")

    for item in commits:
        sha = item.get("sha") or ""
        message = ((item.get("commit") or {}).get("message") or "").strip()
        subject = first_line(message)
        if not subject or subject.lower().startswith("merge "):
            continue
        m = type_re.match(subject)
        category = "other"
        if m:
            t = m.group("type").lower()
            if t in buckets:
                category = t
            elif t in {"build", "style", "test"}:
                category = "chore"
        buckets[category].append((subject, sha[:7], sha))

    lines = []
    lines.append(f"## Sesame-TK {latest_tag} 自动构建")
    lines.append("")
    lines.append(
        f"基于上游 [{upstream}](https://github.com/{upstream}) tag `{latest_tag}` "
        f"(commit `{short_commit}`) 自动构建。"
    )
    lines.append("")
    lines.append(f"- 上游标签：[`{latest_tag}`](https://github.com/{upstream}/releases/tag/{latest_tag})")
    lines.append(f"- 上游提交：[`{short_commit}`](https://github.com/{upstream}/commit/{latest_commit})")
    if previous_tag:
        lines.append(f"- 对比范围：`{previous_tag}...{latest_tag}`")
        if compare_url:
            lines.append(f"- 完整对比：{compare_url}")
    lines.append("")

    if release_body:
        lines.append("## 上游发布说明")
        lines.append("")
        lines.append(release_body)
        lines.append("")
    elif tag_message and tag_message not in {latest_tag, latest_tag.split("-")[-1]}:
        lines.append("## 上游标签说明")
        lines.append("")
        lines.append(tag_message)
        lines.append("")

    has_changes = any(buckets[key] for key, _ in categories)
    if has_changes:
        lines.append("## 更新说明")
        lines.append("")
        for key, title in categories:
            items = buckets[key]
            if not items:
                continue
            lines.append(f"### {title}")
            lines.append("")
            for subject, short_sha, full_sha in items:
                lines.append(
                    f"- {subject} ([{short_sha}](https://github.com/{upstream}/commit/{full_sha}))"
                )
            lines.append("")
    else:
        lines.append("## 更新说明")
        lines.append("")
        lines.append("_暂未解析到可展示的提交变更，请查看上游仓库提交历史。_")
        lines.append("")

    lines.append("## 下载说明")
    lines.append("")
    lines.append("- `app-arm64-v8a-release.apk`：64 位 ARM 设备（主流手机）")
    lines.append("- `app-armeabi-v7a-release.apk`：32 位 ARM 设备（旧款手机）")
    lines.append("- `app-x86_64-release.apk` / `app-x86-release.apk`：模拟器")
    lines.append("- `app-universal-release.apk`：通用版（不确定架构时使用）")
    lines.append("")
    lines.append(
        f"> 此为自动构建版本，非官方发布。使用前请阅读 "
        f"[LEGAL.md](https://github.com/{upstream}/blob/main/LEGAL.md)。"
    )

    Path = __import__("pathlib").Path
    Path(notes_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote release notes to {notes_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
