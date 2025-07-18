#!/usr/bin/env python3
"""
Recovery script to restore damaged pages by re-migrating specific articles.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client

# Add the migration_v8 module to the path
sys.path.append('.')
from migration_v8 import FinalFixedTAMigrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("page_recovery.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def find_page_by_title(title: str):
    """Find a page in the database by title."""
    try:
        response = notion.databases.query(
            database_id=DATABASE_ID,
            filter={
                "property": "Title",
                "title": {
                    "equals": title
                }
            }
        )
        
        if response["results"]:
            return response["results"][0]
        return None
        
    except Exception as e:
        logger.error(f"Error finding page '{title}': {e}")
        return None

def get_page_content(page_id: str):
    """Get all content blocks from a page."""
    try:
        blocks = []
        start_cursor = None
        
        while True:
            if start_cursor:
                response = notion.blocks.children.list(
                    block_id=page_id,
                    start_cursor=start_cursor
                )
            else:
                response = notion.blocks.children.list(block_id=page_id)
            
            blocks.extend(response["results"])
            
            if not response["has_more"]:
                break
            
            start_cursor = response["next_cursor"]
        
        return blocks
        
    except Exception as e:
        logger.error(f"Error getting page content: {e}")
        return []

def check_page_status(title: str):
    """Check if a page exists and if it's empty."""
    logger.info(f"Checking status of page: {title}")
    
    page = find_page_by_title(title)
    if not page:
        logger.error(f"Page '{title}' not found in database")
        return None
    
    page_id = page["id"]
    blocks = get_page_content(page_id)
    
    logger.info(f"Page '{title}' has {len(blocks)} blocks")
    
    if len(blocks) == 0:
        logger.warning(f"Page '{title}' is EMPTY - needs recovery")
        return {"page": page, "status": "empty", "blocks": 0}
    else:
        logger.info(f"Page '{title}' has content")
        return {"page": page, "status": "has_content", "blocks": len(blocks)}

def recover_page(article_path: str):
    """Recover a damaged page by re-migrating the article."""
    logger.info(f"Starting recovery for article: {article_path}")
    
    # Initialize migrator
    migrator = FinalFixedTAMigrator()
    
    # Check if article exists
    article_file = Path(f"en_ta/{article_path}/01.md")
    if not article_file.exists():
        logger.error(f"Article file not found: {article_file}")
        return False
    
    # Find the existing page
    title = article_path.split('/')[-1].replace('-', ' ').title()
    page_info = check_page_status(title)
    
    if not page_info:
        logger.error(f"Could not find page for {title}")
        return False
    
    if page_info["status"] != "empty":
        logger.info(f"Page '{title}' is not empty, skipping recovery")
        return True
    
    # Re-migrate the article content
    try:
        logger.info(f"Re-migrating content for: {title}")
        
        # Read the article content
        with open(article_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Create article data structure
        article_data = {
            'section': article_path.split('/')[0],
            'article_id': article_path.split('/')[1],
            'title': title,
            'content': content
        }
        
        # Get page ID
        page_id = page_info["page"]["id"]
        
        # Process the content and add blocks
        blocks = migrator.process_markdown_content(content)
        
        # Add blocks to the page
        if blocks:
            notion.blocks.children.append(
                block_id=page_id,
                children=blocks
            )
            
            logger.info(f"Successfully recovered page '{title}' with {len(blocks)} blocks")
            return True
        else:
            logger.warning(f"No blocks generated for {title}")
            return False
        
    except Exception as e:
        logger.error(f"Error recovering page '{title}': {e}")
        return False

def main():
    """Main recovery function."""
    if len(sys.argv) < 2:
        logger.info("Usage: python recover_damaged_page.py <article_path>")
        logger.info("Example: python recover_damaged_page.py intro/finding-answers")
        return
    
    article_path = sys.argv[1]
    
    logger.info(f"Starting page recovery for: {article_path}")
    
    if recover_page(article_path):
        logger.info("Page recovery completed successfully")
    else:
        logger.error("Page recovery failed")

if __name__ == "__main__":
    main()