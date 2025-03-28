import os
import logging
import time
from dotenv import load_dotenv
from notion_client import Client

# Import the functions from our other scripts
from clean_notion_pages import clear_translate_toggle
from build_toc_structure import build_translate_section

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

def main(section_limit=None):
    """
    Master function to handle the full import process:
    1. Clean existing Notion toggle contents
    2. Build the TOC structure
    3. Process content, including images and links
    
    Args:
        section_limit: Optional limit for number of top-level sections to process
    """
    logging.info("=== STARTING FULL IMPORT PROCESS ===")
    
    # Step 1: Clean existing Notion toggle contents
    logging.info("Step 1: Cleaning existing Translate toggle contents")
    clear_translate_toggle()
    
    # Give Notion a moment to process the deletions
    time.sleep(2)
    
    # Step 2: Build the TOC structure with content processing
    logging.info("Step 2: Building TOC structure with content processing")
    if section_limit:
        logging.info(f"Limited to first {section_limit} sections")
    
    success = build_translate_section(use_remote=True, process_content=True, section_limit=section_limit)
    
    if success:
        logging.info("=== IMPORT PROCESS COMPLETED SUCCESSFULLY ===")
    else:
        logging.error("=== IMPORT PROCESS FAILED ===")
        
    return success

if __name__ == "__main__":
    # Set section_limit=2 to process only the first 2 sections (for testing)
    main(section_limit=2) 