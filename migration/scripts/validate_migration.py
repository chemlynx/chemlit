"""Script to validate migration success."""

from migration.helpers.validation import MigrationValidator
from migration.helpers.data_migration import DataMigrationHelper


def main():
    """Run full migration validation."""
    print("🔍 Starting migration validation...\n")

    # 1. Validate existing data compatibility
    print("1. Validating existing articles...")
    article_validation = DataMigrationHelper.validate_existing_articles()
    print(f"   ✅ Validated {article_validation['validated_count']} articles")
    print(f"   📊 Success rate: {article_validation['success_rate']:.1%}")
    if article_validation["issues"]:
        print(f"   ⚠️  Issues found: {len(article_validation['issues'])}")
        for issue in article_validation["issues"][:5]:  # Show first 5
            print(f"      - {issue}")

    # 2. Check file structure compatibility
    print("\n2. Checking file structure...")
    file_validation = DataMigrationHelper.check_file_structure_compatibility()
    if file_validation["compatible"]:
        print("   ✅ File structure is compatible")
    else:
        print(f"   ❌ File structure issues: {len(file_validation['issues'])}")
        for issue in file_validation["issues"]:
            print(f"      - {issue}")

    # 3. Test API endpoints
    print("\n3. Testing API endpoints...")
    api_validation = MigrationValidator.test_api_compatibility()
    print(
        f"   ✅ {api_validation['successful_endpoints']}/{api_validation['total_endpoints']} endpoints working"
    )
    print(f"   📊 Success rate: {api_validation['success_rate']:.1%}")

    # 4. Test service functionality
    print("\n4. Testing ArticleService...")
    service_validation = MigrationValidator.test_service_functionality()
    if "error" not in service_validation:
        print("   ✅ ArticleService functioning correctly")
    else:
        print(f"   ❌ ArticleService error: {service_validation['error']['error']}")

    print("\n🎉 Migration validation complete!")


if __name__ == "__main__":
    main()
