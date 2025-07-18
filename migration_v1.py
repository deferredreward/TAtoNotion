#!/usr/bin/env python3
"""
Translation Academy to Notion Database Migration Script

This script migrates Translation Academy content from local files to a Notion database,
preserving the hierarchical structure, relationships, and content organization.
"""

import os
import yaml
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ta_migration.log"),
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

# Constants
TA_BASE_PATH = Path("en_ta")
WIP_PAGE_ID = "1c372d5a-f2de-80e0-8b11-cd7748a1467d"  # from inspection
DATABASE_ID = "340b5f5c-4f57-4a6a-bd21-5e5b30aac26c"  # will try both approaches

class TAMigrator:
    def __init__(self):
        self.sections = {}
        self.articles_data = {}
        self.notion_pages = {}
        self.section_pages = {}
        
    def load_section_config(self, section_name: str) -> Dict:
        """Load configuration for a section (intro, process, translate, checking)."""
        config_path = TA_BASE_PATH / section_name / "config.yaml"
        toc_path = TA_BASE_PATH / section_name / "toc.yaml"
        
        config_data = {}
        toc_data = {}
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
                
        if toc_path.exists():
            with open(toc_path, 'r', encoding='utf-8') as f:
                toc_data = yaml.safe_load(f) or {}
        
        return {
            'config': config_data,
            'toc': toc_data,
            'name': section_name
        }
    
    def load_article_content(self, section_name: str, article_name: str) -> Dict:
        """Load all content files for an article."""
        article_path = TA_BASE_PATH / section_name / article_name
        
        content = {
            'title': '',
            'subtitle': '',
            'content': '',
            'section': section_name,
            'article_id': article_name
        }
        
        # Load title
        title_path = article_path / "title.md"
        if title_path.exists():
            with open(title_path, 'r', encoding='utf-8') as f:
                content['title'] = f.read().strip()
        
        # Load subtitle  
        subtitle_path = article_path / "sub-title.md"
        if subtitle_path.exists():
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                content['subtitle'] = f.read().strip()
        
        # Load main content
        main_path = article_path / "01.md"
        if main_path.exists():
            with open(main_path, 'r', encoding='utf-8') as f:
                content['content'] = f.read().strip()
        
        return content
    
    def get_article_relationships(self, section_name: str, article_name: str) -> Dict:
        """Get dependency and recommendation relationships for an article."""
        config = self.sections.get(section_name, {}).get('config', {})
        
        article_config = config.get(article_name, {})
        
        return {
            'dependencies': article_config.get('dependencies', []),
            'recommended': article_config.get('recommended', []),
            'article_id': article_name,
            'section': section_name
        }
    
    def create_database_entry_properties(self, article_data: Dict, relationships: Dict) -> Dict:
        """Create properties for a database entry based on article data."""
        properties = {
            "Name": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": article_data['title'] or article_data['article_id']}
                    }
                ]
            },
            "Article ID": {
                "rich_text": [
                    {
                        "type": "text", 
                        "text": {"content": article_data['article_id']}
                    }
                ]
            },
            "Section": {
                "select": {
                    "name": article_data['section'].title()
                }
            },
            "Subtitle": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": article_data['subtitle']}
                    }
                ]
            }
        }
        
        # Add dependency and recommendation info if available
        if relationships['dependencies']:
            properties["Dependencies"] = {
                "multi_select": [
                    {"name": dep} for dep in relationships['dependencies'][:10]  # Limit to avoid API limits
                ]
            }
            
        if relationships['recommended']:
            properties["Recommended"] = {
                "multi_select": [
                    {"name": rec} for rec in relationships['recommended'][:10]  # Limit to avoid API limits
                ]
            }
        
        return properties
    
    def create_database_entry(self, article_data: Dict, relationships: Dict) -> Optional[str]:
        """Create a new entry in the Notion database."""
        try:
            properties = self.create_database_entry_properties(article_data, relationships)
            
            # Create the database page
            response = notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=properties
            )
            
            page_id = response['id']
            logger.info(f"Created database entry for {article_data['article_id']}: {page_id}")
            
            # Add content as blocks
            if article_data['content']:
                self.add_content_blocks(page_id, article_data['content'])
            
            return page_id
            
        except Exception as e:
            logger.error(f"Error creating database entry for {article_data['article_id']}: {e}")
            return None
    
    def create_page_entry(self, article_data: Dict, parent_page_id: str) -> Optional[str]:
        """Create a new page under a parent page (fallback approach)."""
        try:
            # Create the page
            response = notion.pages.create(
                parent={"page_id": parent_page_id},
                properties={
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": article_data['title'] or article_data['article_id']}
                            }
                        ]
                    }
                }
            )
            
            page_id = response['id']
            logger.info(f"Created page for {article_data['article_id']}: {page_id}")
            
            # Add all content as blocks
            blocks = []
            
            # Add subtitle if present
            if article_data['subtitle']:
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": article_data['subtitle']}
                            }
                        ]
                    }
                })
            
            # Add main content
            if article_data['content']:
                content_blocks = self.markdown_to_blocks(article_data['content'])
                blocks.extend(content_blocks)
            
            # Add blocks in batches
            if blocks:
                self.add_blocks_in_batches(page_id, blocks)
            
            return page_id
            
        except Exception as e:
            logger.error(f"Error creating page for {article_data['article_id']}: {e}")
            return None
    
    def markdown_to_blocks(self, markdown_content: str) -> List[Dict]:
        """Convert markdown content to Notion blocks."""
        blocks = []
        lines = markdown_content.split('\n')
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                # Empty line - finish current paragraph if any
                if current_paragraph:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": ' '.join(current_paragraph)}
                                }
                            ]
                        }
                    })
                    current_paragraph = []
                continue
            
            # Check for headers
            if line.startswith('### '):
                # Finish current paragraph
                if current_paragraph:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph", 
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": ' '.join(current_paragraph)}
                                }
                            ]
                        }
                    })
                    current_paragraph = []
                
                # Add heading
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": line[4:]}
                            }
                        ]
                    }
                })
            elif line.startswith('## '):
                # Finish current paragraph
                if current_paragraph:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text", 
                                    "text": {"content": ' '.join(current_paragraph)}
                                }
                            ]
                        }
                    })
                    current_paragraph = []
                
                # Add heading
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": line[3:]}
                            }
                        ]
                    }
                })
            elif line.startswith('1. ') or line.startswith('* '):
                # Handle list items - for now, convert to paragraphs
                if current_paragraph:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": ' '.join(current_paragraph)}
                                }
                            ]
                        }
                    })
                    current_paragraph = []
                
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": line[3:] if line.startswith('1. ') else line[2:]}
                            }
                        ]
                    }
                })
            else:
                # Regular text line
                current_paragraph.append(line)
        
        # Finish any remaining paragraph
        if current_paragraph:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": ' '.join(current_paragraph)}
                        }
                    ]
                }
            })
        
        return blocks
    
    def add_blocks_in_batches(self, page_id: str, blocks: List[Dict], batch_size: int = 100):
        """Add blocks to a page in batches to avoid API limits."""
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]
            try:
                notion.blocks.children.append(
                    block_id=page_id,
                    children=batch
                )
                logger.info(f"Added {len(batch)} blocks to page {page_id}")
            except Exception as e:
                logger.error(f"Error adding blocks to page {page_id}: {e}")
    
    def get_or_create_section_page(self, section_name: str) -> Optional[str]:
        """Get or create a section page under the WIP page."""
        if section_name in self.section_pages:
            return self.section_pages[section_name]
        
        try:
            # Search for existing section page
            blocks_response = notion.blocks.children.list(block_id=WIP_PAGE_ID)
            
            for block in blocks_response.get('results', []):
                if block.get('type') == 'child_page':
                    title = block.get('child_page', {}).get('title', '')
                    if title.lower() == section_name.lower():
                        page_id = block['id']
                        self.section_pages[section_name] = page_id
                        logger.info(f"Found existing section page for {section_name}: {page_id}")
                        return page_id
            
            # Create new section page if not found
            response = notion.pages.create(
                parent={"page_id": WIP_PAGE_ID},
                properties={
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": section_name.title()}
                            }
                        ]
                    }
                }
            )
            
            page_id = response['id']
            self.section_pages[section_name] = page_id
            logger.info(f"Created new section page for {section_name}: {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"Error getting/creating section page for {section_name}: {e}")
            return None
    
    def load_all_data(self):
        """Load all Translation Academy data from local files."""
        logger.info("Loading Translation Academy data...")
        
        # Load each section
        for section_name in ['intro', 'process', 'translate', 'checking']:
            section_path = TA_BASE_PATH / section_name
            if not section_path.exists():
                logger.warning(f"Section directory not found: {section_name}")
                continue
            
            # Load section configuration
            self.sections[section_name] = self.load_section_config(section_name)
            logger.info(f"Loaded {section_name} section config")
            
            # Load all articles in this section
            for article_dir in section_path.iterdir():
                if article_dir.is_dir() and article_dir.name not in ['toc.yaml', 'config.yaml']:
                    article_name = article_dir.name
                    
                    # Load article content
                    article_data = self.load_article_content(section_name, article_name)
                    relationships = self.get_article_relationships(section_name, article_name)
                    
                    article_key = f"{section_name}/{article_name}"
                    self.articles_data[article_key] = {
                        'content': article_data,
                        'relationships': relationships
                    }
        
        logger.info(f"Loaded {len(self.articles_data)} articles across {len(self.sections)} sections")
    
    def migrate_to_database(self):
        """Migrate all articles to the Notion database."""
        logger.info("Starting database migration...")
        
        success_count = 0
        error_count = 0
        
        for article_key, article_info in self.articles_data.items():
            article_data = article_info['content']
            relationships = article_info['relationships']
            
            page_id = self.create_database_entry(article_data, relationships)
            
            if page_id:
                self.notion_pages[article_key] = page_id
                success_count += 1
            else:
                error_count += 1
        
        logger.info(f"Database migration complete: {success_count} success, {error_count} errors")
        return success_count, error_count
    
    def migrate_to_pages(self):
        """Migrate all articles to pages (fallback approach)."""
        logger.info("Starting page-based migration...")
        
        success_count = 0
        error_count = 0
        
        # Migrate by section
        for section_name in ['intro', 'process', 'translate', 'checking']:
            section_page_id = self.get_or_create_section_page(section_name)
            if not section_page_id:
                logger.error(f"Could not create section page for {section_name}")
                continue
            
            # Migrate articles for this section
            section_articles = [
                (key, info) for key, info in self.articles_data.items() 
                if info['content']['section'] == section_name
            ]
            
            logger.info(f"Migrating {len(section_articles)} articles for {section_name}")
            
            for article_key, article_info in section_articles:
                article_data = article_info['content']
                
                page_id = self.create_page_entry(article_data, section_page_id)
                
                if page_id:
                    self.notion_pages[article_key] = page_id
                    success_count += 1
                else:
                    error_count += 1
        
        logger.info(f"Page migration complete: {success_count} success, {error_count} errors")
        return success_count, error_count
    
    def run_migration(self, use_database: bool = True):
        """Run the complete migration process."""
        logger.info("Starting Translation Academy migration...")
        
        # Load all data
        self.load_all_data()
        
        if not self.articles_data:
            logger.error("No articles loaded. Exiting.")
            return
        
        # Try database approach first, fall back to pages
        if use_database:
            try:
                success, errors = self.migrate_to_database()
                if success > 0:
                    logger.info(f"Database migration successful: {success} articles migrated")
                    return
                else:
                    logger.warning("Database migration failed, trying page approach...")
            except Exception as e:
                logger.error(f"Database migration failed: {e}")
                logger.info("Falling back to page-based migration...")
        
        # Fall back to page approach
        success, errors = self.migrate_to_pages()
        
        # Save results
        results = {
            'total_articles': len(self.articles_data),
            'successful_migrations': success,
            'failed_migrations': errors,
            'notion_pages': self.notion_pages
        }
        
        with open('migration_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Migration complete! Results saved to migration_results.json")

def main():
    """Main function to run the migration."""
    migrator = TAMigrator()
    migrator.run_migration(use_database=True)

if __name__ == "__main__":
    main()