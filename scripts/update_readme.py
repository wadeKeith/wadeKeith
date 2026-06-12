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


def github_graphql(query: str, variables: dict[str, object]) -> dict[str, object] | None:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        return None

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"{USERNAME}-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request("https://api.github.com/graphql", data=body, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("errors"):
                    return None
                data = payload.get("data")
                return data if isinstance(data, dict) else None
        except (urllib.error.HTTPError, urllib.error.URLError):
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            return None
    return None


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


def display_date(date_text: str | None) -> str:
    if not date_text:
        return "-"
    try:
        value = dt.date.fromisoformat(date_text)
    except ValueError:
        return date_text
    return value.strftime("%b %-d")


def date_span(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "-"
    if start == end:
        return display_date(start)
    return f"{display_date(start)} - {display_date(end)}"


def fetch_contribution_stats() -> dict[str, object]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    payload = github_graphql(query, {"login": USERNAME})
    calendar = (
        payload
        and payload.get("user")
        and payload["user"].get("contributionsCollection")
        and payload["user"]["contributionsCollection"].get("contributionCalendar")
    )
    if not isinstance(calendar, dict):
        return {
            "available": False,
            "total": "-",
            "current": "-",
            "current_span": "-",
            "longest": "-",
            "longest_span": "-",
        }

    days: list[dict[str, object]] = []
    for week in calendar.get("weeks", []):
        if isinstance(week, dict):
            days.extend(day for day in week.get("contributionDays", []) if isinstance(day, dict))
    days = sorted(days, key=lambda day: text(day.get("date")))

    longest = 0
    longest_start: str | None = None
    longest_end: str | None = None
    active = 0
    active_start: str | None = None

    for day in days:
        date_text = text(day.get("date"))
        count = int(day.get("contributionCount") or 0)
        if count > 0:
            if active == 0:
                active_start = date_text
            active += 1
            if active > longest:
                longest = active
                longest_start = active_start
                longest_end = date_text
        else:
            active = 0
            active_start = None

    current = 0
    current_start: str | None = None
    current_end: str | None = None
    for day in reversed(days):
        date_text = text(day.get("date"))
        count = int(day.get("contributionCount") or 0)
        if count <= 0:
            break
        current += 1
        current_start = date_text
        if current_end is None:
            current_end = date_text

    return {
        "available": True,
        "total": calendar.get("totalContributions", "-"),
        "current": current,
        "current_span": date_span(current_start, current_end),
        "longest": longest,
        "longest_span": date_span(longest_start, longest_end),
    }


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


def svg_escape(value: object) -> str:
    return html.escape(text(value), quote=True)


def compact_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return text(value, "-")
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".replace(".0M", "M")
    if number >= 1_000:
        return f"{number / 1_000:.1f}k".replace(".0k", "k")
    if number == int(number):
        return str(int(number))
    return f"{number:.1f}"


def account_age_years(user_payload: dict[str, object]) -> str:
    created_at = text(user_payload.get("created_at"))
    if not created_at:
        return "-"
    try:
        created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    now = dt.datetime.now(dt.timezone.utc)
    years = max(0.0, (now - created).days / 365.25)
    return f"{years:.1f}y"


def trophy_card(
    x: int,
    y: int,
    title: str,
    rank: str,
    subtitle: str,
    points: str,
    color: str,
    progress: float,
) -> str:
    progress_width = max(14, min(108, round(108 * progress)))
    cup_x = x + 42
    cup_y = y + 42
    return f"""<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">
    <rect x="{x}" y="{y}" width="128" height="150" rx="8" fill="#ffffff" stroke="#d0d7de"/>
    <text x="{x + 64}" y="{y + 24}" text-anchor="middle" font-size="14" font-weight="700" fill="#111111">{svg_escape(title)}</text>
    <path d="M{cup_x + 12} {cup_y + 14} C{cup_x - 8} {cup_y + 14} {cup_x - 8} {cup_y + 42} {cup_x + 15} {cup_y + 44}" fill="none" stroke="{color}" stroke-width="6"/>
    <path d="M{cup_x + 44} {cup_y + 14} C{cup_x + 64} {cup_y + 14} {cup_x + 64} {cup_y + 42} {cup_x + 41} {cup_y + 44}" fill="none" stroke="{color}" stroke-width="6"/>
    <path d="M{cup_x + 8} {cup_y} H{cup_x + 48} C{cup_x + 48} {cup_y + 28} {cup_x + 41} {cup_y + 47} {cup_x + 28} {cup_y + 52} C{cup_x + 15} {cup_y + 47} {cup_x + 8} {cup_y + 28} {cup_x + 8} {cup_y} Z" fill="{color}" opacity="0.92"/>
    <circle cx="{cup_x + 28}" cy="{cup_y + 23}" r="22" fill="#ffffff" stroke="{color}" stroke-width="4"/>
    <text x="{cup_x + 28}" y="{cup_y + 32}" text-anchor="middle" font-size="26" font-weight="800" fill="{color}">{svg_escape(rank)}</text>
    <path d="M{cup_x + 23} {cup_y + 52} H{cup_x + 33} V{cup_y + 68} H{cup_x + 23} Z" fill="{color}"/>
    <path d="M{cup_x + 10} {cup_y + 68} H{cup_x + 46} V{cup_y + 76} H{cup_x + 10} Z" fill="{color}"/>
    <text x="{x + 64}" y="{y + 118}" text-anchor="middle" font-size="12" font-weight="700" fill="#57606a">{svg_escape(subtitle)}</text>
    <text x="{x + 64}" y="{y + 135}" text-anchor="middle" font-size="11" font-weight="700" fill="#57606a">{svg_escape(points)}</text>
    <rect x="{x + 10}" y="{y + 141}" width="108" height="4" rx="2" fill="#c8d9f1"/>
    <rect x="{x + 10}" y="{y + 141}" width="{progress_width}" height="4" rx="2" fill="#0969da"/>
  </g>"""


def write_svg_cards(
    user_payload: dict[str, object],
    project_repo_count: int,
    total_stars: int,
    total_forks: int,
    language_counts: dict[str, int],
    pinned_repos: list[dict[str, object]],
    contribution_stats: dict[str, object],
    generated_at: str,
) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    hero_svg = f"""<svg width="900" height="130" viewBox="0 0 900 130" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">wadeKeith profile introduction</title>
  <desc id="desc">Embodied AI, vision-language-action, and robot learning profile header.</desc>
  <rect x="0.5" y="0.5" width="899" height="129" rx="10" fill="#ffffff" stroke="#d0d7de"/>
  <text x="450" y="42" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="28" font-weight="700" fill="#24292f">wadeKeith</text>
  <text x="450" y="74" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="17" font-weight="600" fill="#0969da">Embodied AI | Vision-Language-Action | Robot Learning</text>
  <text x="450" y="101" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="14" fill="#57606a">Building research systems that connect models, data, and real robots</text>
</svg>
"""
    (ASSETS / "profile-hero.svg").write_text(hero_svg, encoding="utf-8")

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

    primary_project = pinned_repos[0] if pinned_repos else {}
    project_name = text(primary_project.get("name"), "DeepThinkVLA")
    project_stars = int(primary_project.get("stargazers_count") or 0)
    language_count = len(language_counts)
    public_repos = int(user_payload.get("public_repos") or 0)
    followers = int(user_payload.get("followers") or 0)
    contribution_total = int(contribution_stats.get("total") if isinstance(contribution_stats.get("total"), int) else 0)
    current_streak = int(contribution_stats.get("current") if isinstance(contribution_stats.get("current"), int) else 0)
    trophy_items = [
        ("MultiLanguage", "S" if language_count >= 5 else "A", "Rainbow Lang User", f"{language_count} langs", "#c42df5", min(1, language_count / 6)),
        ("Stars", "S" if total_stars >= 300 else "A", "High Stargazer", compact_number(total_stars), "#d18b00", min(1, total_stars / 500)),
        ("Followers", "A" if followers >= 50 else "B", "Community Builder", compact_number(followers), "#d59a66", min(1, followers / 150)),
        ("Repositories", "A" if public_repos >= 30 else "B", "Repo Creator", compact_number(public_repos), "#d18b00", min(1, public_repos / 60)),
        ("DeepThinkVLA", "S", "Core Project", f"{compact_number(project_stars)} stars", "#d18b00", min(1, project_stars / 600)),
        ("Commits", "A" if contribution_total >= 500 else "B", "Hyper Committer", compact_number(contribution_total), "#6f7dc8", min(1, contribution_total / 800)),
        ("Streak", "A" if current_streak >= 7 else "B", "Daily Builder", f"{compact_number(current_streak)} days", "#f08a00", min(1, current_streak / 14)),
        ("Experience", "A", "Experienced Dev", account_age_years(user_payload), "#7f8c8d", 0.72),
        ("Forks", "A" if total_forks >= 30 else "B", "Project Forks", compact_number(total_forks), "#5f6b73", min(1, total_forks / 80)),
        ("Projects", "B" if project_repo_count < 30 else "A", "Active Projects", compact_number(project_repo_count), "#59636e", min(1, project_repo_count / 40)),
    ]

    trophy_cards = []
    for index, item in enumerate(trophy_items):
        row = index // 5
        col = index % 5
        trophy_cards.append(trophy_card(34 + col * 170, 52 + row * 166, *item))
    trophy_svg = f"""<svg width="900" height="390" viewBox="0 0 900 390" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">GitHub profile trophies for {svg_escape(USERNAME)}</title>
  <desc id="desc">Self-hosted trophy-style profile board generated from GitHub data.</desc>
  <rect x="0.5" y="0.5" width="899" height="389" rx="10" fill="#f6f8fa" stroke="#d0d7de"/>
  <text x="24" y="34" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="700" fill="#24292f">GitHub Profile Trophies</text>
  <text x="876" y="34" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">Generated {svg_escape(generated_at)}</text>
  {''.join(trophy_cards)}
</svg>
"""
    (ASSETS / "profile-trophy.svg").write_text(trophy_svg, encoding="utf-8")

    contribution_items = [
        ("12-mo contributions", contribution_stats.get("total", "-"), "Contribution calendar"),
        ("Current streak", contribution_stats.get("current", "-"), contribution_stats.get("current_span", "-")),
        ("Longest streak", contribution_stats.get("longest", "-"), contribution_stats.get("longest_span", "-")),
    ]
    contribution_cells = []
    for index, (label, value, caption) in enumerate(contribution_items):
        x = 28 + index * 158
        contribution_cells.append(
            f'<text x="{x + 63}" y="92" text-anchor="middle" font-size="30" font-weight="700" fill="#24292f">{svg_escape(value)}</text>'
            f'<text x="{x + 63}" y="121" text-anchor="middle" font-size="14" font-weight="700" fill="#0969da">{svg_escape(label)}</text>'
            f'<text x="{x + 63}" y="146" text-anchor="middle" font-size="12" fill="#57606a">{svg_escape(caption)}</text>'
            f'<line x1="{x + 135}" y1="64" x2="{x + 135}" y2="154" stroke="#d8dee4"/>'
        )
    contributions_svg = f"""<svg width="520" height="210" viewBox="0 0 520 210" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Contribution summary for {svg_escape(USERNAME)}</title>
  <desc id="desc">Auto-generated contribution summary from GitHub contribution data.</desc>
  <rect x="0.5" y="0.5" width="519" height="209" rx="8" fill="#ffffff" stroke="#d0d7de"/>
  <text x="24" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="700" fill="#24292f">Contribution Summary</text>
  <text x="24" y="56" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">Generated {svg_escape(generated_at)}</text>
  <g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">
    {''.join(contribution_cells)}
  </g>
</svg>
"""
    (ASSETS / "profile-contributions.svg").write_text(contributions_svg, encoding="utf-8")


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
    contribution_stats = fetch_contribution_stats()

    updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_svg_cards(
        user_payload=user_payload,
        project_repo_count=len(original_public_repos),
        total_stars=total_stars,
        total_forks=total_forks,
        language_counts=language_counts,
        pinned_repos=pinned_repos,
        contribution_stats=contribution_stats,
        generated_at=updated_at,
    )
    stats_url = "./assets/profile-stats.svg"
    top_langs_url = "./assets/profile-languages.svg"
    trophy_url = "./assets/profile-trophy.svg"
    contributions_url = "./assets/profile-contributions.svg"

    top_repo_table = "\n".join(repo_row(repo) for repo in top_repos)
    recent_repo_table = "\n".join(repo_row(repo) for repo in recent_repos)

    return f"""<!-- This section is generated by scripts/update_readme.py. -->
<p align="center">
  <img src="{trophy_url}" alt="GitHub profile trophies" />
</p>

## Snapshot

| Public repos | Project repos | Stars | Forks | Followers | Following |
| ---: | ---: | ---: | ---: | ---: | ---: |
| {user_payload.get("public_repos", 0)} | {len(original_public_repos)} | {total_stars} | {total_forks} | {user_payload.get("followers", 0)} | {user_payload.get("following", 0)} |

## Activity

<p align="center">
  <img height="165" src="{stats_url}" alt="GitHub stats" />
  <img height="165" src="{top_langs_url}" alt="Top languages" />
</p>

<p align="center">
  <img height="165" src="{contributions_url}" alt="GitHub contribution summary" />
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
