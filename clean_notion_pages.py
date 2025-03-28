import os
import logging
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
        # Query pages in the parent database that have the specified title
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
        # Get all blocks
        blocks_response = notion.blocks.children.list(block_id=page_id)
        blocks = blocks_response.get("results", [])
        
        # Delete each block
        for block in blocks:
            block_id = block.get("id")
            try:
                notion.blocks.delete(block_id=block_id)
                logging.info(f"Deleted block {block_id}")
            except Exception as e:
                logging.error(f"Error deleting block {block_id}: {str(e)}")
        
        return True
    except Exception as e:
        logging.error(f"Error deleting page content: {str(e)}")
        return False

def clear_translate_toggle():
    """Find and clear the Translate toggle in the parent page."""
    parent_page_id = "1c372d5af2de80e08b11cd7748a1467d"
    
    try:
        # Get all blocks in the parent page
        blocks_response = notion.blocks.children.list(block_id=parent_page_id)
        blocks = blocks_response.get("results", [])
        
        # Find the Translate toggle
        translate_toggle_id = None
        for block in blocks:
            if block.get("type") == "toggle":
                # Check if this is the Translate toggle
                rich_text = block.get("toggle", {}).get("rich_text", [])
                if rich_text and rich_text[0].get("text", {}).get("content", "") == "Translate":
                    translate_toggle_id = block.get("id")
                    logging.info(f"Found Translate toggle with ID: {translate_toggle_id}")
                    break
        
        if translate_toggle_id:
            # Delete all content within the toggle
            toggle_blocks_response = notion.blocks.children.list(block_id=translate_toggle_id)
            toggle_blocks = toggle_blocks_response.get("results", [])
            
            for block in toggle_blocks:
                block_id = block.get("id")
                try:
                    notion.blocks.delete(block_id=block_id)
                    logging.info(f"Deleted block {block_id}")
                except Exception as e:
                    logging.error(f"Error deleting block {block_id}: {str(e)}")
            
            logging.info("Successfully cleared Translate toggle")
            return True
        else:
            # Translate toggle not found, will create it fresh
            logging.info("Translate toggle not found. Will create it fresh.")
            return True
    except Exception as e:
        logging.error(f"Error in clear_translate_toggle: {str(e)}")
        return False

if __name__ == "__main__":
    logging.info("Starting cleanup of Notion pages")
    clear_translate_toggle()
    logging.info("Cleanup completed") 