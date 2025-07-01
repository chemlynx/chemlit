"""Script to help migrate endpoint code."""

import re
from pathlib import Path
from typing import List


class EndpointMigrator:
    """Helps migrate endpoint code to use ArticleService."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.backup_dir = project_root / "migration" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_endpoint_file(self, file_path: Path) -> Path:
        """Create backup of endpoint file before migration."""
        backup_path = self.backup_dir / f"{file_path.name}.backup"
        backup_path.write_text(file_path.read_text())
        print(f"✅ Backed up {file_path} to {backup_path}")
        return backup_path

    def find_migration_opportunities(self, file_path: Path) -> List[dict[str, any]]:
        """Find code patterns that can be migrated."""
        content = file_path.read_text()
        opportunities = []

        # Pattern: CrossRef service usage
        crossref_pattern = r"CrossRefService\(\).*?\.fetch_and_convert_article"
        matches = re.finditer(crossref_pattern, content, re.DOTALL)
        for match in matches:
            opportunities.append(
                {
                    "type": "crossref_usage",
                    "line": content[: match.start()].count("\n") + 1,
                    "pattern": match.group(),
                    "suggestion": "Replace with ArticleService.register_article(fetch_metadata=True)",
                }
            )

        # Pattern: ArticleCRUD.create usage
        crud_pattern = r"ArticleCRUD\.create\([^)]+\)"
        matches = re.finditer(crud_pattern, content)
        for match in matches:
            opportunities.append(
                {
                    "type": "crud_usage",
                    "line": content[: match.start()].count("\n") + 1,
                    "pattern": match.group(),
                    "suggestion": "Replace with ArticleService.register_article()",
                }
            )

        return opportunities

    def generate_migration_report(self) -> str:
        """Generate a migration report for all endpoint files."""
        endpoints_dir = (
            self.project_root / "src" / "chemlit_extractor" / "api" / "v1" / "endpoints"
        )
        report_lines = ["# Endpoint Migration Report\n"]

        for py_file in endpoints_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            opportunities = self.find_migration_opportunities(py_file)

            report_lines.append(f"## {py_file.name}\n")

            if opportunities:
                report_lines.append(
                    f"Found {len(opportunities)} migration opportunities:\n"
                )
                for opp in opportunities:
                    report_lines.append(f"- Line {opp['line']}: {opp['type']}")
                    report_lines.append(f"  - Current: `{opp['pattern'][:80]}...`")
                    report_lines.append(f"  - Suggestion: {opp['suggestion']}\n")
            else:
                report_lines.append("✅ No migration opportunities found.\n")

        return "\n".join(report_lines)
