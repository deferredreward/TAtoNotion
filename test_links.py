import os
import logging
import time
import argparse
from dotenv import load_dotenv
from notion_client import Client
from clean_notion_pages import clear_translate_page
from build_toc_structure import (
    build_translate_section, 
    page_cache, 
    url_to_page_id_map,
    save_cache_to_file
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

def update_page_links(page_id):
    """
    Update links in a page by replacing Gitea links with internal Notion links
    where possible.
    """
    if not page_id:
        return False
        
    try:
        # Get all blocks in the page
        blocks_response = notion.blocks.children.list(block_id=page_id)
        blocks = blocks_response.get("results", [])
        
        # Handle pagination if there are many blocks
        while blocks_response.get("has_more", False):
            next_cursor = blocks_response.get("next_cursor")
            if next_cursor:
                blocks_response = notion.blocks.children.list(
                    block_id=page_id, 
                    start_cursor=next_cursor
                )
                blocks.extend(blocks_response.get("results", []))
            else:
                break
        
        update_count = 0
        link_count = 0
        
        # Process each block
        for block in blocks:
            block_id = block.get("id")
            block_type = block.get("type")
            
            if not block_id or not block_type:
                continue
                
            # Get rich text content from the block based on its type
            rich_text = None
            if block_type == "paragraph":
                rich_text = block.get("paragraph", {}).get("rich_text", [])
            elif block_type == "heading_1":
                rich_text = block.get("heading_1", {}).get("rich_text", [])
            elif block_type == "heading_2":
                rich_text = block.get("heading_2", {}).get("rich_text", [])
            elif block_type == "heading_3":
                rich_text = block.get("heading_3", {}).get("rich_text", [])
            elif block_type == "bulleted_list_item":
                rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
            elif block_type == "numbered_list_item":
                rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
            elif block_type == "quote":
                rich_text = block.get("quote", {}).get("rich_text", [])
            
            if not rich_text:
                continue
                
            # Check for links that need updating
            updated_rich_text = []
            modified = False
            
            for text_obj in rich_text:
                if text_obj.get("type") == "text":
                    link = text_obj.get("text", {}).get("link")
                    
                    if link and isinstance(link, dict) and "url" in link:
                        link_url = link["url"]
                        link_count += 1
                        
                        # Check if this is a Gitea link that can be converted
                        is_gitea_link = "git.door43.org" in link_url
                        is_relative_link = "../" in link_url
                        
                        # Try to find a matching page ID
                        matching_page_id = None
                        
                        # Try exact match first
                        if link_url in url_to_page_id_map:
                            matching_page_id = url_to_page_id_map[link_url]
                            logging.info(f"Found exact match for URL: {link_url} -> {matching_page_id}")
                        # Then try variations
                        elif is_relative_link:
                            # Extract article ID from relative link
                            parts = [p for p in link_url.strip('/').split('/') if p and p != '..']
                            if parts:
                                article_id = parts[-1]
                                if article_id.endswith('.md'):
                                    article_id = article_id[:-3]  # Remove .md extension
                                if article_id in page_cache:
                                    matching_page_id = page_cache[article_id]
                                    logging.info(f"Found article_id match for relative link: {link_url} -> {article_id} -> {matching_page_id}")
                        elif is_gitea_link:
                            # Extract article ID from gitea URL
                            if "/translate/" in link_url:
                                parts = link_url.split("/translate/")[1].split("/")
                                if parts:
                                    article_id = parts[0]
                                    if article_id in page_cache:
                                        matching_page_id = page_cache[article_id]
                                        logging.info(f"Found article_id match for Gitea link: {link_url} -> {article_id} -> {matching_page_id}")
                        
                        if matching_page_id:
                            # Update the link to internal Notion link
                            updated_text_obj = text_obj.copy()
                            updated_text_obj["text"]["link"]["url"] = f"https://www.notion.so/{matching_page_id.replace('-', '')}"
                            updated_rich_text.append(updated_text_obj)
                            modified = True
                            update_count += 1
                            logging.info(f"Updated link from {link_url} to Notion page {matching_page_id}")
                        else:
                            # Keep original link but log
                            if is_gitea_link or is_relative_link:
                                logging.warning(f"Could not find matching Notion page for link: {link_url}")
                            updated_rich_text.append(text_obj)
                    else:
                        # Not a link or no URL, keep as is
                        updated_rich_text.append(text_obj)
                else:
                    # Not a text object, keep as is
                    updated_rich_text.append(text_obj)
            
            # Update the block if modified
            if modified:
                try:
                    update_data = {
                        block_type: {
                            "rich_text": updated_rich_text
                        }
                    }
                    
                    notion.blocks.update(block_id=block_id, **update_data)
                    time.sleep(0.3)  # Avoid rate limiting
                except Exception as update_err:
                    logging.error(f"Error updating block {block_id}: {str(update_err)}")
        
        # Report results
        if link_count > 0:
            logging.info(f"Processed {link_count} links in page {page_id}, updated {update_count} links to internal Notion links")
        
        return update_count > 0
    
    except Exception as e:
        logging.error(f"Error updating links in page {page_id}: {str(e)}")
        return False

def process_all_pages():
    """
    Process all pages to update Gitea links to internal Notion links.
    Uses the URL mapping and page cache.
    """
    # Load the cache from file
    try:
        import json
        with open("page_cache.json", 'r') as f:
            data = json.load(f)
            
        if "page_cache" in data:
            global page_cache
            for key, value in data["page_cache"].items():
                page_cache[key] = value
            logging.info(f"Loaded {len(page_cache)} page cache entries")
            
        if "url_map" in data:
            global url_to_page_id_map
            for key, value in data["url_map"].items():
                url_to_page_id_map[key] = value
            logging.info(f"Loaded {len(url_to_page_id_map)} URL mappings")
    except Exception as e:
        logging.error(f"Error loading cache: {str(e)}")
    
    logging.info(f"Starting link update process...")
    logging.info(f"Found {len(page_cache)} pages in cache to process")
    
    # Keep track of unique page IDs (since the cache maps both titles and IDs to page_ids)
    processed_page_ids = set()
    update_count = 0
    
    for key, page_id in page_cache.items():
        # Skip non-page entries or already processed pages
        if not page_id or page_id in processed_page_ids or len(key) < 3:
            continue
            
        processed_page_ids.add(page_id)
        logging.info(f"Processing page: {key} -> {page_id}")
        
        # Update links in this page
        if update_page_links(page_id):
            update_count += 1
        
        # Add a small delay to avoid rate limiting
        time.sleep(0.3)
    
    logging.info(f"Link update process complete. Updated links in {update_count} pages.")
    return update_count > 0

def main():
    """Run a test of the link processing."""
    parser = argparse.ArgumentParser(description='Test link processing')
    parser.add_argument('--import', dest='run_import', action='store_true', help='Run the import first')
    parser.add_argument('--sections', type=int, default=1, help='Number of sections to import')
    parser.add_argument('--start', type=int, default=1, help='Start section index')
    args = parser.parse_args()
    
    if args.run_import:
        logging.info("=== RUNNING IMPORT FIRST ===")
        # Clean existing pages
        clear_translate_page()
        time.sleep(2)
        
        # Build TOC structure - but don't process links yet
        build_translate_section(
            use_remote=True, 
            process_content=True,
            section_limit=args.sections, 
            start_section=args.start,
            update_links=False
        )
        
        # Save cache to file
        save_cache_to_file()
        time.sleep(2)
    
    # Now process links
    logging.info("=== PROCESSING LINKS ===")
    process_all_pages()
    
    logging.info("=== TEST COMPLETE ===")

if __name__ == "__main__":
    main() 