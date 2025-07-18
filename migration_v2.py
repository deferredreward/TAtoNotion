#!/usr/bin/env python3
"""
Complete Translation Academy to Notion Database Migration Script

This script migrates all Translation Academy content to the comprehensive Notion database,
mapping local content and YAML metadata to the rich database schema.
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
        logging.FileHandler("ta_complete_migration.log"),
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
DATABASE_ID = "340b5f5c-4f57-4a6a-bd21-5e5b30aac26c"

# Manual mappings
MANUAL_MAPPING = {
    'intro': 'Introduction',
    'process': 'Process Manual', 
    'translate': 'Translation Manual',
    'checking': 'Checking Manual'
}

# Content type mappings based on structure
def get_content_type(article_name: str, section_name: str) -> str:
    """Determine content type based on naming patterns."""
    if article_name in ['intro-checking', 'intro-share', 'intro-publishing', 'ta-intro']:
        return 'Section'
    elif article_name.startswith('figs-') or article_name.startswith('grammar-') or article_name.startswith('translate-'):
        return 'Module'
    else:
        return 'Topic'

# Key concepts mapping
def get_key_concepts(article_name: str, content: str) -> List[str]:
    """Determine key concepts based on article content and name."""
    concepts = []
    
    # Figure of speech patterns
    if 'figs-' in article_name or 'metaphor' in content.lower() or 'simile' in content.lower():
        concepts.append('Figures of Speech')
    
    # Grammar patterns  
    if 'grammar-' in article_name or 'verb' in content.lower() or 'sentence' in content.lower():
        concepts.append('Grammar')
    
    # Translation principles
    if any(word in content.lower() for word in ['translation', 'translate', 'meaning', 'accurate']):
        concepts.append('Translation Principles')
    
    # Quality assurance
    if any(word in content.lower() for word in ['check', 'review', 'accuracy', 'quality']):
        concepts.append('Quality Assurance')
    
    # Team management
    if any(word in content.lower() for word in ['team', 'leader', 'collaborate']):
        concepts.append('Team Management')
    
    # Cultural context
    if any(word in content.lower() for word in ['culture', 'cultural', 'context', 'custom']):
        concepts.append('Cultural Context')
    
    # Church involvement
    if any(word in content.lower() for word in ['church', 'pastor', 'leader', 'community']):
        concepts.append('Church Involvement')
    
    # Source texts
    if any(word in content.lower() for word in ['source', 'original', 'hebrew', 'greek', 'manuscript']):
        concepts.append('Source Texts')
    
    return concepts

# Target audience mapping
def get_target_audience(section_name: str, article_name: str, content: str) -> List[str]:
    """Determine target audience based on content."""
    audiences = []
    
    if section_name == 'translate':
        audiences.append('Translators')
    elif section_name == 'checking':
        audiences.append('Checkers')
    elif section_name == 'process':
        audiences.append('Team Leaders')
    
    if any(word in content.lower() for word in ['train', 'teaching', 'learn']):
        audiences.append('Trainers')
    
    if any(word in content.lower() for word in ['church', 'pastor', 'elder']):
        audiences.append('Church Leaders')
    
    # Ensure at least one audience
    if not audiences:
        audiences.append('Translators')
    
    return audiences

# Difficulty level mapping
def get_difficulty_level(article_name: str, dependencies: List[str]) -> str:
    """Determine difficulty based on dependencies and complexity."""
    if len(dependencies) == 0:
        return 'Beginner'
    elif len(dependencies) <= 3:
        return 'Intermediate'
    else:
        return 'Advanced'

class CompleteTAMigrator:
    def __init__(self):
        self.sections = {}
        self.articles_data = {}
        self.notion_pages = {}
        self.section_sequence = {'intro': 1, 'process': 2, 'translate': 3, 'checking': 4}
        
    def load_manifest(self) -> Dict:
        """Load the main manifest.yaml file."""
        manifest_path = TA_BASE_PATH / "manifest.yaml"
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def load_section_config(self, section_name: str) -> Dict:
        """Load configuration for a section."""
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
            'article_id': article_name,
            'directory_path': str(article_path.relative_to(TA_BASE_PATH)),
            'repository_path': f"en_ta/{section_name}/{article_name}"
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
    
    def create_rich_database_properties(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Dict:
        """Create comprehensive properties for the database entry."""
        full_content = f"{article_data['content']}\n{article_data['subtitle']}"
        
        properties = {
            # Core identification
            "Title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": article_data['title'] or article_data['article_id']}
                    }
                ]
            },
            
            # Slug for URL-friendly identifier
            "Slug": {
                "rich_text": [
                    {
                        "type": "text", 
                        "text": {"content": article_data['article_id']}
                    }
                ]
            },
            
            # Manual section
            "Manual": {
                "select": {
                    "name": MANUAL_MAPPING[article_data['section']]
                }
            },
            
            # Content organization
            "Content Type": {
                "select": {
                    "name": get_content_type(article_data['article_id'], article_data['section'])
                }
            },
            
            # Sequence and organization
            "Sequence Order": {
                "number": sequence_order
            },
            
            # Paths and references
            "Directory Path": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": article_data['directory_path']}
                    }
                ]
            },
            
            "Repository Path": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": article_data['repository_path']}
                    }
                ]
            },
            
            # Content details
            "Summary": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": article_data['subtitle']}
                    }
                ]
            },
            
            # Learning objective (from content analysis)
            "Learning Objective": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": self.extract_learning_objective(full_content)}
                    }
                ]
            },
            
            # YAML configuration
            "YAML Config": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": json.dumps({
                            'dependencies': relationships['dependencies'],
                            'recommended': relationships['recommended']
                        }, indent=2)}
                    }
                ]
            },
            
            # Difficulty and concepts
            "Difficulty Level": {
                "select": {
                    "name": get_difficulty_level(article_data['article_id'], relationships['dependencies'])
                }
            },
            
            "Key Concepts": {
                "multi_select": [
                    {"name": concept} for concept in get_key_concepts(article_data['article_id'], full_content)
                ]
            },
            
            # Target audience
            "Target Audience": {
                "multi_select": [
                    {"name": audience} for audience in get_target_audience(
                        article_data['section'], article_data['article_id'], full_content
                    )
                ]
            },
            
            # Status
            "Status": {
                "select": {
                    "name": "Complete" if article_data['content'] else "Needs Review"
                }
            },
            
            # Translation status
            "Translation Status": {
                "multi_select": [
                    {"name": "Available in GL"}
                ]
            }
        }
        
        return properties
    
    def extract_learning_objective(self, content: str) -> str:
        """Extract or generate a learning objective from content."""
        # Look for explicit learning objectives in content
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            if any(keyword in line.lower() for keyword in ['learn', 'understand', 'objective', 'goal']):
                return line.strip()[:200]  # Limit length
        
        # Generate from first substantial paragraph
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.startswith('#')]
        if paragraphs:
            return paragraphs[0][:200] + "..." if len(paragraphs[0]) > 200 else paragraphs[0]
        
        return "Learn about translation concepts and techniques."
    
    def create_database_entry(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Optional[str]:
        """Create a database entry with comprehensive properties."""
        try:
            properties = self.create_rich_database_properties(article_data, relationships, sequence_order)
            
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
            logger.error(f"Error details: {str(e)}")
            return None
    
    def add_content_blocks(self, page_id: str, content: str):
        """Add content as blocks to the page."""
        try:
            blocks = self.markdown_to_blocks(content)
            if blocks:
                # Add blocks in batches to avoid API limits
                batch_size = 100
                for i in range(0, len(blocks), batch_size):
                    batch = blocks[i:i + batch_size]
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=batch
                    )
                logger.info(f"Added {len(blocks)} blocks to {page_id}")
        except Exception as e:
            logger.error(f"Error adding content blocks: {e}")
    
    def markdown_to_blocks(self, markdown_content: str) -> List[Dict]:
        """Convert markdown content to Notion blocks."""
        blocks = []
        lines = markdown_content.split('\n')
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                # Empty line - finish current paragraph
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
            
            # Handle headers and special formatting
            if line.startswith('### '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                    }
                })
            elif line.startswith('## '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "heading_2", 
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith('1. '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith('* ') or line.startswith('- '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            else:
                current_paragraph.append(line)
        
        # Finish any remaining paragraph
        self._finish_paragraph(blocks, current_paragraph)
        
        return blocks
    
    def _finish_paragraph(self, blocks: List[Dict], current_paragraph: List[str]):
        """Helper to finish current paragraph."""
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
    
    def load_all_data(self):
        """Load all Translation Academy data."""
        logger.info("Loading Translation Academy data...")
        
        # Load manifest
        manifest = self.load_manifest()
        
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
                if (article_dir.is_dir() and 
                    article_dir.name not in ['toc.yaml', 'config.yaml'] and
                    not article_dir.name.startswith('.')):
                    
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
    
    def run_migration(self, test_only: bool = False, limit: int = None):
        """Run the complete migration process."""
        logger.info("Starting comprehensive Translation Academy migration...")
        
        # Load all data
        self.load_all_data()
        
        if not self.articles_data:
            logger.error("No articles loaded. Exiting.")
            return
        
        # Sort articles for consistent ordering
        sorted_articles = sorted(self.articles_data.items())
        
        # Limit for testing
        if test_only and limit:
            sorted_articles = sorted_articles[:limit]
            logger.info(f"Test mode: limiting to {limit} articles")
        
        success_count = 0
        error_count = 0
        
        # Migrate all articles
        for i, (article_key, article_info) in enumerate(sorted_articles, 1):
            article_data = article_info['content']
            relationships = article_info['relationships']
            
            logger.info(f"Migrating ({i}/{len(sorted_articles)}): {article_key}")
            
            page_id = self.create_database_entry(article_data, relationships, i)
            
            if page_id:
                self.notion_pages[article_key] = page_id
                success_count += 1
            else:
                error_count += 1
        
        # Save results
        results = {
            'total_articles': len(sorted_articles),
            'successful_migrations': success_count,
            'failed_migrations': error_count,
            'notion_pages': self.notion_pages,
            'test_mode': test_only
        }
        
        result_file = 'test_migration_results.json' if test_only else 'complete_migration_results.json'
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Migration complete! {success_count} success, {error_count} errors")
        logger.info(f"Results saved to: {result_file}")

def main():
    """Main function to run the migration."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate Translation Academy to Notion DB')
    parser.add_argument('--test', action='store_true', help='Run in test mode with limited articles')
    parser.add_argument('--limit', type=int, default=5, help='Limit number of articles in test mode')
    
    args = parser.parse_args()
    
    migrator = CompleteTAMigrator()
    migrator.run_migration(test_only=args.test, limit=args.limit if args.test else None)

if __name__ == "__main__":
    main()