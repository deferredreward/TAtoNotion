import os
import re
import time
import logging
import json
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

# Mapping from Gitea URLs to Notion page IDs
url_to_page_id_map = {}
# Cache for page IDs by title/article_id
page_cache = {}

def load_cache_from_file(filename="page_cache.json"):
    """Load page cache from a JSON file."""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            if "page_cache" in data:
                global page_cache
                page_cache = data["page_cache"]
                logging.info(f"Loaded {len(page_cache)} page cache entries from {filename}")
            if "url_map" in data:
                global url_to_page_id_map
                url_to_page_id_map = data["url_map"]
                logging.info(f"Loaded {len(url_to_page_id_map)} URL mappings from {filename}")
            return True
    except Exception as e:
        logging.error(f"Error loading cache from {filename}: {str(e)}")
        return False

def save_cache_to_file(filename="page_cache.json"):
    """Save page cache to a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump({
                "page_cache": page_cache,
                "url_map": url_to_page_id_map
            }, f, indent=2)
        logging.info(f"Saved {len(page_cache)} page cache entries and {len(url_to_page_id_map)} URL mappings to {filename}")
        return True
    except Exception as e:
        logging.error(f"Error saving cache to {filename}: {str(e)}")
        return False

def extract_article_id_from_link(link_url):
    """Extract article ID from an internal link."""
    article_id = None
    
    # Check for the pattern ../folder/01.md or ../folder/
    if "../" in link_url:
        # Pattern 1: ../folder/01.md
        if "01.md" in link_url:
            match = re.search(r'\.\.\/([^\/]+)\/01\.md', link_url)
            if match:
                article_id = match.group(1)
        # Pattern 2: ../folder/
        elif link_url.endswith("/"):
            match = re.search(r'\.\.\/([^\/]+)\/', link_url)
            if match:
                article_id = match.group(1)
        # Additional pattern: 01-article-name.md
        elif re.search(r'(\d+-[^\/]+)\.md$', link_url):
            match = re.search(r'(\d+-[^\/]+)\.md$', link_url)
            if match:
                article_id = match.group(1)
    # Handle full URL paths
    elif "git.door43.org" in link_url and "translate/" in link_url:
        match = re.search(r'translate/([^/]+)(?:/01\.md)?', link_url)
        if match:
            article_id = match.group(1)
    
    return article_id

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
                        
                        # Try to find a matching page ID
                        matching_page_id = None
                        
                        # Try exact match first
                        if link_url in url_to_page_id_map:
                            matching_page_id = url_to_page_id_map[link_url]
                        # Then try variations
                        else:
                            # Check for article ID in the URL
                            article_id = extract_article_id_from_link(link_url)
                            if article_id and article_id in page_cache:
                                matching_page_id = page_cache[article_id]
                        
                        if matching_page_id:
                            # Update the link to internal Notion link
                            updated_text_obj = text_obj.copy()
                            updated_text_obj["text"]["link"]["url"] = f"https://www.notion.so/{matching_page_id.replace('-', '')}"
                            updated_rich_text.append(updated_text_obj)
                            modified = True
                            update_count += 1
                            logging.debug(f"Updated link from {link_url} to Notion page {matching_page_id}")
                        else:
                            # Keep original link but log
                            if is_gitea_link:
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
        
        # Update links in this page
        if update_page_links(page_id):
            update_count += 1
        
        # Add a small delay to avoid rate limiting
        time.sleep(0.3)
    
    logging.info(f"Link update process complete. Updated links in {update_count} pages.")
    return update_count > 0

def update_gitea_links_to_internal():
    """Main function to update Gitea links to internal Notion links."""
    # Load cache from file
    success = load_cache_from_file()
    if not success:
        logging.error("Failed to load cache, exiting.")
        return False
        
    # Process all pages to update links
    success = process_all_pages()
    
    # Save updated cache
    save_cache_to_file()
    
    return success

if __name__ == "__main__":
    logging.info("Starting post-processing of Gitea links...")
    success = update_gitea_links_to_internal()
    if success:
        logging.info("Successfully updated Gitea links to internal Notion links.")
    else:
        logging.error("Failed to update links.") 