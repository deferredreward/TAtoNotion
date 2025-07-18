#!/usr/bin/env python3
"""
Selective Translation Academy Migration Script

This script allows you to migrate specific Translation Academy articles
by providing a list of article identifiers.
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from notion_client import Client

# Import from our complete migration script
from ta_to_notion_complete import CompleteTAMigrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ta_selective_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SelectiveTAMigrator(CompleteTAMigrator):
    def __init__(self):
        super().__init__()
        
    def find_articles_by_pattern(self, patterns: List[str]) -> List[str]:
        """Find articles matching given patterns."""
        if not self.articles_data:
            self.load_all_data()
        
        matching_articles = []
        
        for article_key in self.articles_data.keys():
            section, article_name = article_key.split('/', 1)
            
            for pattern in patterns:
                if (pattern.lower() in article_name.lower() or 
                    pattern.lower() in article_key.lower()):
                    matching_articles.append(article_key)
                    break
        
        return sorted(set(matching_articles))
    
    def list_available_articles(self, filter_pattern: str = None) -> List[str]:
        """List all available articles, optionally filtered by pattern."""
        if not self.articles_data:
            self.load_all_data()
        
        all_articles = list(self.articles_data.keys())
        
        if filter_pattern:
            filtered = [
                article for article in all_articles 
                if filter_pattern.lower() in article.lower()
            ]
            return sorted(filtered)
        
        return sorted(all_articles)
    
    def migrate_specific_articles(self, article_list: List[str]) -> Dict:
        """Migrate only the specified articles."""
        if not self.articles_data:
            self.load_all_data()
        
        logger.info(f"Starting migration of {len(article_list)} specific articles...")
        
        success_count = 0
        error_count = 0
        migrated_pages = {}
        not_found = []
        
        for i, article_key in enumerate(article_list, 1):
            if article_key not in self.articles_data:
                logger.warning(f"Article not found: {article_key}")
                not_found.append(article_key)
                continue
            
            article_info = self.articles_data[article_key]
            article_data = article_info['content']
            relationships = article_info['relationships']
            
            logger.info(f"Migrating ({i}/{len(article_list)}): {article_key}")
            logger.info(f"  Title: {article_data['title']}")
            
            page_id = self.create_database_entry(article_data, relationships, i)
            
            if page_id:
                migrated_pages[article_key] = page_id
                success_count += 1
                logger.info(f"  ✅ Success: {page_id}")
            else:
                error_count += 1
                logger.error(f"  ❌ Failed")
        
        results = {
            'requested_articles': len(article_list),
            'successful_migrations': success_count,
            'failed_migrations': error_count,
            'not_found': not_found,
            'migrated_pages': migrated_pages
        }
        
        return results

def main():
    """Main function with different modes of operation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Selectively migrate Translation Academy articles')
    parser.add_argument('--list', action='store_true', help='List all available articles')
    parser.add_argument('--filter', type=str, help='Filter articles by pattern when listing')
    parser.add_argument('--search', nargs='+', help='Search for articles matching patterns')
    parser.add_argument('--articles', nargs='+', help='Specific articles to migrate (section/article format)')
    parser.add_argument('--jit', action='store_true', help='Migrate just-in-time figures of speech modules')
    parser.add_argument('--form-meaning', action='store_true', help='Migrate form and meaning related articles')
    
    args = parser.parse_args()
    
    migrator = SelectiveTAMigrator()
    
    if args.list:
        articles = migrator.list_available_articles(args.filter)
        print(f"\nFound {len(articles)} articles:")
        for article in articles:
            print(f"  {article}")
        return
    
    if args.search:
        articles = migrator.find_articles_by_pattern(args.search)
        print(f"\nFound {len(articles)} articles matching patterns {args.search}:")
        for article in articles:
            print(f"  {article}")
        return
    
    # Define article sets
    articles_to_migrate = []
    
    if args.jit:
        # Just-in-time figures of speech modules
        jit_patterns = ['figs-metaphor', 'figs-simile', 'figs-metonymy', 'figs-synecdoche', 
                       'figs-hyperbole', 'figs-irony', 'figs-litotes', 'figs-rquestion']
        jit_articles = migrator.find_articles_by_pattern(jit_patterns)
        articles_to_migrate.extend(jit_articles)
        print(f"Added {len(jit_articles)} JIT figures of speech articles")
    
    if args.form_meaning:
        # Form and meaning related articles
        form_meaning_patterns = ['translate-fandm', 'translate-form', 'translate-literal', 
                               'translate-dynamic', 'translate-problem']
        fm_articles = migrator.find_articles_by_pattern(form_meaning_patterns)
        articles_to_migrate.extend(fm_articles)
        print(f"Added {len(fm_articles)} form and meaning articles")
    
    if args.articles:
        articles_to_migrate.extend(args.articles)
        print(f"Added {len(args.articles)} specified articles")
    
    # Remove duplicates while preserving order
    articles_to_migrate = list(dict.fromkeys(articles_to_migrate))
    
    if not articles_to_migrate:
        print("No articles specified for migration. Use --help for options.")
        return
    
    print(f"\nMigrating {len(articles_to_migrate)} articles:")
    for article in articles_to_migrate:
        print(f"  {article}")
    
    # Confirm before proceeding
    response = input(f"\nProceed with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return
    
    # Run migration
    results = migrator.migrate_specific_articles(articles_to_migrate)
    
    # Save results
    with open('selective_migration_results.json', 'w') as f:
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
    
    print(f"\nResults saved to: selective_migration_results.json")

if __name__ == "__main__":
    main()