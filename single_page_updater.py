#!/usr/bin/env python3
"""
Single Page Updater for Testing Formatting Fixes
Based on migration_v8.py but focused on updating a single page
"""

import os
import re
import logging
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("single_page_update.log"),
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

class SinglePageUpdater:
    def __init__(self):
        pass
    
    def parse_rich_text(self, text: str) -> List[Dict]:
        """Parse text for bold, italic, and links - simple and reliable approach."""
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        # Clean up any weird whitespace
        text = text.strip()
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        result = []
        i = 0
        
        while i < len(text):
            # Look for **bold** text
            if text[i:i+2] == '**':
                # Find the closing **
                end = text.find('**', i + 2)
                if end != -1:
                    if i > 0:
                        # Add text before bold
                        result.append({
                            "type": "text",
                            "text": {"content": text[:i]}
                        })
                        text = text[i:]
                        end = end - i
                        i = 0
                    
                    bold_text = text[2:end]
                    result.append({
                        "type": "text",
                        "text": {"content": bold_text},
                        "annotations": {"bold": True}
                    })
                    text = text[end+2:]
                    i = 0
                    continue
            
            # Look for *italic* text
            elif text[i] == '*' and i + 1 < len(text) and text[i+1] != '*':
                # Find the closing *
                end = text.find('*', i + 1)
                if end != -1:
                    if i > 0:
                        # Add text before italic
                        result.append({
                            "type": "text",
                            "text": {"content": text[:i]}
                        })
                        text = text[i:]
                        end = end - i
                        i = 0
                    
                    italic_text = text[1:end]
                    result.append({
                        "type": "text",
                        "text": {"content": italic_text},
                        "annotations": {"italic": True}
                    })
                    text = text[end+1:]
                    i = 0
                    continue
            
            # Look for [link text](url) patterns
            elif text[i] == '[':
                # Find the closing ]
                close_bracket = text.find(']', i + 1)
                if close_bracket != -1 and close_bracket + 1 < len(text) and text[close_bracket + 1] == '(':
                    # Find the closing )
                    close_paren = text.find(')', close_bracket + 2)
                    if close_paren != -1:
                        if i > 0:
                            # Add text before link
                            result.append({
                                "type": "text",
                                "text": {"content": text[:i]}
                            })
                            text = text[i:]
                            close_bracket = close_bracket - i
                            close_paren = close_paren - i
                            i = 0
                        
                        link_text = text[1:close_bracket]
                        link_url = text[close_bracket + 2:close_paren]
                        result.append({
                            "type": "text",
                            "text": {"content": link_text, "link": {"url": link_url}}
                        })
                        text = text[close_paren + 1:]
                        i = 0
                        continue
            
            i += 1
        
        # Add any remaining text
        if text:
            result.append({
                "type": "text",
                "text": {"content": text}
            })
        
        return result if result else [{"type": "text", "text": {"content": ""}}]
    
    def process_table(self, lines: List[str], start_i: int) -> tuple:
        """Process markdown table and convert to Notion table block."""
        try:
            table_lines = []
            i = start_i
            
            # Collect all table lines (starting with |)
            while i < len(lines) and lines[i].strip().startswith('|'):
                line = lines[i].strip()
                if line.endswith('|'):
                    table_lines.append(line)
                i += 1
            
            if len(table_lines) < 2:
                # Not a valid table, return None
                return None, start_i + 1
            
            # Parse table structure
            header_line = table_lines[0]
            headers = [cell.strip() for cell in header_line.split('|')[1:-1]]  # Remove empty first/last
            
            # Skip separator line if it exists (like |----|----|)
            data_start = 1
            if len(table_lines) > 1 and all(c in '-|: ' for c in table_lines[1]):
                data_start = 2
            
            # Parse data rows
            rows = []
            for line in table_lines[data_start:]:
                cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last
                if len(cells) >= len(headers):
                    rows.append(cells[:len(headers)])  # Truncate to header count
                elif len(cells) > 0:
                    # Pad short rows with empty cells
                    while len(cells) < len(headers):
                        cells.append('')
                    rows.append(cells)
            
            if not rows:
                return None, start_i + 1
            
            # Create Notion table block
            table_block = {
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": len(headers),
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": []
                }
            }
            
            # Add header row
            header_row = {
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": []
                }
            }
            
            for header in headers:
                header_row["table_row"]["cells"].append(
                    self.parse_rich_text(header) if header else [{"type": "text", "text": {"content": ""}}]
                )
            
            table_block["table"]["children"].append(header_row)
            
            # Add data rows
            for row in rows:
                row_block = {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": []
                    }
                }
                
                for cell in row:
                    row_block["table_row"]["cells"].append(
                        self.parse_rich_text(cell) if cell else [{"type": "text", "text": {"content": ""}}]
                    )
                
                table_block["table"]["children"].append(row_block)
            
            return table_block, i
            
        except Exception as e:
            logger.error(f"Error processing table: {e}")
            return None, start_i + 1
    
    def detect_table_in_text(self, text: str) -> bool:
        """Check if text contains a markdown table."""
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('|') and line.endswith('|') and line.count('|') >= 3:
                return True
        return False
    
    def convert_table_text_to_blocks(self, text: str) -> List[Dict]:
        """Convert text containing markdown table to Notion blocks."""
        lines = text.split('\n')
        blocks = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for table
            if line.startswith('|') and line.endswith('|') and line.count('|') >= 3:
                table_block, new_i = self.process_table(lines, i)
                if table_block:
                    blocks.append(table_block)
                    i = new_i
                    continue
            
            # Regular text - collect non-table lines
            text_lines = []
            while i < len(lines) and not (lines[i].strip().startswith('|') and lines[i].strip().endswith('|')):
                if lines[i].strip():  # Skip empty lines
                    text_lines.append(lines[i])
                i += 1
            
            if text_lines:
                # Create a paragraph from the text
                paragraph_text = ' '.join(text_lines)
                if paragraph_text.strip():
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": self.parse_rich_text(paragraph_text)
                        }
                    })
        
        return blocks
    
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
    
    def update_page_content(self, page_id: str, new_blocks: List[Dict]) -> bool:
        """Replace all content in a page with new blocks."""
        try:
            # Get existing blocks
            existing_blocks = self.get_page_content(page_id)
            
            # Delete existing blocks
            for block in existing_blocks:
                try:
                    notion.blocks.delete(block_id=block["id"])
                    time.sleep(0.1)  # Rate limiting
                except Exception as e:
                    logger.warning(f"Could not delete block {block['id']}: {e}")
            
            # Add new blocks
            for block in new_blocks:
                try:
                    notion.blocks.children.append(block_id=page_id, children=[block])
                    time.sleep(0.1)  # Rate limiting
                except Exception as e:
                    logger.error(f"Error adding block: {e}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating page content: {e}")
            return False
    
    def process_page_for_tables(self, page_id: str, title: str) -> bool:
        """Process a single page to find and convert table text to proper tables."""
        logger.info(f"Processing page: {title}")
        
        try:
            # Get page content
            blocks = self.get_page_content(page_id)
            
            if not blocks:
                logger.info("No blocks found")
                return True
            
            logger.info(f"Found {len(blocks)} blocks")
            
            # Look for blocks that contain table markdown
            new_blocks = []
            tables_found = 0
            
            for i, block in enumerate(blocks):
                block_type = block.get("type")
                
                if block_type == "paragraph":
                    rich_text = block.get("paragraph", {}).get("rich_text", [])
                    if rich_text:
                        # Reconstruct text from rich_text
                        text_content = ""
                        for item in rich_text:
                            if item.get("type") == "text":
                                text_content += item.get("text", {}).get("content", "")
                        
                        # Check if this text contains a table
                        if self.detect_table_in_text(text_content):
                            logger.info(f"Found table in block {i+1}")
                            tables_found += 1
                            
                            # Convert table text to proper blocks
                            table_blocks = self.convert_table_text_to_blocks(text_content)
                            new_blocks.extend(table_blocks)
                        else:
                            # Keep original block
                            new_blocks.append(block)
                    else:
                        # Keep original block
                        new_blocks.append(block)
                else:
                    # Keep original block
                    new_blocks.append(block)
            
            if tables_found > 0:
                logger.info(f"Converting {tables_found} table(s) to proper Notion tables")
                
                # Update page content
                if self.update_page_content(page_id, new_blocks):
                    logger.info("Page updated successfully!")
                    return True
                else:
                    logger.error("Failed to update page")
                    return False
            else:
                logger.info("No tables found in this page")
                return True
                
        except Exception as e:
            logger.error(f"Error processing page: {e}")
            return False

def main():
    """Main function to update the Biblical-Weight page."""
    page_id = "23272d5af2de81a88589e901ea36436a"
    page_title = "Biblical Weight"
    
    logger.info(f"Starting single page update for: {page_title}")
    
    updater = SinglePageUpdater()
    
    success = updater.process_page_for_tables(page_id, page_title)
    
    if success:
        logger.info("Single page update completed successfully!")
    else:
        logger.error("Single page update failed!")
    
    # Also run the comprehensive formatter on this page
    logger.info("Running comprehensive formatter on the page...")
    
    # Import and run the comprehensive formatter
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from comprehensive_formatting_fixer import ComprehensiveFormattingFixer
        
        fixer = ComprehensiveFormattingFixer()
        fixer.fix_page_formatting(page_id, page_title)
        
        logger.info("Comprehensive formatting completed!")
        
    except Exception as e:
        logger.error(f"Error running comprehensive formatter: {e}")

if __name__ == "__main__":
    main()