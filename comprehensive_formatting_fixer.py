#!/usr/bin/env python3
"""
Comprehensive Formatting Fixer for Notion Database

This script fixes common formatting issues based on patterns found in the codebase:
1. Converts HTML <sup> tags to Unicode superscript characters
2. Removes <br> tags and converts to proper line breaks
3. Fixes empty quote blocks with proper space placeholders
4. Handles malformed footnote references
5. Removes other HTML tags
"""

import os
import sys
import re
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("comprehensive_formatting_fix.log"),
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

class ComprehensiveFormattingFixer:
    def __init__(self):
        self.total_pages_processed = 0
        self.total_issues_fixed = 0
        self.issue_counts = {}
        
        # Unicode superscript mapping (from existing codebase)
        self.superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
            'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
            'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
            'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
            'p': 'ᵖ', 'q': 'ᵠ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ',
            'u': 'ᵘ', 'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ',
            'z': 'ᶻ', '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽',
            ')': '⁾', '[': '⁽', ']': '⁾', ' ': ' '
        }
        
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
    
    def convert_to_superscript(self, text: str) -> str:
        """Convert text to Unicode superscript characters."""
        return ''.join(self.superscript_map.get(c, c) for c in text)
    
    def clean_html_and_formatting(self, text: str) -> str:
        """Remove HTML tags and fix formatting issues."""
        original_text = text
        
        # Handle <sup> tags with comprehensive patterns (from existing codebase)
        def sup_full_repl(match):
            content = match.group(1).strip()
            
            # Combined numeric and bracket footnote: e.g. '16 [1]' -> ¹⁶⁽¹⁾
            cm = re.match(r'^(?P<num>\\d+)\\s*\\[\\s*(?P<foot>\\d+)\\s*\\]$', content)
            if cm:
                num_sup = self.convert_to_superscript(cm.group('num'))
                foot_sup = self.convert_to_superscript(cm.group('foot'))
                return f"{num_sup}⁽{foot_sup}⁾"
            
            # Bracket-only footnote: e.g. '[1]' -> ⁽¹⁾
            bm = re.match(r'^\\[\\s*(\\d+)\\s*\\]$', content)
            if bm:
                foot_sup = self.convert_to_superscript(bm.group(1))
                return f"⁽{foot_sup}⁾"
            
            # Numeric superscript: e.g. '16' -> ¹⁶
            nm = re.match(r'^(\\d+)$', content)
            if nm:
                return self.convert_to_superscript(nm.group(1))
            
            # Fallback: convert any content to superscript
            return self.convert_to_superscript(content)
        
        # Apply superscript conversion
        text = re.sub(r'<sup>\\s*(.*?)\\s*</sup>', sup_full_repl, text)
        
        # Handle <br> tags - convert to line breaks
        text = text.replace('<br>', '\\n')
        text = text.replace('<br/>', '\\n')
        text = text.replace('<br />', '\\n')
        
        # Fix stray literal \\n characters - convert to actual line breaks
        text = text.replace('\\n', '\n')
        
        # Remove other common HTML tags
        text = re.sub(r'</?p>', '', text)
        text = re.sub(r'</?div[^>]*>', '', text)
        text = re.sub(r'</?span[^>]*>', '', text)
        text = re.sub(r'</?strong>', '', text)  # Keep bold formatting in text
        text = re.sub(r'</?em>', '', text)     # Keep italic formatting in text
        text = re.sub(r'</?b>', '', text)      # Keep bold formatting in text
        text = re.sub(r'</?i>', '', text)      # Keep italic formatting in text
        
        # Clean up excessive whitespace
        text = re.sub(r'\\n\\s*\\n\\s*\\n+', '\\n\\n', text)  # Max 2 consecutive newlines
        text = re.sub(r'\\s+', ' ', text)  # Multiple whitespace to single space
        text = text.strip()
        
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
                
                # Clean HTML and formatting
                cleaned_text = self.clean_html_and_formatting(text_content)
                
                if cleaned_text != original_text:
                    if "<sup>" in original_text:
                        issues_fixed.append("HTML superscript tags converted")
                    if "<br" in original_text:
                        issues_fixed.append("HTML br tags removed")
                    if "\\n" in original_text:
                        issues_fixed.append("Stray \\n characters converted to line breaks")
                    if re.search(r'<[^>]+>', original_text):
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
    
    def update_block_safely(self, block_id: str, updated_block: Dict, original_block: Dict) -> bool:
        """Safely update a single block without deleting it."""
        try:
            # Get the block type
            block_type = updated_block.get("type")
            if not block_type:
                logger.warning(f"  Block {block_id} has no type, skipping")
                return False
            
            # Prepare update data based on block type
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                update_data = {
                    block_type: {
                        "rich_text": updated_block.get(block_type, {}).get("rich_text", [])
                    }
                }
            elif block_type == "quote":
                update_data = {
                    "quote": {
                        "rich_text": updated_block.get("quote", {}).get("rich_text", [])
                    }
                }
            elif block_type == "callout":
                callout_data = {
                    "rich_text": updated_block.get("callout", {}).get("rich_text", [])
                }
                # Preserve icon and color if they exist
                if "icon" in original_block.get("callout", {}):
                    callout_data["icon"] = original_block["callout"]["icon"]
                if "color" in original_block.get("callout", {}):
                    callout_data["color"] = original_block["callout"]["color"]
                update_data = {"callout": callout_data}
            else:
                logger.warning(f"  Block type {block_type} not supported for updates")
                return False
            
            # Update the block
            notion.blocks.update(block_id=block_id, **update_data)
            logger.debug(f"  Updated block {block_id} ({block_type})")
            return True
            
        except Exception as e:
            logger.error(f"  Error updating block {block_id}: {e}")
            return False
    
    def fix_page_formatting(self, page_id: str, title: str) -> bool:
        """Fix formatting issues in a page using safe, non-destructive updates."""
        logger.info(f"Processing: {title}")
        
        try:
            # Get all blocks from the page
            blocks = self.get_page_content(page_id)
            
            if not blocks:
                logger.info(f"  No blocks found")
                return True
            
            logger.info(f"  Found {len(blocks)} blocks to check")
            
            # Process each block individually and safely
            blocks_updated = 0
            page_issues_fixed = []
            
            for i, block in enumerate(blocks):
                block_id = block.get("id")
                if not block_id:
                    logger.warning(f"  Block {i} has no ID, skipping")
                    continue
                
                # Check if this block needs fixing
                updated_block, issues_fixed = self.fix_block_formatting(block)
                
                if issues_fixed:
                    # Only update if there were actual changes
                    if self.update_block_safely(block_id, updated_block, block):
                        blocks_updated += 1
                        page_issues_fixed.extend(issues_fixed)
                        logger.info(f"  Block {i+1}: Fixed {', '.join(set(issues_fixed))}")
                        
                        # Track issue types
                        for issue in issues_fixed:
                            self.issue_counts[issue] = self.issue_counts.get(issue, 0) + 1
                    else:
                        logger.error(f"  Block {i+1}: Failed to update, skipping")
                    
                    # Rate limiting between block updates
                    time.sleep(0.2)
            
            # Handle excessive consecutive quotes separately (this is more complex)
            # For now, let's skip this to avoid the destructive behavior
            # TODO: Implement safe consecutive quote removal
            
            if blocks_updated > 0:
                self.total_issues_fixed += len(page_issues_fixed)
                logger.info(f"  Successfully updated {blocks_updated} blocks")
                logger.info(f"  Fixed: {', '.join(set(page_issues_fixed))}")
                return True
            else:
                logger.info(f"  No issues found or no updates needed")
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
        logger.info("Starting comprehensive formatting fix process...")
        
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
        
        logger.info(f"Comprehensive formatting fix complete:")
        logger.info(f"  Pages processed: {success_count}/{total_pages}")
        logger.info(f"  Total issues fixed: {self.total_issues_fixed}")
        
        if self.issue_counts:
            logger.info("Issue types fixed:")
            for issue_type, count in self.issue_counts.items():
                logger.info(f"  {issue_type}: {count}")
    
    def process_test_articles(self, test_articles: List[str]):
        """Process only test articles specified in test_articles.txt."""
        logger.info(f"Processing {len(test_articles)} test articles...")
        
        if not test_articles:
            logger.warning("No test articles found")
            return
        
        # Get all pages from database
        all_pages = self.get_all_pages()
        if not all_pages:
            logger.error("No pages found in database")
            return
        
        # Filter pages to only those in test_articles list
        test_pages = []
        for page in all_pages:
            # Get Repository Path property
            repo_path = ""
            if "Repository Path" in page["properties"]:
                repo_path_prop = page["properties"]["Repository Path"]
                if repo_path_prop.get("rich_text"):
                    repo_path = repo_path_prop["rich_text"][0]["plain_text"]
            
            # Check if this page matches any test article
            if repo_path in test_articles:
                test_pages.append(page)
                logger.info(f"Found test article: {repo_path}")
        
        if not test_pages:
            logger.warning("No matching pages found for test articles")
            return
        
        logger.info(f"Processing {len(test_pages)} matching test pages...")
        
        success_count = 0
        for i, page in enumerate(test_pages, 1):
            # Get page title
            title = ""
            if "Title" in page["properties"]:
                title_prop = page["properties"]["Title"]
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
            
            logger.info(f"Processing ({i}/{len(test_pages)}): {title}")
            
            try:
                if self.fix_page_formatting(page["id"], title):
                    success_count += 1
                    self.total_pages_processed += 1
                
                # Rate limiting between pages
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing page {i}: {e}")
                continue
        
        logger.info(f"Test article processing complete:")
        logger.info(f"  Pages processed: {success_count}/{len(test_pages)}")
        logger.info(f"  Total issues fixed: {self.total_issues_fixed}")
        
        if self.issue_counts:
            logger.info("Issue types fixed:")
            for issue_type, count in self.issue_counts.items():
                logger.info(f"  {issue_type}: {count}")

def load_test_articles():
    """Load test articles from file."""
    test_file = Path("test_articles.txt")
    if test_file.exists():
        with open(test_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    else:
        logger.warning("test_articles.txt not found, using empty list")
        return []

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Comprehensive Formatting Fixer')
    parser.add_argument('--test', action='store_true', 
                       help='Run with test articles from test_articles.txt')
    parser.add_argument('--all', action='store_true', 
                       help='Run with all pages in database (default)')
    
    args = parser.parse_args()
    
    # Default to --all if no option specified
    if not args.test and not args.all:
        args.all = True
    
    logger.info("Starting Translation Academy comprehensive formatting fix...")
    
    fixer = ComprehensiveFormattingFixer()
    
    if args.test:
        logger.info("Running in TEST mode with articles from test_articles.txt")
        test_articles = load_test_articles()
        fixer.process_test_articles(test_articles)
    else:
        logger.info("Running in ALL mode - processing all pages")
        fixer.process_all_pages()
    
    logger.info("Comprehensive formatting fix process finished!")

if __name__ == "__main__":
    main()