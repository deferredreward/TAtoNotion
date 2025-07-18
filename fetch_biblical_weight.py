#!/usr/bin/env python3
"""
Script to fetch and examine the Biblical-Weight page content
"""

import os
import json
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def extract_page_id_from_url(url):
    """Extract page ID from Notion URL."""
    # URL format: https://www.notion.so/unfoldingword/Biblical-Weight-23272d5af2de81a88589e901ea36436a
    # Page ID is the last part: 23272d5af2de81a88589e901ea36436a
    parts = url.split('-')
    if len(parts) > 1:
        return parts[-1]
    return None

def get_page_content(page_id):
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
        print(f"Error getting page content: {e}")
        return []

def get_page_properties(page_id):
    """Get page properties."""
    try:
        response = notion.pages.retrieve(page_id=page_id)
        return response
    except Exception as e:
        print(f"Error getting page properties: {e}")
        return None

def analyze_content_for_tables(blocks):
    """Analyze content blocks for tables and formatting issues."""
    print("\n=== CONTENT ANALYSIS ===")
    
    table_count = 0
    formatting_issues = []
    
    for i, block in enumerate(blocks):
        block_type = block.get("type")
        
        if block_type == "table":
            table_count += 1
            print(f"\nTable {table_count} found at block {i+1}:")
            table_data = block.get("table", {})
            print(f"  Columns: {table_data.get('table_width', 'unknown')}")
            print(f"  Has header: {table_data.get('has_column_header', False)}")
            print(f"  Has row header: {table_data.get('has_row_header', False)}")
            
        elif block_type == "table_row":
            # This would be a child of a table block
            cells = block.get("table_row", {}).get("cells", [])
            print(f"  Row with {len(cells)} cells")
            
        # Check for formatting issues
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            for item in rich_text:
                if item.get("type") == "text":
                    text_content = item.get("text", {}).get("content", "")
                    if "<sup>" in text_content:
                        formatting_issues.append(f"Block {i+1}: HTML superscript tags found")
                    if "<br" in text_content:
                        formatting_issues.append(f"Block {i+1}: HTML br tags found")
                    if "\\n" in text_content:
                        formatting_issues.append(f"Block {i+1}: Literal \\n characters found")
                    if text_content.strip() == "":
                        formatting_issues.append(f"Block {i+1}: Empty text content")
    
    print(f"\nFound {table_count} tables")
    if formatting_issues:
        print(f"\nFormatting issues found:")
        for issue in formatting_issues:
            print(f"  - {issue}")
    else:
        print("\nNo major formatting issues detected")
    
    return table_count, formatting_issues

def main():
    # Extract page ID from URL
    url = "https://www.notion.so/unfoldingword/Biblical-Weight-23272d5af2de81a88589e901ea36436a"
    page_id = extract_page_id_from_url(url)
    
    if not page_id:
        print("Could not extract page ID from URL")
        return
    
    print(f"Page ID: {page_id}")
    
    # Get page properties
    page_props = get_page_properties(page_id)
    if page_props:
        title = ""
        if "Title" in page_props["properties"]:
            title_prop = page_props["properties"]["Title"]
            if title_prop.get("title"):
                title = title_prop["title"][0]["plain_text"]
        print(f"Page Title: {title}")
    
    # Get page content
    blocks = get_page_content(page_id)
    print(f"Found {len(blocks)} blocks")
    
    # Analyze content
    table_count, formatting_issues = analyze_content_for_tables(blocks)
    
    # Save raw content for inspection
    output_file = "biblical_weight_content.json"
    with open(output_file, "w") as f:
        json.dump({
            "page_id": page_id,
            "page_properties": page_props,
            "blocks": blocks,
            "analysis": {
                "table_count": table_count,
                "formatting_issues": formatting_issues
            }
        }, f, indent=2)
    
    print(f"\nRaw content saved to {output_file}")
    
    # Print some sample blocks for inspection
    print("\n=== SAMPLE BLOCKS ===")
    for i, block in enumerate(blocks[:5]):  # First 5 blocks
        print(f"\nBlock {i+1} ({block.get('type')}):")
        if block.get("type") in ["paragraph", "heading_1", "heading_2", "heading_3"]:
            rich_text = block.get(block.get("type"), {}).get("rich_text", [])
            for item in rich_text:
                if item.get("type") == "text":
                    content = item.get("text", {}).get("content", "")
                    print(f"  Text: {repr(content[:100])}")  # First 100 chars

if __name__ == "__main__":
    main()