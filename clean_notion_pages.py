import os
import logging
import time
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

def find_page_by_title(title):
    """Find a Notion page by title."""
    try:
        # Query pages that have the specified title
        response = notion.search(
            query=title,
            filter={
                "property": "object",
                "value": "page"
            }
        )
        
        # Check if any pages were found
        results = response.get("results", [])
        if results:
            # Return the ID of the first matching page
            for page in results:
                page_title = page.get("properties", {}).get("title", {}).get("title", [])
                if page_title:
                    title_text = page_title[0].get("text", {}).get("content", "")
                    if title_text.lower() == title.lower():
                        return page.get("id")
        
        # No matching page found
        return None
    except Exception as e:
        logging.error(f"Error searching for page {title}: {str(e)}")
        return None

def delete_page_content(page_id):
    """Delete all content blocks within a page."""
    try:
        # Get all blocks in the page
        blocks = notion.blocks.children.list(block_id=page_id).get("results", [])
        
        # Delete each block
        for block in blocks:
            block_id = block.get("id")
            notion.blocks.delete(block_id=block_id)
            logging.info(f"Deleted block {block_id}")
            time.sleep(0.5)  # Add a delay to prevent rate limiting
        
        logging.info(f"Cleared all content from page {page_id}")
        return True
    except Exception as e:
        logging.error(f"Error deleting content from page {page_id}: {str(e)}")
        return False

def find_toggle_by_title(title):
    """Find a toggle block by title within the parent page."""
    try:
        # For the main page ID
        parent_page_id = "1c372d5af2de80e08b11cd7748a1467d"
        
        # Get all blocks in the page
        blocks = notion.blocks.children.list(block_id=parent_page_id).get("results", [])
        
        # Find the toggle with the specified title
        for block in blocks:
            if block.get("type") == "heading_1" and block.get("heading_1", {}).get("is_toggleable", False):
                # Get the text content of the toggle
                rich_text = block.get("heading_1", {}).get("rich_text", [])
                if rich_text:
                    block_title = rich_text[0].get("text", {}).get("content", "")
                    if block_title.lower() == title.lower():
                        return block.get("id")
        
        # No matching toggle found
        return None
    except Exception as e:
        logging.error(f"Error finding toggle {title}: {str(e)}")
        return None

def clear_translate_page():
    """Find and clear the 'Translate' page by deleting all content blocks."""
    translate_page_id = find_page_by_title("Translate")
    if translate_page_id:
        logging.info(f"Found Translate toggle with ID: {translate_page_id}")
        return delete_page_content(translate_page_id)
    else:
        logging.info("No Translate toggle found, no cleanup needed.")
        return True

if __name__ == "__main__":
    logging.info("Starting cleanup process")
    clear_translate_page()
    logging.info("Cleanup process completed") 