#!/usr/bin/env python3
"""
Update Parent Section relationships from TOC YAML structure

This script parses the toc.yaml files to establish hierarchical Parent Section
relationships in the Translation Academy database.
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("update_parent_sections.log"),
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
TA_BASE_PATH = Path("en_ta")

class ParentSectionUpdater:
    def __init__(self):
        self.article_to_page_id = {}
        self.section_hierarchies = {}
        self.parent_child_relationships = {}
        
    def load_existing_pages(self):
        """Load all existing pages from the database."""
        logger.info("Loading existing pages from database...")
        
        try:
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
                
                has_more = response.get('has_more', False)
                next_cursor = response.get('next_cursor')
            
            logger.info(f"Loaded {len(self.article_to_page_id)} existing pages")
            return True
            
        except Exception as e:
            logger.error(f"Error loading existing pages: {e}")
            return False
    
    def parse_toc_hierarchy(self, section_name: str) -> Dict:
        """Parse the toc.yaml file for a section to extract hierarchy."""
        toc_path = TA_BASE_PATH / section_name / "toc.yaml"
        
        if not toc_path.exists():
            logger.warning(f"TOC file not found: {toc_path}")
            return {}
        
        try:
            with open(toc_path, 'r', encoding='utf-8') as f:
                toc_data = yaml.safe_load(f) or {}
            
            hierarchy = {}
            self._parse_toc_sections(toc_data.get('sections', []), hierarchy, section_name)
            
            return hierarchy
            
        except Exception as e:
            logger.error(f"Error parsing TOC for {section_name}: {e}")
            return {}
    
    def _parse_toc_sections(self, sections: List[Dict], hierarchy: Dict, section_name: str, parent_link: str = None):
        """Recursively parse TOC sections to build hierarchy."""
        for section in sections:
            link = section.get('link')
            title = section.get('title', '')
            child_sections = section.get('sections', [])
            
            if link:
                article_key = f"{section_name}/{link}"
                
                # Store the parent relationship
                if parent_link:
                    parent_key = f"{section_name}/{parent_link}"
                    hierarchy[article_key] = parent_key
                    
                    # Track parent->child relationships for logging
                    if parent_key not in self.parent_child_relationships:
                        self.parent_child_relationships[parent_key] = []
                    self.parent_child_relationships[parent_key].append(article_key)
                
                # Process child sections
                if child_sections:
                    self._parse_toc_sections(child_sections, hierarchy, section_name, link)
            
            # Handle sections without links but with children
            elif child_sections and parent_link:
                self._parse_toc_sections(child_sections, hierarchy, section_name, parent_link)
            elif child_sections:
                # Top-level section without link - process children without parent
                self._parse_toc_sections(child_sections, hierarchy, section_name, None)
    
    def build_all_hierarchies(self):
        """Build hierarchies for all sections."""
        logger.info("Building TOC hierarchies for all sections...")
        
        for section_name in ['intro', 'process', 'translate', 'checking']:
            hierarchy = self.parse_toc_hierarchy(section_name)
            self.section_hierarchies[section_name] = hierarchy
            
            logger.info(f"Built hierarchy for {section_name}: {len(hierarchy)} parent-child relationships")
    
    def update_parent_section_for_article(self, article_key: str) -> bool:
        """Update the Parent Section for a single article."""
        if article_key not in self.article_to_page_id:
            logger.warning(f"Article not found in database: {article_key}")
            return False
        
        page_id = self.article_to_page_id[article_key]
        section_name = article_key.split('/')[0]
        
        # Check if this article has a parent in the hierarchy
        hierarchy = self.section_hierarchies.get(section_name, {})
        parent_article_key = hierarchy.get(article_key)
        
        if not parent_article_key:
            logger.debug(f"No parent found for {article_key}")
            return True  # Not an error, just no parent
        
        # Check if parent article exists in database
        if parent_article_key not in self.article_to_page_id:
            logger.debug(f"Parent article not in database: {parent_article_key} for {article_key}")
            return True  # Not an error, parent just not migrated yet
        
        parent_page_id = self.article_to_page_id[parent_article_key]
        
        # Update the Parent Section relationship
        try:
            notion.pages.update(
                page_id=page_id,
                properties={
                    "Parent Section": {
                        "relation": [{"id": parent_page_id}]
                    }
                }
            )
            logger.info(f"Updated parent section for {article_key} -> {parent_article_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating parent section for {article_key}: {e}")
            return False
    
    def update_all_parent_sections(self, article_list: List[str] = None):
        """Update Parent Section relationships for all or specified articles."""
        if not self.load_existing_pages():
            logger.error("Failed to load existing pages")
            return
        
        # Build hierarchies from TOC files
        self.build_all_hierarchies()
        
        # Show hierarchy summary
        logger.info("TOC Hierarchy Summary:")
        for section_name, hierarchy in self.section_hierarchies.items():
            logger.info(f"  {section_name}: {len(hierarchy)} parent-child relationships")
            
            # Show some examples
            example_count = 0
            for child, parent in hierarchy.items():
                if example_count < 3:  # Show first 3 examples
                    child_id = child.split('/')[-1]
                    parent_id = parent.split('/')[-1]
                    logger.info(f"    {child_id} -> {parent_id}")
                    example_count += 1
                elif example_count == 3:
                    logger.info(f"    ... and {len(hierarchy) - 3} more")
                    break
        
        # Determine which articles to update
        if article_list:
            articles_to_update = article_list
        else:
            articles_to_update = list(self.article_to_page_id.keys())
        
        logger.info(f"Updating Parent Section for {len(articles_to_update)} articles...")
        
        success_count = 0
        error_count = 0
        updated_count = 0
        
        for i, article_key in enumerate(articles_to_update, 1):
            logger.debug(f"Processing ({i}/{len(articles_to_update)}): {article_key}")
            
            # Check if this article has a parent relationship to set
            section_name = article_key.split('/')[0]
            hierarchy = self.section_hierarchies.get(section_name, {})
            parent_article_key = hierarchy.get(article_key)
            
            if parent_article_key and parent_article_key in self.article_to_page_id:
                if self.update_parent_section_for_article(article_key):
                    success_count += 1
                    updated_count += 1
                else:
                    error_count += 1
            else:
                success_count += 1  # No error, just no parent to set
        
        logger.info(f"Parent Section updates complete: {updated_count} updated, {success_count - updated_count} no parent, {error_count} errors")
        
        # Save results
        results = {
            'total_articles': len(articles_to_update),
            'articles_updated': updated_count,
            'articles_no_parent': success_count - updated_count,
            'failed_updates': error_count,
            'hierarchies': self.section_hierarchies,
            'parent_child_relationships': self.parent_child_relationships
        }
        
        with open('parent_section_update_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        return results

def main():
    """Main function to update parent sections."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Parent Section relationships from TOC hierarchy')
    parser.add_argument('--articles', nargs='+', help='Specific articles to update (section/article format)')
    parser.add_argument('--all', action='store_true', help='Update all articles in the database')
    
    args = parser.parse_args()
    
    updater = ParentSectionUpdater()
    
    if args.all:
        logger.info("Updating Parent Section for ALL articles in the database")
        updater.update_all_parent_sections()
    elif args.articles:
        logger.info(f"Updating Parent Section for {len(args.articles)} specified articles")
        updater.update_all_parent_sections(args.articles)
    else:
        # Default: update the recently migrated articles
        recently_migrated = [
            'translate/figs-metaphor',
            'translate/figs-simile', 
            'translate/figs-metonymy',
            'translate/figs-hyperbole',
            'translate/figs-irony',
            'translate/figs-rquestion',
            'translate/translate-fandm',
            'translate/translate-form',
            'translate/translate-literal',
            'translate/translate-dynamic'
        ]
        
        logger.info("Updating Parent Section for recently migrated articles")
        updater.update_all_parent_sections(recently_migrated)

if __name__ == "__main__":
    main()