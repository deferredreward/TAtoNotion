import os
import logging
import time
import argparse
from dotenv import load_dotenv
from notion_client import Client
from clean_notion_pages import clear_translate_page
from build_toc_structure import build_translate_section
from post_process_links import update_gitea_links_to_internal

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

def main(section_limit=None, start_section=0, process_links=True):
    """
    Run the full import process:
    1. Clean existing pages
    2. Build TOC structure and process content
    3. Post-process links to update any Gitea links to internal Notion links
    
    Args:
        section_limit (int, optional): Limit to a specific number of top-level sections.
        start_section (int, optional): Start from a specific section index.
        process_links (bool, optional): Whether to run the link post-processing.
    """
    logging.info("=== STARTING FULL IMPORT PROCESS ===")
    
    # Step 1: Clean existing pages
    logging.info("Step 1: Cleaning existing Translate toggle contents")
    clear_translate_page()
    
    # Small delay to allow Notion to process deletions
    time.sleep(2)
    
    # Step 2: Build TOC structure and process content
    logging.info("Step 2: Building TOC structure with content processing")
    if section_limit:
        logging.info(f"Limited to {section_limit} sections, starting from section {start_section}")
    
    success = build_translate_section(use_remote=True, process_content=True,
                                     section_limit=section_limit, start_section=start_section,
                                     update_links=False)  # Don't update links during build
    
    if not success:
        logging.error("Failed to build TOC structure")
        return False
        
    # Step 3: Post-process links (if requested)
    if process_links:
        logging.info("Step 3: Post-processing links to update Gitea links to internal Notion links")
        update_gitea_links_to_internal()
    
    logging.info("=== IMPORT PROCESS COMPLETE ===")
    return True

if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Run the full Notion import process.")
    parser.add_argument('--sections', type=int, default=None, 
                        help='Limit the number of top-level sections to process.')
    parser.add_argument('--start', type=int, default=0, 
                        help='The 1-based index of the top-level section to start processing from.')
    parser.add_argument('--no-remote', action='store_true', 
                        help='Use local toc.yaml instead of fetching from Gitea.')
    parser.add_argument('--no-content', action='store_true', 
                        help='Skip processing and adding article content (only build structure).')
    parser.add_argument('--no-link-update', action='store_true', 
                        help='Skip the final phase of updating Gitea links to Notion links.')
                        
    args = parser.parse_args()
    
    # Calculate 0-based start index
    start_index = args.start - 1 if args.start > 0 else 0
    
    # Determine flags
    use_remote_data = not args.no_remote
    process_article_content = not args.no_content
    update_internal_links = not args.no_link_update
    
    # Run the main import process with parsed arguments
    # Remove section_limit=2 for full import
    main(
        section_limit=args.sections, 
        start_section=start_index, 
        process_links=update_internal_links
    ) 