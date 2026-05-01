#!/usr/bin/env python3
"""Update the generated section of the GitHub profile README."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


USERNAME = os.getenv("PROFILE_USERNAME", "wadeKeith")
ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ASSETS = ROOT / "assets"
START = "<!-- PROFILE:START -->"
END = "<!-- PROFILE:END -->"
PINNED_REPOS = ("OpenBMB/DeepThinkVLA",)


def github_json(url: str) -> tuple[object, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2**attempt)
                continue
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API request failed: {exc.code} {url}\n{body}") from exc
        except urllib.error.URLError as exc:
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"GitHub API request failed: {url}\n{exc}") from exc
    raise AssertionError("unreachable")


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def fetch_repos() -> list[dict[str, object]]:
    repos: list[dict[str, object]] = []
    url = (
        f"https://api.github.com/users/{urllib.parse.quote(USERNAME)}/repos"
        "?type=owner&sort=updated&per_page=100"
    )
    while url:
        payload, headers = github_json(url)
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected repos payload: {payload!r}")
        repos.extend(payload)
        url = parse_next_link(headers.get("Link"))
    return repos


def fetch_repo(full_name: str) -> dict[str, object]:
    payload, _ = github_json(f"https://api.github.com/repos/{urllib.parse.quote(full_name, safe='/')}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected repo payload for {full_name}: {payload!r}")
    return payload


def text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


def md_escape(value: object) -> str:
    return text(value, "-").replace("|", r"\|").replace("\n", " ").strip() or "-"


def repo_row(repo: dict[str, object]) -> str:
    full_name = text(repo.get("full_name"))
    owner = full_name.split("/", 1)[0] if "/" in full_name else USERNAME
    display_name = full_name if owner != USERNAME and full_name else repo.get("name")
    name = md_escape(display_name)
    html_url = text(repo.get("html_url"), f"https://github.com/{USERNAME}/{name}")
    description = md_escape(repo.get("description")) if repo.get("description") else "-"
    stars = repo.get("stargazers_count", 0)
    language_obj = repo.get("language")
    language = md_escape(language_obj) if language_obj else "-"
    updated = text(repo.get("updated_at"), "")[:10] or "-"
    return f"| [{name}]({html_url}) | {description} | {language} | {stars} | {updated} |"


def shields_language_badges(language_counts: dict[str, int]) -> str:
    colors = {
        "Python": "3776AB",
        "C++": "00599C",
        "TypeScript": "3178C6",
        "Jupyter Notebook": "F37626",
        "TeX": "008080",
        "Shell": "4EAA25",
        "Makefile": "6D8086",
    }
    badges = []
    for language, count in sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))[:6]:
        label = urllib.parse.quote(language)
        color = colors.get(language, "555555")
        badges.append(
            f'<img src="https://img.shields.io/badge/{label}-{count}-{color}?style=flat-square" alt="{language}" />'
        )
    return "\n".join(badges)


def svg_escape(value: object) -> str:
    return html.escape(text(value), quote=True)


def write_svg_cards(
    user_payload: dict[str, object],
    project_repo_count: int,
    total_stars: int,
    total_forks: int,
    language_counts: dict[str, int],
    generated_at: str,
) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    stats = [
        ("Public repos", user_payload.get("public_repos", 0)),
        ("Project repos", project_repo_count),
        ("Stars", total_stars),
        ("Forks", total_forks),
        ("Followers", user_payload.get("followers", 0)),
        ("Following", user_payload.get("following", 0)),
    ]
    stat_cells = []
    for index, (label, value) in enumerate(stats):
        col = index % 2
        row = index // 2
        x = 28 + col * 220
        y = 78 + row * 45
        stat_cells.append(
            f'<text x="{x}" y="{y}" font-size="24" font-weight="700" fill="#24292f">{svg_escape(value)}</text>'
            f'<text x="{x}" y="{y + 20}" font-size="12" fill="#57606a">{svg_escape(label)}</text>'
        )

    stats_svg = f"""<svg width="480" height="210" viewBox="0 0 480 210" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">GitHub snapshot for {svg_escape(USERNAME)}</title>
  <desc id="desc">Auto-generated GitHub profile statistics.</desc>
  <rect x="0.5" y="0.5" width="479" height="209" rx="8" fill="#ffffff" stroke="#d0d7de"/>
  <text x="24" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="700" fill="#24292f">GitHub Snapshot</text>
  <text x="24" y="56" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">Generated {svg_escape(generated_at)}</text>
  <g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">
    {''.join(stat_cells)}
  </g>
</svg>
"""
    (ASSETS / "profile-stats.svg").write_text(stats_svg, encoding="utf-8")

    language_colors = {
        "Python": "#3776AB",
        "C++": "#00599C",
        "TypeScript": "#3178C6",
        "Jupyter Notebook": "#F37626",
        "TeX": "#008080",
        "Shell": "#4EAA25",
        "Makefile": "#6D8086",
        "MATLAB": "#E16737",
    }
    languages = sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    max_count = max((count for _, count in languages), default=1)
    language_rows = []
    if languages:
        for index, (language, count) in enumerate(languages):
            y = 74 + index * 25
            width = max(8, round(250 * count / max_count))
            color = language_colors.get(language, "#59636e")
            language_rows.append(
                f'<text x="24" y="{y}" font-size="12" fill="#24292f">{svg_escape(language)}</text>'
                f'<text x="316" y="{y}" font-size="12" text-anchor="end" fill="#57606a">{count}</text>'
                f'<rect x="24" y="{y + 7}" width="292" height="8" rx="4" fill="#eaeef2"/>'
                f'<rect x="24" y="{y + 7}" width="{width}" height="8" rx="4" fill="{color}"/>'
            )
    else:
        language_rows.append('<text x="24" y="84" font-size="13" fill="#57606a">No language data yet</text>')

    languages_svg = f"""<svg width="340" height="210" viewBox="0 0 340 210" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Language mix for {svg_escape(USERNAME)}</title>
  <desc id="desc">Auto-generated language distribution by public project count.</desc>
  <rect x="0.5" y="0.5" width="339" height="209" rx="8" fill="#ffffff" stroke="#d0d7de"/>
  <text x="24" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="700" fill="#24292f">Language Mix</text>
  <text x="24" y="56" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">By public project repositories</text>
  <g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">
    {''.join(language_rows)}
  </g>
</svg>
"""
    (ASSETS / "profile-languages.svg").write_text(languages_svg, encoding="utf-8")


def build_generated_section() -> str:
    user_payload, _ = github_json(f"https://api.github.com/users/{urllib.parse.quote(USERNAME)}")
    if not isinstance(user_payload, dict):
        raise RuntimeError(f"Unexpected user payload: {user_payload!r}")

    repos = fetch_repos()
    original_public_repos = [
        repo for repo in repos
        if not repo.get("fork") and not repo.get("archived") and repo.get("name") != USERNAME
    ]
    pinned_repos = [fetch_repo(full_name) for full_name in PINNED_REPOS]
    total_stars = sum(int(repo.get("stargazers_count") or 0) for repo in original_public_repos)
    total_forks = sum(int(repo.get("forks_count") or 0) for repo in original_public_repos)
    language_counts: dict[str, int] = {}
    for repo in original_public_repos:
        language = repo.get("language")
        if language:
            language_counts[str(language)] = language_counts.get(str(language), 0) + 1

    sorted_top_repos = sorted(
        original_public_repos,
        key=lambda repo: (int(repo.get("stargazers_count") or 0), text(repo.get("updated_at"))),
        reverse=True,
    )
    pinned_full_names = {text(repo.get("full_name")) for repo in pinned_repos}
    top_repos = pinned_repos + [
        repo for repo in sorted_top_repos
        if text(repo.get("full_name")) not in pinned_full_names
    ][:6]
    recent_repos = sorted(
        original_public_repos,
        key=lambda repo: text(repo.get("updated_at")),
        reverse=True,
    )[:5]

    updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_svg_cards(
        user_payload=user_payload,
        project_repo_count=len(original_public_repos),
        total_stars=total_stars,
        total_forks=total_forks,
        language_counts=language_counts,
        generated_at=updated_at,
    )
    trophy_url = (
        "https://github-profile-trophy.vercel.app/"
        f"?username={urllib.parse.quote(USERNAME)}"
        "&theme=flat"
        "&column=7"
        "&margin-w=8"
        "&margin-h=8"
        "&no-bg=true"
    )
    stats_url = "./assets/profile-stats.svg"
    top_langs_url = "./assets/profile-languages.svg"
    streak_url = (
        "https://streak-stats.demolab.com"
        f"?user={urllib.parse.quote(USERNAME)}"
        "&theme=default"
        "&hide_border=false"
    )
    visitor_url = (
        "https://komarev.com/ghpvc/"
        f"?username={urllib.parse.quote(USERNAME)}"
        "&style=flat-square"
        "&color=0e75b6"
        "&label=Profile+views"
    )

    language_badges = shields_language_badges(language_counts)
    top_repo_table = "\n".join(repo_row(repo) for repo in top_repos)
    recent_repo_table = "\n".join(repo_row(repo) for repo in recent_repos)

    return f"""<!-- This section is generated by scripts/update_readme.py. -->
<p align="center">
  <img src="{visitor_url}" alt="Profile views" />
  <img src="https://img.shields.io/github/followers/{USERNAME}?style=flat-square&label=Followers&color=0e75b6" alt="Followers" />
  <img src="https://img.shields.io/badge/Total%20stars-{total_stars}-0e75b6?style=flat-square" alt="Total stars" />
  <img src="https://img.shields.io/badge/Public%20repos-{user_payload.get("public_repos", 0)}-0e75b6?style=flat-square" alt="Public repositories" />
</p>

<p align="center">
  <img src="{trophy_url}" alt="GitHub profile trophies" />
</p>

## Snapshot

| Public repos | Project repos | Stars | Forks | Followers | Following |
| ---: | ---: | ---: | ---: | ---: | ---: |
| {user_payload.get("public_repos", 0)} | {len(original_public_repos)} | {total_stars} | {total_forks} | {user_payload.get("followers", 0)} | {user_payload.get("following", 0)} |

<p align="center">
{language_badges}
</p>

## Activity

<p align="center">
  <img height="165" src="{stats_url}" alt="GitHub stats" />
  <img height="165" src="{top_langs_url}" alt="Top languages" />
</p>

<p align="center">
  <img src="{streak_url}" alt="GitHub contribution streak" />
</p>

## Featured Repositories

| Repository | Description | Language | Stars | Updated |
| --- | --- | --- | ---: | --- |
{top_repo_table}

## Recently Active Public Repositories

| Repository | Description | Language | Stars | Updated |
| --- | --- | --- | ---: | --- |
{recent_repo_table}

<sub>Last generated: {updated_at}</sub>"""


def replace_section(readme: str, generated: str) -> str:
    if START not in readme or END not in readme:
        raise RuntimeError(f"{README} must contain {START} and {END} markers")
    return re.sub(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        f"{START}\n{generated}\n{END}",
        readme,
        flags=re.DOTALL,
    )


def main() -> int:
    readme = README.read_text(encoding="utf-8")
    generated = build_generated_section()
    updated = replace_section(readme, generated)
    if updated != readme:
        README.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
