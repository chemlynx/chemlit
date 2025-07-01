"""Post-migration cleanup script."""

from pathlib import Path
import shutil


def cleanup_migration_artifacts(project_root: Path, confirm: bool = False):
    """Clean up migration artifacts after successful migration."""

    migration_dir = project_root / "migration"

    if not confirm:
        print("⚠️  This will permanently delete migration artifacts!")
        print(f"   Directory: {migration_dir}")
        response = input("   Continue? (y/N): ")
        if response.lower() != "y":
            print("❌ Cleanup cancelled")
            return

    if migration_dir.exists():
        # Keep backups but remove helpers and scripts
        backups_dir = migration_dir / "backups"
        if backups_dir.exists():
            print(f"📦 Keeping backups in {backups_dir}")

        # Remove helper and script directories
        for subdir in ["helpers", "scripts", "tests"]:
            subdir_path = migration_dir / subdir
            if subdir_path.exists():
                shutil.rmtree(subdir_path)
                print(f"🗑️  Removed {subdir_path}")

        print("✅ Migration cleanup complete!")
        print("💡 You can now remove the migration/ directory entirely if desired")
    else:
        print("ℹ️  No migration directory found")
