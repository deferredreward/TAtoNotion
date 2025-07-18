#!/usr/bin/env python3
"""
Direct migration of selected Translation Academy articles
"""

import logging
from ta_selective_migration import SelectiveTAMigrator
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migrate_selected.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    # Key articles to migrate
    selected_articles = [
        # Core figures of speech from JIT modules
        'translate/figs-metaphor',
        'translate/figs-simile', 
        'translate/figs-metonymy',
        'translate/figs-hyperbole',
        'translate/figs-irony',
        'translate/figs-rquestion',
        
        # Form and meaning
        'translate/translate-fandm',
        'translate/translate-form',
        'translate/translate-literal',
        'translate/translate-dynamic'
    ]
    
    print(f"Migrating {len(selected_articles)} selected articles:")
    for article in selected_articles:
        print(f"  - {article}")
    
    migrator = SelectiveTAMigrator()
    
    # Run the migration
    results = migrator.migrate_specific_articles(selected_articles)
    
    # Save results
    with open('selected_migration_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print(f"\n{'='*50}")
    print("MIGRATION SUMMARY")
    print(f"{'='*50}")
    print(f"Requested articles: {results['requested_articles']}")
    print(f"Successful migrations: {results['successful_migrations']}")
    print(f"Failed migrations: {results['failed_migrations']}")
    
    if results['not_found']:
        print(f"Articles not found: {len(results['not_found'])}")
        for article in results['not_found']:
            print(f"  - {article}")
    
    if results['migrated_pages']:
        print(f"\nSuccessfully migrated articles:")
        for article, page_id in results['migrated_pages'].items():
            print(f"  - {article}: {page_id}")
    
    print(f"\nResults saved to: selected_migration_results.json")

if __name__ == "__main__":
    main()