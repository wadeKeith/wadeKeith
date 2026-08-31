from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_readme", ROOT / "scripts" / "update_readme.py"
)
assert SPEC and SPEC.loader
update_readme = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_readme)


class RenderGeneratedSectionTests(unittest.TestCase):
    def test_generated_update_is_limited_to_a_compact_activity_section(self) -> None:
        repos = [
            {
                "id": 1,
                "name": "autoresearch-qwen",
                "full_name": "wadeKeith/autoresearch-qwen",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 212,
                "forks_count": 33,
                "language": "Python",
                "updated_at": "2026-08-24T00:00:00Z",
                "html_url": "https://github.com/wadeKeith/autoresearch-qwen",
                "description": "Autonomous research tooling",
            },
            {
                "id": 2,
                "name": "wadeKeith",
                "full_name": "wadeKeith/wadeKeith",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 99,
                "forks_count": 0,
                "language": None,
                "updated_at": "2026-08-31T00:00:00Z",
                "html_url": "https://github.com/wadeKeith/wadeKeith",
                "description": "Profile repository",
            },
        ]
        contributions = {
            "available": True,
            "total": 1010,
            "current": 10,
            "current_span": "Aug 22 - Aug 31",
            "longest": 20,
            "longest_span": "Jul 1 - Jul 20",
        }

        with tempfile.TemporaryDirectory() as directory, mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=repos),
            fetch_contribution_stats=mock.Mock(return_value=contributions),
            ASSETS=pathlib.Path(directory),
        ), mock.patch.object(
            update_readme,
            "fetch_contributed_repos",
            create=True,
            return_value=[],
        ):
            rendered = update_readme.build_generated_section()
            generated_assets = list(pathlib.Path(directory).iterdir())

        self.assertIn("## GitHub Activity", rendered)
        self.assertIn("| 1 | 212 | 1,010 |", rendered)
        self.assertNotIn("Troph", rendered)
        self.assertNotIn("Featured Repositories", rendered)
        self.assertNotIn("Recently Active", rendered)
        self.assertNotIn("streak", rendered.lower())
        self.assertEqual([], generated_assets)

    def test_includes_stars_from_owned_and_curated_contributor_repositories(self) -> None:
        owned_repos = [
            {
                "id": 1,
                "name": "autoresearch-qwen",
                "full_name": "wadeKeith/autoresearch-qwen",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 212,
            },
            {
                "id": 2,
                "name": "wadeKeith",
                "full_name": "wadeKeith/wadeKeith",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 99,
            },
        ]
        contributed_repos = [
            {
                "id": 101,
                "full_name": "OpenBMB/DeepThinkVLA",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 529,
            },
            {
                "id": 102,
                "full_name": "OpenBMB/SimpleNav",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 26,
            },
            {
                "id": 103,
                "full_name": "OpenBMB/MiniCPM-Robot",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 321,
            },
            {
                "id": 104,
                "full_name": "starVLA/starVLA",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 3600,
            },
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=owned_repos),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": True, "total": 1010}
            ),
        ), mock.patch.object(
            update_readme,
            "fetch_contributed_repos",
            create=True,
            return_value=contributed_repos,
        ):
            rendered = update_readme.build_generated_section()

        self.assertIn("Stars · owned + contributed repos", rendered)
        self.assertIn("| 1 | 4,688 | 1,010 |", rendered)

    def test_rejects_contributor_without_explicit_public_status(self) -> None:
        contributed_repos = [
            {
                "id": 101,
                "full_name": "OpenBMB/DeepThinkVLA",
                "stargazers_count": 529,
            }
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=[]),
            fetch_contributed_repos=mock.Mock(return_value=contributed_repos),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": True, "total": 1010}
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "not explicitly public"):
                update_readme.build_generated_section()

    def test_rejects_nonpositive_repository_id(self) -> None:
        contributed_repos = [
            {
                "id": 0,
                "full_name": "OpenBMB/DeepThinkVLA",
                "private": False,
                "stargazers_count": 529,
            }
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=[]),
            fetch_contributed_repos=mock.Mock(return_value=contributed_repos),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": True, "total": 1010}
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "numeric id"):
                update_readme.build_generated_section()

    def test_counts_same_repository_id_only_once(self) -> None:
        owned_repos = [
            {
                "id": 101,
                "name": "transferred-project",
                "full_name": "wadeKeith/transferred-project",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 42,
            }
        ]
        contributed_repos = [
            {
                "id": 101,
                "full_name": "ResearchOrg/transferred-project",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 42,
            }
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=owned_repos),
            fetch_contributed_repos=mock.Mock(return_value=contributed_repos),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": True, "total": 1010}
            ),
        ):
            rendered = update_readme.build_generated_section()

        self.assertIn("| 1 | 42 | 1,010 |", rendered)


class FetchContributedReposTests(unittest.TestCase):
    def test_fetches_every_verified_public_contributor_repository(self) -> None:
        expected_names = [
            "OpenBMB/DeepThinkVLA",
            "OpenBMB/SimpleNav",
            "OpenBMB/MiniCPM-Robot",
            "starVLA/starVLA",
            "huggingface/lerobot",
            "OpenDriveLab/AgiBot-World",
            "Physical-Intelligence/openpi",
            "twentyhq/twenty",
            "public-apis/public-apis",
        ]
        payloads = {
            name: {
                "id": index,
                "full_name": name,
                "private": False,
                "stargazers_count": index,
            }
            for index, name in enumerate(expected_names, start=1)
        }

        def fake_github_json(url: str) -> tuple[object, dict[str, str]]:
            full_name = url.removeprefix("https://api.github.com/repos/")
            return payloads[full_name], {}

        with mock.patch.object(
            update_readme, "github_json", side_effect=fake_github_json
        ):
            repositories = update_readme.fetch_contributed_repos()

        self.assertEqual(expected_names, [repo["full_name"] for repo in repositories])


class ReplaceSectionTests(unittest.TestCase):
    def test_rejects_ambiguous_duplicate_marker_pairs(self) -> None:
        readme = (
            f"intro\n{update_readme.START}\nold\n{update_readme.END}\n"
            f"research\n{update_readme.START}\nstale\n{update_readme.END}\n"
        )

        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            update_readme.replace_section(readme, "new activity")

    def test_rejects_reversed_markers(self) -> None:
        readme = (
            f"intro\n{update_readme.END}\nstale\n"
            f"{update_readme.START}\nresearch\n"
        )

        with self.assertRaisesRegex(RuntimeError, "before"):
            update_readme.replace_section(readme, "new activity")


class ContributionStatsTests(unittest.TestCase):
    def test_returns_only_the_total_used_by_the_public_summary(self) -> None:
        payload = {
            "user": {
                "contributionsCollection": {
                    "contributionCalendar": {
                        "totalContributions": 1010,
                        "weeks": [],
                    }
                }
            }
        }

        with mock.patch.object(update_readme, "github_graphql", return_value=payload):
            stats = update_readme.fetch_contribution_stats()

        self.assertEqual({"available": True, "total": 1010}, stats)

    def test_keeps_the_last_good_summary_when_contributions_are_unavailable(self) -> None:
        repos = [
            {
                "id": 1,
                "name": "autoresearch-qwen",
                "full_name": "wadeKeith/autoresearch-qwen",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers_count": 212,
            }
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=repos),
            fetch_contributed_repos=mock.Mock(return_value=[]),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": False, "total": "-"}
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "contribution data"):
                update_readme.build_generated_section()


if __name__ == "__main__":
    unittest.main()
