#!/usr/bin/env python3
"""
Fix Formatting Issues in Notion Database

This script detects and fixes common formatting problems like:
1. HTML tags (especially <sup> tags) left in text
2. Empty quote blocks without the space placeholder
3. Excessive consecutive quote blocks
4. Malformed footnote references
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
        logging.FileHandler("fix_formatting.log"),
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

class FormattingFixer:
    def __init__(self):
        self.total_pages_processed = 0
        self.total_issues_fixed = 0
        self.issue_counts = {}
        
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
    
    def clean_html_tags(self, text: str) -> str:
        """Remove HTML tags from text."""
        # Remove <sup> tags and convert to plain text
        text = re.sub(r'<sup>\s*(\d+)\s*</sup>', r'[\1]', text)
        text = re.sub(r'<sup>\s*\[\s*(\d+)\s*\]\s*</sup>', r'[\1]', text)
        
        # Remove other common HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        return text
    
    def fix_rich_text_formatting(self, rich_text: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """Fix formatting issues in rich text array."""
        if not rich_text:
            return rich_text, []
        
        fixed_rich_text = []
        issues_fixed = []
        
        for item in rich_text:
            if item.get("type") == "text":
                text_content = item.get("text", {}).get("content", "")
                original_text = text_content
                
                # Clean HTML tags
                cleaned_text = self.clean_html_tags(text_content)
                
                if cleaned_text != original_text:
                    issues_fixed.append("HTML tags removed")
                    
                    # Update the text content
                    updated_item = item.copy()
                    updated_item["text"]["content"] = cleaned_text
                    fixed_rich_text.append(updated_item)
                else:
                    fixed_rich_text.append(item)
            else:
                fixed_rich_text.append(item)
        
        return fixed_rich_text, issues_fixed
    
    def fix_block_formatting(self, block: Dict) -> Tuple[Dict, List[str]]:
        """Fix formatting issues in a single block."""
        block_type = block.get("type")
        updated_block = block.copy()
        all_issues_fixed = []
        
        # Handle different block types with rich text
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            if rich_text:
                fixed_rich_text, issues_fixed = self.fix_rich_text_formatting(rich_text)
                updated_block[block_type]["rich_text"] = fixed_rich_text
                all_issues_fixed.extend(issues_fixed)
        
        elif block_type == "quote":
            rich_text = block.get("quote", {}).get("rich_text", [])
            
            # Check for empty quote blocks
            if not rich_text or all(not item.get("text", {}).get("content", "").strip() for item in rich_text):
                # Fix empty quote by adding single space
                updated_block["quote"]["rich_text"] = [{"type": "text", "text": {"content": " "}}]
                all_issues_fixed.append("Empty quote block fixed")
            else:
                fixed_rich_text, issues_fixed = self.fix_rich_text_formatting(rich_text)
                updated_block["quote"]["rich_text"] = fixed_rich_text
                all_issues_fixed.extend(issues_fixed)
        
        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
            if rich_text:
                fixed_rich_text, issues_fixed = self.fix_rich_text_formatting(rich_text)
                updated_block["callout"]["rich_text"] = fixed_rich_text
                all_issues_fixed.extend(issues_fixed)
        
        return updated_block, all_issues_fixed
    
    def remove_excessive_consecutive_quotes(self, blocks: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """Remove excessive consecutive empty quote blocks."""
        if not blocks:
            return blocks, []
        
        cleaned_blocks = []
        issues_fixed = []
        consecutive_empty_quotes = 0
        
        for i, block in enumerate(blocks):
            block_type = block.get("type")
            
            if block_type == "quote":
                rich_text = block.get("quote", {}).get("rich_text", [])
                
                # Check if quote is effectively empty (just whitespace or single space)
                is_empty = (
                    not rich_text or 
                    all(not item.get("text", {}).get("content", "").strip() or 
                        item.get("text", {}).get("content", "").strip() == " " 
                        for item in rich_text)
                )
                
                if is_empty:
                    consecutive_empty_quotes += 1
                    
                    # Keep first empty quote, remove excess
                    if consecutive_empty_quotes == 1:
                        # Ensure it has the space placeholder
                        if not rich_text or all(not item.get("text", {}).get("content", "") for item in rich_text):
                            block["quote"]["rich_text"] = [{"type": "text", "text": {"content": " "}}]
                        cleaned_blocks.append(block)
                    else:
                        # Skip this excessive empty quote
                        issues_fixed.append(f"Removed excessive empty quote block {i}")
                else:
                    consecutive_empty_quotes = 0
                    cleaned_blocks.append(block)
            else:
                consecutive_empty_quotes = 0
                cleaned_blocks.append(block)
        
        return cleaned_blocks, issues_fixed
    
    def fix_page_formatting(self, page_id: str, title: str) -> bool:
        """Fix formatting issues in a page."""
        logger.info(f"Processing: {title}")
        
        try:
            # Get all blocks from the page
            blocks = self.get_page_content(page_id)
            
            if not blocks:
                logger.info(f"  No blocks found")
                return True
            
            # Fix formatting in each block
            updated_blocks = []
            page_issues_fixed = []
            
            for block in blocks:
                updated_block, issues_fixed = self.fix_block_formatting(block)
                updated_blocks.append(updated_block)
                page_issues_fixed.extend(issues_fixed)
            
            # Remove excessive consecutive quotes
            final_blocks, quote_issues = self.remove_excessive_consecutive_quotes(updated_blocks)
            page_issues_fixed.extend(quote_issues)
            
            # Update page if any issues were fixed
            if page_issues_fixed:
                logger.info(f"  Fixing {len(page_issues_fixed)} issues")
                
                # Track issue types
                for issue in page_issues_fixed:
                    self.issue_counts[issue] = self.issue_counts.get(issue, 0) + 1
                
                # Delete existing blocks
                for block in blocks:
                    try:
                        notion.blocks.delete(block_id=block["id"])
                        time.sleep(0.1)  # Small delay to avoid rate limits
                    except Exception as e:
                        logger.warning(f"  Could not delete block {block['id']}: {e}")
                
                # Add updated blocks in batches
                batch_size = 50
                for i in range(0, len(final_blocks), batch_size):
                    batch = final_blocks[i:i + batch_size]
                    
                    # Clean blocks for API
                    clean_batch = []
                    for block in batch:
                        clean_block = {
                            k: v for k, v in block.items() 
                            if k not in ["id", "created_time", "last_edited_time", "created_by", "last_edited_by", "archived", "has_children"]
                        }
                        clean_batch.append(clean_block)
                    
                    try:
                        notion.blocks.children.append(
                            block_id=page_id,
                            children=clean_batch
                        )
                        time.sleep(0.3)  # Rate limiting
                    except Exception as e:
                        logger.error(f"  Error adding blocks: {e}")
                        return False
                
                self.total_issues_fixed += len(page_issues_fixed)
                logger.info(f"  Fixed: {', '.join(set(page_issues_fixed))}")
                return True
            else:
                logger.info(f"  No issues found")
                return True
                
        except Exception as e:
            logger.error(f"Error fixing page {page_id}: {e}")
            return False
    
    def get_all_pages(self) -> List[Dict]:
        """Get all pages from the database."""
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
            
            return all_pages
            
        except Exception as e:
            logger.error(f"Error getting pages: {e}")
            return []
    
    def process_all_pages(self):
        """Process all pages in the database."""
        logger.info("Starting formatting fix process...")
        
        pages = self.get_all_pages()
        if not pages:
            logger.error("No pages found")
            return
        
        success_count = 0
        total_pages = len(pages)
        
        for i, page in enumerate(pages, 1):
            # Get page title
            title = ""
            if "Title" in page["properties"]:
                title_prop = page["properties"]["Title"]
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
            
            logger.info(f"Processing ({i}/{total_pages}): {title}")
            
            try:
                if self.fix_page_formatting(page["id"], title):
                    success_count += 1
                    self.total_pages_processed += 1
                
                # Rate limiting between pages
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing page {i}: {e}")
                continue
        
        logger.info(f"Formatting fix complete:")
        logger.info(f"  Pages processed: {success_count}/{total_pages}")
        logger.info(f"  Total issues fixed: {self.total_issues_fixed}")
        
        if self.issue_counts:
            logger.info("Issue types fixed:")
            for issue_type, count in self.issue_counts.items():
                logger.info(f"  {issue_type}: {count}")

def main():
    """Main function."""
    logger.info("Starting Translation Academy formatting fix...")
    
    fixer = FormattingFixer()
    fixer.process_all_pages()
    
    logger.info("Formatting fix process finished!")

if __name__ == "__main__":
    main()