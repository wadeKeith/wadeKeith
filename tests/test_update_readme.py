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
                "name": "autoresearch-qwen",
                "full_name": "wadeKeith/autoresearch-qwen",
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
                "name": "wadeKeith",
                "full_name": "wadeKeith/wadeKeith",
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
                "name": "autoresearch-qwen",
                "fork": False,
                "archived": False,
                "stargazers_count": 212,
            }
        ]

        with mock.patch.multiple(
            update_readme,
            fetch_repos=mock.Mock(return_value=repos),
            fetch_contribution_stats=mock.Mock(
                return_value={"available": False, "total": "-"}
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "contribution data"):
                update_readme.build_generated_section()


if __name__ == "__main__":
    unittest.main()
