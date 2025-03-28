import os
import logging
import time
import argparse
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

def main(section_limit=None, start_section=1):
    """
    Master function to handle the full import process:
    1. Clean existing Notion toggle contents
    2. Build the TOC structure
    3. Process content, including images and links
    
    Args:
        section_limit: Optional limit for number of top-level sections to process
        start_section: Index of the section to start processing from (default: 1 for "Defining a Good Translation")
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
        logging.info(f"Limited to {section_limit} sections, starting from section {start_section}")
    else:
        logging.info(f"Processing all sections, starting from section {start_section}")
    
    success = build_translate_section(use_remote=True, process_content=True, 
                                     section_limit=section_limit, start_section=start_section)
    
    if success:
        logging.info("=== IMPORT PROCESS COMPLETED SUCCESSFULLY ===")
    else:
        logging.error("=== IMPORT PROCESS FAILED ===")
        
    return success

if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description='Import TOC and content into Notion')
    parser.add_argument('--sections', type=int, default=1, 
                        help='Number of sections to import (default: 1 for testing)')
    parser.add_argument('--start', type=int, default=1,
                        help='Index of section to start from (default: 1 for "Defining a Good Translation")')
    
    args = parser.parse_args()
    
    # Run the main function with the specified section limit and start section
    main(section_limit=args.sections, start_section=args.start) 