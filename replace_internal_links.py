#!/usr/bin/env python3
"""
Replace Internal Links in Notion Database

This script scans all pages in the Translation Academy Notion database
and replaces relative file links with proper Notion page links.
"""

import os
import sys
import re
import time
import logging
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("replace_internal_links.log"),
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

class LinkReplacer:
    def __init__(self):
        self.page_map = {}  # Maps article paths to page IDs
        self.updated_pages = 0
        self.total_links_replaced = 0
        
    def load_page_mapping(self):
        """Load all pages and create a mapping from article paths to page IDs."""
        logger.info("Loading page mapping from database...")
        
        try:
            all_pages = []
            start_cursor = None
            
            while True:
                if start_cursor:
                    response = notion.databases.query(
                        database_id=DATABASE_ID,
                        start_cursor=start_cursor
                    )
                else:
                    response = notion.databases.query(database_id=DATABASE_ID)
                
                all_pages.extend(response["results"])
                
                if not response["has_more"]:
                    break
                
                start_cursor = response["next_cursor"]
            
            logger.info(f"Found {len(all_pages)} pages in database")
            
            # Build mapping from repository path to page ID
            for page in all_pages:
                repo_path = None
                title = ""
                
                # Get repository path
                if "Repository Path" in page["properties"]:
                    repo_prop = page["properties"]["Repository Path"]
                    if repo_prop.get("rich_text"):
                        repo_path = repo_prop["rich_text"][0]["plain_text"]
                
                # Get title for logging
                if "Title" in page["properties"]:
                    title_prop = page["properties"]["Title"]
                    if title_prop.get("title"):
                        title = title_prop["title"][0]["plain_text"]
                
                if repo_path:
                    # Convert repo path to article key format
                    # e.g., "en_ta/translate/figs-metaphor" -> "translate/figs-metaphor"
                    if repo_path.startswith("en_ta/"):
                        article_key = repo_path[6:]  # Remove "en_ta/" prefix
                        self.page_map[article_key] = {
                            "page_id": page["id"],
                            "title": title
                        }
                        logger.debug(f"Mapped {article_key} -> {title}")
            
            logger.info(f"Created mapping for {len(self.page_map)} articles")
            return True
            
        except Exception as e:
            logger.error(f"Error loading page mapping: {e}")
            return False
    
    def resolve_relative_path(self, current_path: str, relative_path: str) -> Optional[str]:
        """Resolve a relative path to an absolute article path."""
        try:
            # Remove /01.md suffix if present
            if relative_path.endswith("/01.md"):
                relative_path = relative_path[:-6]
            
            # Get current directory (section)
            current_parts = current_path.split("/")
            current_section = current_parts[0] if current_parts else ""
            
            # Resolve relative path
            if relative_path.startswith("../"):
                # Same section link - just replace with section/article
                article_name = relative_path[3:]  # Remove "../"
                resolved_path = f"{current_section}/{article_name}"
                
            elif relative_path.startswith("../../"):
                # Cross-section link - remove "../../" and use as-is
                resolved_path = relative_path[6:]  # Remove "../../"
                
            else:
                # Relative to current directory
                if current_parts:
                    resolved_path = f"{current_section}/{relative_path}"
                else:
                    resolved_path = relative_path
            
            # Clean up any double slashes and fix "../" patterns
            resolved_path = re.sub(r'/+', '/', resolved_path)
            resolved_path = re.sub(r'[^/]+/\.\./+', '', resolved_path)  # Remove "section/../" patterns
            
            # Remove leading slash if present
            if resolved_path.startswith("/"):
                resolved_path = resolved_path[1:]
            
            return resolved_path
            
        except Exception as e:
            logger.error(f"Error resolving path {relative_path} from {current_path}: {e}")
            return None
    
    def is_internal_link(self, url: str) -> bool:
        """Check if a URL is an internal link that should be replaced."""
        return (
            url.endswith("/01.md") or 
            (url.startswith("../") and "/01.md" not in url) or
            (url.startswith("../../") and "/01.md" not in url)
        )
    
    def get_page_content(self, page_id: str) -> List[Dict]:
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
            logger.error(f"Error getting page content for {page_id}: {e}")
            return []
    
    def update_rich_text_links(self, rich_text: List[Dict], current_path: str) -> Tuple[List[Dict], int]:
        """Update links in rich text array."""
        updated_rich_text = []
        links_replaced = 0
        
        for item in rich_text:
            if item.get("type") == "text":
                text_obj = item.get("text", {})
                link_obj = text_obj.get("link")
                
                if link_obj and self.is_internal_link(link_obj["url"]):
                    # Resolve the relative path
                    resolved_path = self.resolve_relative_path(current_path, link_obj["url"])
                    
                    if resolved_path and resolved_path in self.page_map:
                        # Replace with Notion page link
                        target_page_id = self.page_map[resolved_path]["page_id"]
                        new_url = f"https://www.notion.so/{target_page_id.replace('-', '')}"
                        
                        # Update the link
                        updated_item = item.copy()
                        updated_item["text"]["link"]["url"] = new_url
                        updated_rich_text.append(updated_item)
                        
                        links_replaced += 1
                        logger.info(f"  Replaced: {link_obj['url']} -> {self.page_map[resolved_path]['title']}")
                    else:
                        # Keep original link if we can't resolve it
                        updated_rich_text.append(item)
                        if resolved_path:
                            logger.warning(f"  Could not find page for: {resolved_path}")
                else:
                    updated_rich_text.append(item)
            else:
                updated_rich_text.append(item)
        
        return updated_rich_text, links_replaced
    
    def update_block_links(self, block: Dict, current_path: str) -> Tuple[Dict, int]:
        """Update links in a single block."""
        updated_block = block.copy()
        links_replaced = 0
        
        block_type = block.get("type")
        
        # Handle different block types with rich text
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            if rich_text:
                updated_rich_text, replaced = self.update_rich_text_links(rich_text, current_path)
                updated_block[block_type]["rich_text"] = updated_rich_text
                links_replaced += replaced
        
        elif block_type == "quote":
            rich_text = block.get("quote", {}).get("rich_text", [])
            if rich_text:
                updated_rich_text, replaced = self.update_rich_text_links(rich_text, current_path)
                updated_block["quote"]["rich_text"] = updated_rich_text
                links_replaced += replaced
        
        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
            if rich_text:
                updated_rich_text, replaced = self.update_rich_text_links(rich_text, current_path)
                updated_block["callout"]["rich_text"] = updated_rich_text
                links_replaced += replaced
        
        return updated_block, links_replaced
    
    def update_page_links(self, page_id: str, current_path: str, title: str) -> bool:
        """Update all links in a page."""
        logger.info(f"Updating links in: {title}")
        
        try:
            # Get all blocks from the page
            blocks = self.get_page_content(page_id)
            
            if not blocks:
                logger.info(f"  No blocks found in page")
                return True
            
            # Update links in each block
            updated_blocks = []
            page_links_replaced = 0
            
            for block in blocks:
                updated_block, links_replaced = self.update_block_links(block, current_path)
                updated_blocks.append(updated_block)
                page_links_replaced += links_replaced
            
            # Update blocks if any links were replaced
            if page_links_replaced > 0:
                # Delete existing blocks
                for block in blocks:
                    try:
                        notion.blocks.delete(block_id=block["id"])
                    except Exception as e:
                        logger.warning(f"  Could not delete block {block['id']}: {e}")
                
                # Add updated blocks
                # Process in batches to avoid API limits
                batch_size = 100
                for i in range(0, len(updated_blocks), batch_size):
                    batch = updated_blocks[i:i + batch_size]
                    
                    # Remove IDs from blocks before adding
                    clean_batch = []
                    for block in batch:
                        clean_block = {k: v for k, v in block.items() if k not in ["id", "created_time", "last_edited_time", "created_by", "last_edited_by", "archived", "has_children"]}
                        clean_batch.append(clean_block)
                    
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=clean_batch
                    )
                
                logger.info(f"  Replaced {page_links_replaced} links")
                self.total_links_replaced += page_links_replaced
                return True
            else:
                logger.info(f"  No links to replace")
                return True
                
        except Exception as e:
            logger.error(f"Error updating links in page {page_id}: {e}")
            return False
    
    def process_all_pages(self):
        """Process all pages in the database."""
        logger.info("Starting link replacement process...")
        
        if not self.load_page_mapping():
            logger.error("Failed to load page mapping")
            return
        
        success_count = 0
        total_pages = len(self.page_map)
        
        for i, (article_path, page_info) in enumerate(self.page_map.items(), 1):
            logger.info(f"Processing ({i}/{total_pages}): {article_path}")
            
            try:
                if self.update_page_links(page_info["page_id"], article_path, page_info["title"]):
                    success_count += 1
                    self.updated_pages += 1
                
                # Rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error processing {article_path}: {e}")
                continue
        
        logger.info(f"Link replacement complete:")
        logger.info(f"  Pages processed: {success_count}/{total_pages}")
        logger.info(f"  Total links replaced: {self.total_links_replaced}")

def main():
    """Main function."""
    logger.info("Starting Translation Academy link replacement...")
    
    replacer = LinkReplacer()
    replacer.process_all_pages()
    
    logger.info("Link replacement process finished!")

if __name__ == "__main__":
    main()