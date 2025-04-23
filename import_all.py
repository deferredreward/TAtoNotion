# import_all.py
import os
import time
import logging
import argparse
from dotenv import load_dotenv

# Import necessary functions from build_toc_structure
# Make sure build_toc_structure.py is in the same directory or accessible via PYTHONPATH
from build_toc_structure import (
    load_toc_data,
    load_config_data,
    build_manual_section, # Correct function name
    process_all_pages_links,
    load_cache_from_file,
    save_cache_to_file,
    fetch_article_title,
    create_section_page, # Import helper if needed here
    create_toggle,       # Import helper if needed here
    find_page_by_title,  # Import helper if needed here
    id_title_map_global, # Import the global map
    VISUAL_TOC_MAIN_PARENT_PAGE_ID, # Import constant with correct name
    HIERARCHY_MAIN_PARENT_ID      # Import constant
)
# Import cleanup function if needed (assuming it exists and is updated)
# from clean_notion_pages import clear_all_manual_pages # Example name

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("import_all.log"), # Log to a file
        logging.StreamHandler() # Also log to console
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Define the manuals to import
MANUAL_NAMES = ['intro', 'process', 'checking', 'translate']
# Note: VISUAL_TOC_MAIN_PARENT_PAGE_ID and HIERARCHY_MAIN_PARENT_ID are now imported

# --- Preprocessing: Build ID -> Title Map ---
def build_id_title_map(manuals):
    """Pre-fetches all titles to build a map of article_id to title."""
    logger.info("Preprocessing: Building Article ID -> Title map...")
    errors = 0
    start_time = time.time()
    # id_title_map_global is populated here
    id_title_map_global.clear() # Ensure it's empty before building

    for manual in manuals:
        toc_data = load_toc_data(manual)
        if not toc_data:
            logger.error(f"Failed to load TOC for manual: {manual}")
            errors += 1
            continue

        def process_toc_level(sections):
            nonlocal errors
            if not isinstance(sections, list): return

            for item in sections:
                title = item.get("title")
                article_id = item.get("link") # 'link' in toc.yaml is the article_id/slug
                subsections = item.get("sections", [])

                if article_id and title:
                    # Use TOC title for the map for consistency
                    display_title = title
                    if article_id not in id_title_map_global:
                         id_title_map_global[article_id] = display_title
                    elif id_title_map_global[article_id] != display_title:
                         logger.warning(f"ID Collision/Mismatch: Article ID '{article_id}' already mapped to '{id_title_map_global[article_id]}', new title is '{display_title}'. Keeping first mapping.")

                if subsections:
                    process_toc_level(subsections)

        process_toc_level(toc_data.get("sections", []))

    end_time = time.time()
    logger.info(f"Finished building ID->Title map ({len(id_title_map_global)} entries) in {end_time - start_time:.2f}s. Encountered {errors} TOC loading errors.")
    # Save the map as part of the cache immediately
    save_cache_to_file()


# --- Main Import Function ---
def main(manual_list, section_limit=None, start_section=0, start_subsection=None, use_remote=True, process_content=True, update_links=True, skip_cleanup=False, skip_existing=False):
    """Main function to process the TOC and create pages.
    
    Args:
        manual_list (list): List of manuals to process
        section_limit (int, optional): Limit on number of top-level sections to process
        start_section (int, optional): Index of top-level section to start from
        start_subsection (str, optional): Title of subsection to start from (will process parent but skip earlier siblings)
        use_remote (bool): Whether to use remote Gitea content
        process_content (bool): Whether to process article content
        update_links (bool): Whether to update links after processing
        skip_cleanup (bool): Whether to skip cleanup phase
        skip_existing (bool): Whether to skip creating pages that already exist
    """
    logger.info("Starting import process...")
    start_time = time.time()

    # Load cache if exists
    load_cache_from_file()

    # Build ID -> Title map first
    build_id_title_map(manual_list)

    # Validate and normalize manual list
    if isinstance(manual_list, str):
        manual_list = [manual_list]
    elif not manual_list:
        logger.error("No manuals specified to process")
        return

    # Load TOC and config data for all manuals
    all_manual_data = {}
    for manual in manual_list:
        toc_data = load_toc_data(manual)
        config_data = load_config_data(manual)
        if not toc_data:
            logger.error(f"Failed to load TOC for manual: {manual}")
            continue
        if not config_data:
            logger.warning(f"No config data loaded for manual: {manual}")
        all_manual_data[manual] = {"toc": toc_data, "config": config_data or {}}

    if not all_manual_data:
        logger.error("No valid manual data loaded. Exiting.")
        return

    # Create/find parent pages for each manual
    manual_hierarchy_parents = {}
    manual_visual_toc_parents = {}

    for manual in all_manual_data.keys():
        # Create hierarchy parent
        hierarchy_parent = find_page_by_title(manual.capitalize())
        if not hierarchy_parent:
            hierarchy_parent = create_section_page(manual, manual.capitalize(), HIERARCHY_MAIN_PARENT_ID)
        if hierarchy_parent:
            manual_hierarchy_parents[manual] = hierarchy_parent
            logger.info(f"Using hierarchy parent for {manual}: {hierarchy_parent}")
        else:
            logger.error(f"Failed to create/find hierarchy parent for {manual}")
            continue

        # Create visual TOC parent
        visual_parent = create_toggle(VISUAL_TOC_MAIN_PARENT_PAGE_ID, manual.capitalize(), level=1, is_heading=True)
        if visual_parent:
            manual_visual_toc_parents[manual] = visual_parent
            logger.info(f"Created visual TOC parent for {manual}: {visual_parent}")
        else:
            logger.warning(f"Failed to create visual TOC parent for {manual}, will skip visual TOC for this manual")

    # Process sections for each manual
    for manual, data in all_manual_data.items():
        logger.info(f"--- Processing Manual: {manual.capitalize()} ---")
        manual_toc = data["toc"]
        manual_config = data["config"]
        hierarchy_parent = manual_hierarchy_parents.get(manual)
        visual_parent = manual_visual_toc_parents.get(manual)

        if not hierarchy_parent:
             logger.error(f"Cannot process sections for '{manual}', hierarchy parent page ID is missing.")
             continue

        sections_to_process = manual_toc.get("sections", [])
        # Apply section limit and start index if specified (applies per manual)
        effective_start = max(0, start_section)
        if effective_start < len(sections_to_process):
            sections_to_process = sections_to_process[effective_start:]
            logger.info(f"Starting '{manual}' from section index {effective_start}")
        if section_limit is not None and section_limit > 0:
            sections_to_process = sections_to_process[:section_limit]
            logger.info(f"Limiting '{manual}' to {len(sections_to_process)} sections.")

        def find_subsection_path(sections, target, path=None):
            """Find path to target subsection title."""
            if path is None: path = []
            for i, section in enumerate(sections):
                current_path = path + [i]
                if section.get("title") == target:
                    return current_path
                if "sections" in section:
                    result = find_subsection_path(section["sections"], target, current_path)
                    if result: return result
            return None

        # If start_subsection specified, find its path and mark sections to skip
        skip_until_section = None
        if start_subsection:
            subsection_path = find_subsection_path(sections_to_process, start_subsection)
            if subsection_path:
                logger.info(f"Found path to subsection '{start_subsection}': {subsection_path}")
                skip_until_section = start_subsection
            else:
                logger.warning(f"Could not find subsection '{start_subsection}', will process all sections")

        for section_data in sections_to_process:
            # Pass the specific parents for this manual and skip info
            build_manual_section(
                manual_name=manual,
                manual_toc_data=section_data,
                manual_config_data=manual_config,
                visual_toc_parent_id=visual_parent,
                hierarchy_parent_page_id=hierarchy_parent,
                level=1,
                delay_seconds=0.5,
                process_content=process_content,
                skip_existing=skip_existing,
                skip_until_section=skip_until_section
            )
            time.sleep(0.5)

    end_time = time.time()
    logger.info(f"Import process completed in {end_time - start_time:.2f}s")

    # Post-processing: Update links in all created pages
    if update_links:
        logger.info("Starting link update post-processing...")
        process_all_pages_links()

    if not skip_cleanup:
        # Cleanup: Save final cache state
        save_cache_to_file()


# --- Script Execution ---
if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Setup argument parser
    parser = argparse.ArgumentParser(description="Import Translation Academy content to Notion")
    parser.add_argument("--manuals", help="Comma-separated list of manuals to process (e.g., 'translate,checking')")
    parser.add_argument("--sections", type=int, help="Number of sections to process")
    parser.add_argument("--start", type=int, default=0, help="Section index to start from")
    parser.add_argument("--subsection", help="Title of subsection to start from")
    parser.add_argument("--no-remote", action="store_true", help="Don't use remote content")
    parser.add_argument("--no-content", action="store_true", help="Don't process article content")
    parser.add_argument("--no-links", action="store_true", help="Don't update links after processing")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup phase")
    parser.add_argument("--skip-existing", action="store_true", help="Skip creating pages that already exist")

    args = parser.parse_args()
    
    if not args.manuals:
        parser.error("--manuals is required")
    
    manual_list = [m.strip() for m in args.manuals.split(",")]
    
    main(
        manual_list=manual_list,
        section_limit=args.sections,
        start_section=args.start,
        start_subsection=args.subsection,
        use_remote=not args.no_remote,
        process_content=not args.no_content,
        update_links=not args.no_links,
        skip_cleanup=args.skip_cleanup,
        skip_existing=args.skip_existing
    )