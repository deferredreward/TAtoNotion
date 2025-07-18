import os
import sys
import re
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def get_page_content(page_id):
    """Get the content blocks from a page."""
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

def extract_links_from_blocks(blocks):
    """Extract all links from blocks."""
    links = []
    
    def extract_from_rich_text(rich_text_array):
        for item in rich_text_array:
            if item.get("type") == "text":
                text_obj = item.get("text", {})
                if text_obj.get("link"):
                    links.append({
                        "text": text_obj.get("content", ""),
                        "url": text_obj["link"]["url"]
                    })
    
    def process_block(block):
        block_type = block.get("type")
        
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            extract_from_rich_text(rich_text)
        elif block_type == "quote":
            rich_text = block.get("quote", {}).get("rich_text", [])
            extract_from_rich_text(rich_text)
        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
            extract_from_rich_text(rich_text)
        
        # Process children recursively
        if "children" in block:
            for child in block["children"]:
                process_block(child)
    
    for block in blocks:
        process_block(block)
    
    return links

def get_sample_pages():
    """Get a few sample pages to analyze."""
    try:
        response = notion.databases.query(
            database_id=DATABASE_ID,
            page_size=5
        )
        
        pages = response["results"]
        print(f"Found {len(pages)} sample pages")
        
        for page in pages:
            title = ""
            if "Title" in page["properties"]:
                title_prop = page["properties"]["Title"]
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
            
            print(f"\n=== Page: {title} ===")
            print(f"Page ID: {page['id']}")
            
            # Get page content
            blocks = get_page_content(page["id"])
            print(f"Found {len(blocks)} blocks")
            
            # Extract links
            links = extract_links_from_blocks(blocks)
            print(f"Found {len(links)} links")
            
            for link in links:
                print(f"  Text: '{link['text']}'")
                print(f"  URL: {link['url']}")
                print()
    
    except Exception as e:
        print(f"Error getting sample pages: {e}")

if __name__ == "__main__":
    get_sample_pages()