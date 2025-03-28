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

def add_image_to_page(page_id, image_url, caption=""):
    """Add an image to a specific Notion page."""
    try:
        # Add the image block
        response = notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    },
                    "caption": [
                        {
                            "type": "text",
                            "text": {
                                "content": caption
                            }
                        }
                    ] if caption else []
                }
            }]
        )
        logging.info(f"Added image to page: {image_url}")
        return True
    except Exception as e:
        logging.error(f"Error adding image to page: {str(e)}")
        return False

def verify_page(page_id):
    """Verify that a page exists and return its title."""
    try:
        response = notion.pages.retrieve(page_id=page_id)
        page_title = response.get("properties", {}).get("title", {}).get("title", [{}])[0].get("text", {}).get("content", "")
        logging.info(f"Found page: {page_title} with ID: {page_id}")
        return page_title
    except Exception as e:
        logging.error(f"Error verifying page: {str(e)}")
        return None

if __name__ == "__main__":
    # The known page ID for the translation process page
    target_page_id = "1c472d5af2de81cbb7d2fd6f130529fd"
    
    # Verify the page exists
    page_title = verify_page(target_page_id)
    
    if page_title:
        # Add the image
        image_url = "https://cdn.door43.org/ta/jpg/translation_process.png"
        image_caption = "Simple translation process flowchart"
        success = add_image_to_page(target_page_id, image_url, image_caption)
        
        if success:
            logging.info(f"Successfully added image to '{page_title}' page")
        else:
            logging.error(f"Failed to add image to '{page_title}' page")
    else:
        logging.error(f"Could not find page with ID: {target_page_id}") 