#!/usr/bin/env python3
"""
Update relationships in the Translation Academy Notion database

This script updates the Parent Section, Prerequisites, and Related Topics
relation fields after articles have been migrated to the database.
"""

import os
import json
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv
from notion_client import Client
from migration_v2 import CompleteTAMigrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("update_relationships.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    logger.error("NOTION_API_KEY not found in .env file")
    exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

DATABASE_ID = "340b5f5c-4f57-4a6a-bd21-5e5b30aac26c"

class RelationshipUpdater:
    def __init__(self):
        self.migrator = CompleteTAMigrator()
        self.article_to_page_id = {}
        self.section_pages = {}
        
    def load_existing_pages(self):
        """Load all existing pages from the database to build article->page_id mapping."""
        logger.info("Loading existing pages from database...")
        
        try:
            # Query all pages in the database
            has_more = True
            next_cursor = None
            
            while has_more:
                query_params = {
                    "database_id": DATABASE_ID,
                    "page_size": 100
                }
                
                if next_cursor:
                    query_params["start_cursor"] = next_cursor
                
                response = notion.databases.query(**query_params)
                
                for page in response.get('results', []):
                    # Get the slug/article ID from properties
                    slug_prop = page.get('properties', {}).get('Slug', {})
                    slug_rich_text = slug_prop.get('rich_text', [])
                    
                    if slug_rich_text:
                        article_id = slug_rich_text[0].get('plain_text', '')
                        
                        # Get the manual/section
                        manual_prop = page.get('properties', {}).get('Manual', {})
                        manual_select = manual_prop.get('select', {})
                        manual_name = manual_select.get('name', '') if manual_select else ''
                        
                        # Map manual name back to section
                        section_mapping = {
                            'Introduction': 'intro',
                            'Process Manual': 'process', 
                            'Translation Manual': 'translate',
                            'Checking Manual': 'checking'
                        }
                        section = section_mapping.get(manual_name, '')
                        
                        if section and article_id:
                            article_key = f"{section}/{article_id}"
                            self.article_to_page_id[article_key] = page['id']
                            
                            # Track section pages for parent relationships
                            if article_key not in self.section_pages:
                                self.section_pages[section] = []
                            self.section_pages[section].append(page['id'])
                
                has_more = response.get('has_more', False)
                next_cursor = response.get('next_cursor')
            
            logger.info(f"Loaded {len(self.article_to_page_id)} existing pages")
            return True
            
        except Exception as e:
            logger.error(f"Error loading existing pages: {e}")
            return False
    
    def find_related_page_id(self, article_id: str, current_section: str = None) -> Optional[str]:
        """Find the page ID for a related article by ID."""
        # First try exact match with current section
        if current_section:
            full_key = f"{current_section}/{article_id}"
            if full_key in self.article_to_page_id:
                return self.article_to_page_id[full_key]
        
        # Try all sections
        for section in ['intro', 'process', 'translate', 'checking']:
            full_key = f"{section}/{article_id}"
            if full_key in self.article_to_page_id:
                return self.article_to_page_id[full_key]
        
        return None
    
    def update_article_relationships(self, article_key: str) -> bool:
        """Update relationships for a single article."""
        if article_key not in self.article_to_page_id:
            logger.warning(f"Article not found in database: {article_key}")
            return False
        
        page_id = self.article_to_page_id[article_key]
        section, article_id = article_key.split('/', 1)
        
        # Get article data
        if not self.migrator.articles_data:
            self.migrator.load_all_data()
        
        if article_key not in self.migrator.articles_data:
            logger.warning(f"Article data not found: {article_key}")
            return False
        
        article_info = self.migrator.articles_data[article_key]
        relationships = article_info['relationships']
        
        # Build relationship updates
        property_updates = {}
        
        # Prerequisites - relation to other articles
        if relationships['dependencies']:
            prerequisite_ids = []
            for dep_id in relationships['dependencies']:
                related_page_id = self.find_related_page_id(dep_id, section)
                if related_page_id:
                    prerequisite_ids.append({"id": related_page_id})
                else:
                    logger.debug(f"Prerequisite not found: {dep_id} for {article_key}")
            
            if prerequisite_ids:
                property_updates["Prerequisites"] = {
                    "relation": prerequisite_ids
                }
        
        # Related Topics - relation to recommended articles
        if relationships['recommended']:
            related_ids = []
            for rec_id in relationships['recommended']:
                related_page_id = self.find_related_page_id(rec_id, section)
                if related_page_id:
                    related_ids.append({"id": related_page_id})
                else:
                    logger.debug(f"Related topic not found: {rec_id} for {article_key}")
            
            if related_ids:
                property_updates["Related Topics"] = {
                    "relation": related_ids
                }
        
        # Parent Section - relation to section parent (for now, we'll skip this as it's complex)
        # This would require creating section-level entries or using a different approach
        
        # Update the page if we have any relationships to update
        if property_updates:
            try:
                notion.pages.update(
                    page_id=page_id,
                    properties=property_updates
                )
                logger.info(f"Updated relationships for {article_key}")
                return True
            except Exception as e:
                logger.error(f"Error updating relationships for {article_key}: {e}")
                return False
        else:
            logger.info(f"No relationships to update for {article_key}")
            return True
    
    def update_all_relationships(self, article_list: List[str] = None):
        """Update relationships for all articles or a specific list."""
        if not self.load_existing_pages():
            logger.error("Failed to load existing pages")
            return
        
        # Load article data
        self.migrator.load_all_data()
        
        # Determine which articles to update
        if article_list:
            articles_to_update = article_list
        else:
            articles_to_update = list(self.article_to_page_id.keys())
        
        logger.info(f"Updating relationships for {len(articles_to_update)} articles...")
        
        success_count = 0
        error_count = 0
        
        for i, article_key in enumerate(articles_to_update, 1):
            logger.info(f"Updating ({i}/{len(articles_to_update)}): {article_key}")
            
            if self.update_article_relationships(article_key):
                success_count += 1
            else:
                error_count += 1
        
        logger.info(f"Relationship updates complete: {success_count} success, {error_count} errors")
        
        # Save results
        results = {
            'total_articles': len(articles_to_update),
            'successful_updates': success_count,
            'failed_updates': error_count,
            'article_to_page_mapping': self.article_to_page_id
        }
        
        with open('relationship_update_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        return results

def load_test_articles() -> List[str]:
    """Load test articles from test_articles.txt file."""
    try:
        with open('test_articles.txt', 'r') as f:
            articles = [line.strip() for line in f if line.strip()]
        return articles
    except FileNotFoundError:
        logger.warning("test_articles.txt not found, using default test articles")
        return ['translate/translate-process']
    except Exception as e:
        logger.error(f"Error reading test_articles.txt: {e}")
        return ['translate/translate-process']

def main():
    """Main function to update relationships."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Translation Academy article relationships')
    parser.add_argument('--articles', nargs='+', help='Specific articles to update (section/article format)')
    parser.add_argument('--test', action='store_true', help='Update only test articles from test_articles.txt')
    parser.add_argument('--all', action='store_true', help='Update all articles in the database (default behavior)')
    
    args = parser.parse_args()
    
    updater = RelationshipUpdater()
    
    if args.test:
        test_articles = load_test_articles()
        logger.info(f"Updating relationships for {len(test_articles)} test articles")
        updater.update_all_relationships(test_articles)
    elif args.articles:
        logger.info(f"Updating relationships for {len(args.articles)} specified articles")
        updater.update_all_relationships(args.articles)
    else:
        # Default: update all articles in the database
        logger.info("Updating relationships for ALL articles in the database (default)")
        updater.update_all_relationships()

if __name__ == "__main__":
    main()