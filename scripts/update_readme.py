#!/usr/bin/env python3
"""Refresh the compact activity section in the GitHub profile README."""

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
ASSETS = ROOT / "assets"
START = "<!-- PROFILE:START -->"
END = "<!-- PROFILE:END -->"
CONTRIBUTED_REPOSITORIES = (
    "OpenBMB/DeepThinkVLA",
    "OpenBMB/SimpleNav",
    "OpenBMB/MiniCPM-Robot",
    "starVLA/starVLA",
    "huggingface/lerobot",
    "OpenDriveLab/AgiBot-World",
    "Physical-Intelligence/openpi",
    "twentyhq/twenty",
    "public-apis/public-apis",
)


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


def fetch_contributed_repos() -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for full_name in CONTRIBUTED_REPOSITORIES:
        normalized_name = full_name.casefold()
        if normalized_name in seen_names:
            raise RuntimeError(f"Duplicate contributed repository: {full_name}")
        seen_names.add(normalized_name)

        url = f"https://api.github.com/repos/{urllib.parse.quote(full_name, safe='/')}"
        payload, _ = github_json(url)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected repository payload for {full_name}: {payload!r}"
            )
        repositories.append(payload)
    return repositories


def fetch_contribution_stats() -> dict[str, object]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
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
        return {"available": False, "total": "-"}
    return {"available": True, "total": calendar.get("totalContributions", "-")}


def format_metric(value: object) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def render_generated_section(
    *,
    public_projects: int,
    maintained_stars: int,
    contributions: object,
    generated_at: str,
) -> str:
    return f"""<!-- This section is generated by scripts/update_readme.py. -->
## GitHub Activity

| Public projects | Stars · owned + contributed repos | Contributions · last 12 months |
| ---: | ---: | ---: |
| {public_projects} | {format_metric(maintained_stars)} | {format_metric(contributions)} |

<sub>Public GitHub data · repository stars include owned and verified contributed projects · refreshed {generated_at}</sub>"""


def build_generated_section() -> str:
    repos = fetch_repos()
    public_projects = [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
        and repo.get("name") != USERNAME
    ]
    contributed_repos = fetch_contributed_repos()
    star_repositories: dict[int, dict[str, object]] = {}
    for repo in [*public_projects, *contributed_repos]:
        repo_id = repo.get("id")
        stars = repo.get("stargazers_count")
        if (
            isinstance(repo_id, bool)
            or not isinstance(repo_id, int)
            or repo_id <= 0
        ):
            raise RuntimeError(f"Repository is missing a valid numeric id: {repo!r}")
        if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
            raise RuntimeError(f"Repository has invalid star data: {repo!r}")
        if repo.get("private") is not False:
            raise RuntimeError(f"Repository is not explicitly public: {repo!r}")
        star_repositories[repo_id] = repo
    maintained_stars = sum(
        int(repo["stargazers_count"]) for repo in star_repositories.values()
    )
    contribution_stats = fetch_contribution_stats()
    if not contribution_stats.get("available"):
        raise RuntimeError("GitHub contribution data is unavailable; keeping the last good summary")
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return render_generated_section(
        public_projects=len(public_projects),
        maintained_stars=maintained_stars,
        contributions=contribution_stats.get("total", "-"),
        generated_at=generated_at,
    )


def replace_section(readme: str, generated: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise RuntimeError(
            f"{README} must contain exactly one {START} and one {END} marker"
        )
    if readme.index(START) > readme.index(END):
        raise RuntimeError(f"{README} must place {START} before {END}")
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
