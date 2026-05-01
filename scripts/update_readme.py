#!/usr/bin/env python3
"""Update the generated section of the GitHub profile README."""

from __future__ import annotations

import datetime as dt
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
START = "<!-- PROFILE:START -->"
END = "<!-- PROFILE:END -->"


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


def text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


def md_escape(value: object) -> str:
    return text(value, "-").replace("|", r"\|").replace("\n", " ").strip() or "-"


def repo_row(repo: dict[str, object]) -> str:
    name = md_escape(repo.get("name"))
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


def build_generated_section() -> str:
    user_payload, _ = github_json(f"https://api.github.com/users/{urllib.parse.quote(USERNAME)}")
    if not isinstance(user_payload, dict):
        raise RuntimeError(f"Unexpected user payload: {user_payload!r}")

    repos = fetch_repos()
    original_public_repos = [
        repo for repo in repos
        if not repo.get("fork") and not repo.get("archived") and repo.get("name") != USERNAME
    ]
    total_stars = sum(int(repo.get("stargazers_count") or 0) for repo in original_public_repos)
    total_forks = sum(int(repo.get("forks_count") or 0) for repo in original_public_repos)
    language_counts: dict[str, int] = {}
    for repo in original_public_repos:
        language = repo.get("language")
        if language:
            language_counts[str(language)] = language_counts.get(str(language), 0) + 1

    top_repos = sorted(
        original_public_repos,
        key=lambda repo: (int(repo.get("stargazers_count") or 0), text(repo.get("updated_at"))),
        reverse=True,
    )[:6]
    recent_repos = sorted(
        original_public_repos,
        key=lambda repo: text(repo.get("updated_at")),
        reverse=True,
    )[:5]

    updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    trophy_url = (
        "https://github-profile-trophy.vercel.app/"
        f"?username={urllib.parse.quote(USERNAME)}"
        "&theme=flat"
        "&column=7"
        "&margin-w=8"
        "&margin-h=8"
        "&no-bg=true"
    )
    stats_url = (
        "https://github-readme-stats.vercel.app/api"
        f"?username={urllib.parse.quote(USERNAME)}"
        "&show_icons=true"
        "&theme=default"
        "&hide_border=false"
        "&include_all_commits=true"
        "&count_private=false"
    )
    top_langs_url = (
        "https://github-readme-stats.vercel.app/api/top-langs/"
        f"?username={urllib.parse.quote(USERNAME)}"
        "&layout=compact"
        "&theme=default"
        "&hide_border=false"
    )
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

## Featured Public Repositories

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
