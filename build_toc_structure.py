import os
import yaml
import time
import logging
import requests
import base64
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

# Parent Notion page ID
NOTION_PARENT_ID = os.environ.get("NOTION_PAGE_ID")

# Gitea API settings
GITEA_API_BASE = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_API_KEY = os.environ.get("GITEA_API_KEY")

# Global toggle index to track and ensure unique toggle IDs
toggle_index = 0

def fetch_gitea_content(path):
    """Fetch content from Gitea API."""
    url = f"{GITEA_API_BASE}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/contents/{path}"
    headers = {}
    if GITEA_API_KEY:
        headers["Authorization"] = f"token {GITEA_API_KEY}"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content
    except Exception as e:
        logging.error(f"Failed to fetch content from Gitea: {str(e)}")
        return None

def load_toc_data(file_path="toc.yaml", use_remote=True):
    """Load Table of Contents data from file or Gitea."""
    if use_remote:
        logging.info("Fetching TOC data from Gitea...")
        content = fetch_gitea_content("translate/toc.yaml")
        if content:
            try:
                return yaml.safe_load(content)
            except Exception as e:
                logging.error(f"Error parsing remote TOC data: {str(e)}")
                # Fall back to local file
    
    # Load from local file
    try:
        logging.info(f"Loading TOC data from local file: {file_path}")
        with open(file_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file.read())
    except Exception as e:
        logging.error(f"Error loading TOC data from {file_path}: {str(e)}")
        return {}

def find_page_by_title(notion, title):
    """Find a Notion page by title within the parent page."""
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

def create_top_level_page(title):
    """Create a new top-level page in Notion."""
    try:
        # If we don't have a parent page ID, we'll create a top-level page
        if not NOTION_PARENT_ID:
            page_data = {
                "parent": {"database_id": os.environ.get("NOTION_DATABASE_ID", "1c372d5a-f2de-80e0-8b11-cd7748a1467d")},
                "properties": {
                    "title": {"title": [{"text": {"content": title}}]}
                }
            }
        else:
            page_data = {
                "parent": {"page_id": NOTION_PARENT_ID},
                "properties": {
                    "title": {"title": [{"text": {"content": title}}]}
                }
            }
        
        response = notion.pages.create(**page_data)
        logging.info(f"Created top-level page: {title}")
        return response["id"]
    except Exception as e:
        logging.error(f"Error creating top-level page {title}: {e}")
        return None

def create_toggle(notion, parent_id, title, level=1):
    """Create a toggle block with specified title and heading level."""
    try:
        # Use the paragraph type for toggles as it's more reliable
        toggle_block = {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": title
                        }
                    }
                ],
                "color": "default"
            }
        }
        
        response = notion.blocks.children.append(
            block_id=parent_id,
            children=[toggle_block]
        )
        
        toggle_id = response.get("results", [{}])[0].get("id")
        logging.info(f"Created level {level} toggle: {title}")
        return toggle_id
    except Exception as e:
        logging.error(f"Error creating toggle {title}: {str(e)}")
        logging.error(f"Failed to create toggle for section {title}")
        return None

def fetch_article_content(article_id):
    """Fetch article content from Gitea."""
    path = f"translate/{article_id}/01.md"
    return fetch_gitea_content(path)

def extract_images_from_markdown(markdown_text):
    """Extract image URLs and captions from markdown content."""
    import re
    
    # Pattern to match markdown images: ![caption](url)
    image_pattern = r'!\[(.*?)\]\((.*?)\)'
    
    images = []
    for match in re.finditer(image_pattern, markdown_text):
        caption = match.group(1)
        url = match.group(2)
        
        # Convert relative URLs to absolute URLs
        if url.startswith("../"):
            url = url.replace("../", "https://git.door43.org/unfoldingWord/en_ta/raw/branch/master/translate/")
        elif not url.startswith(("http://", "https://")):
            url = f"https://git.door43.org/unfoldingWord/en_ta/raw/branch/master/translate/{url}"
            
        images.append({"caption": caption, "url": url})
        
    return images

def extract_web_links_from_markdown(markdown_text):
    """Extract web links from markdown content."""
    import re
    
    # Pattern to match markdown links: [text](url)
    link_pattern = r'\[(.*?)\]\((.*?)\)'
    
    links = []
    for match in re.finditer(link_pattern, markdown_text):
        text = match.group(1)
        url = match.group(2)
        
        # Skip image links (they start with !)
        if markdown_text[match.start()-1:match.start()] == '!':
            continue
            
        # Skip internal article links (we handle those separately)
        if "../" in url and "/01.md" in url:
            continue
            
        # Ensure URL is absolute
        if not url.startswith(("http://", "https://")):
            url = f"https://git.door43.org/unfoldingWord/en_ta/raw/branch/master/translate/{url}"
            
        links.append({"text": text, "url": url})
        
    return links

def add_image_to_page(notion, page_id, image_url, caption=""):
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

def update_translate_process_page():
    """Update the translate-process page with the flowchart image."""
    # First find the page by ID to verify it exists
    target_page_id = "1c472d5af2de81cbb7d2fd6f130529fd"
    
    try:
        # Verify the page exists
        response = notion.pages.retrieve(page_id=target_page_id)
        page_title = response.get("properties", {}).get("title", {}).get("title", [{}])[0].get("text", {}).get("content", "")
        logging.info(f"Found page: {page_title} with ID: {target_page_id}")
        
        # Add the image
        image_url = "https://cdn.door43.org/ta/jpg/translation_process.png"
        image_caption = "Simple translation process flowchart"
        add_image_to_page(notion, target_page_id, image_url, image_caption)
        
        return True
    except Exception as e:
        logging.error(f"Error updating translate process page: {str(e)}")
        return False

def find_page_by_article_id(notion, article_id):
    """Find a Notion page by its article ID."""
    try:
        # Get all pages
        translate_id = find_page_by_title(notion, "Translate")
        
        if not translate_id:
            logging.error("Translate page not found")
            return None
        
        # Recursively search through TOC structure
        toc_data = load_toc_data(use_remote=False)
        
        # Define a recursive function to search through sections
        def search_sections(sections):
            for section in sections:
                link = section.get("link", "")
                if link:
                    section_article_id = link.split("/")[-1].replace(".md", "")
                    if section_article_id == article_id:
                        return section.get("title", "")
                
                # Search in subsections
                subsections = section.get("sections", [])
                if subsections:
                    result = search_sections(subsections)
                    if result:
                        return result
            
            return None
        
        # Start the search
        article_title = search_sections(toc_data.get("sections", []))
        
        if article_title:
            # Now find the page by title
            page_id = find_page_by_title(notion, article_title)
            return page_id
            
        return None
    except Exception as e:
        logging.error(f"Error finding page by article ID: {str(e)}")
        return None

def update_page_with_image(article_id, image_url, caption=""):
    """Update a specific page identified by article ID with an image."""
    try:
        # Find the page by article ID
        page_id = find_page_by_article_id(notion, article_id)
        
        if not page_id:
            # Try directly with the provided ID as fallback
            page_id = article_id
            
        # Add the image
        success = add_image_to_page(notion, page_id, image_url, caption)
        
        if success:
            logging.info(f"Successfully updated page with image for article ID: {article_id}")
        else:
            logging.error(f"Failed to update page with image for article ID: {article_id}")
            
        return success
    except Exception as e:
        logging.error(f"Error in update_page_with_image: {str(e)}")
        return False

def add_web_link_to_page(notion, page_id, link_text, link_url):
    """Add a web link to a Notion page."""
    try:
        response = notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "🔗 ",
                            }
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": link_text,
                                "link": {"url": link_url}
                            },
                            "annotations": {
                                "color": "blue"
                            }
                        }
                    ]
                }
            }]
        )
        logging.info(f"Added web link: {link_text} → {link_url}")
        return True
    except Exception as e:
        logging.error(f"Error adding web link {link_text}: {str(e)}")
        return False

def process_article_content(notion, page_id, article_id):
    """Process article content to extract and add images and web links."""
    # Fetch article content
    content = fetch_article_content(article_id)
    
    if not content:
        logging.error(f"Failed to fetch content for article: {article_id}")
        return False
        
    # Extract and add images
    images = extract_images_from_markdown(content)
    for img in images:
        add_image_to_page(notion, page_id, img["url"], img["caption"])
        time.sleep(0.5)  # Delay to prevent rate limiting
        
    # Extract and add web links
    links = extract_web_links_from_markdown(content)
    for link in links:
        add_web_link_to_page(notion, page_id, link["text"], link["url"])
        time.sleep(0.5)  # Delay to prevent rate limiting
        
    return True

def create_article_page(notion, title, article_id):
    """Create a new article page in Notion and populate it with content."""
    try:
        # We need to use the parent page ID where our TOC is
        parent_page_id = "1c372d5af2de80e08b11cd7748a1467d"
        
        # Create the page
        page_data = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            }
        }
        
        response = notion.pages.create(**page_data)
        page_id = response.get("id")
        logging.info(f"Created new article page: {title} with ID: {page_id}")
        
        # Add a header with the article title
        notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }]
        )
        
        # Fetch the article content
        content = fetch_article_content(article_id)
        
        if content:
            # Convert the markdown content to Notion blocks
            # For now, we'll just add it as a paragraph
            paragraphs = content.split('\n\n')
            for paragraph in paragraphs:
                if paragraph.strip():
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=[{
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": paragraph.strip()
                                        }
                                    }
                                ]
                            }
                        }]
                    )
                    time.sleep(0.3)  # Small delay to prevent rate limiting
        
        return page_id
    except Exception as e:
        logging.error(f"Error creating article page {title}: {str(e)}")
        return None

def create_page_link(notion, parent_id, title, article_id, is_child=False, indent_level=0, process_content=True):
    """Create a link to another page in Notion, checking if it exists first."""
    try:
        # Check if we have this page in cache
        page_id = find_page_by_title(notion, title)
        
        # Use different icons for different indentation levels
        if is_child:
            # Level 1 indentation: right arrow
            if indent_level == 1:
                prefix = "    ↳ "
            # Level 2 indentation: small circle
            elif indent_level == 2:
                prefix = "      ○ "
            # Level 3+ indentation: small dot
            else:
                prefix = "        • "
        else:
            prefix = "📄 "
        
        if not page_id and article_id:
            # Create a new page for this article
            page_id = create_article_page(notion, title, article_id)
            time.sleep(0.5)  # Delay to prevent rate limiting
        
        if page_id:
            # Add a link to the page
            response = notion.blocks.children.append(
                block_id=parent_id,
                children=[{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": prefix,
                                },
                            },
                            {
                                "type": "text",
                                "text": {
                                    "content": title,
                                    "link": {"url": f"https://www.notion.so/{page_id.replace('-', '')}"}
                                },
                                "annotations": {
                                    "bold": True,
                                    "color": "blue"
                                }
                            }
                        ]
                    }
                }]
            )
            logging.info(f"Added page link: {title}")
            
            # Process article content if requested
            if process_content and article_id:
                process_article_content(notion, page_id, article_id)
                
            return page_id  # Return the page ID for possible further operations
        else:
            # Create a placeholder text entry without a link
            logging.info(f"Creating placeholder for: {title} (no article ID available)")
            response = notion.blocks.children.append(
                block_id=parent_id,
                children=[{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"{prefix}{title} (Not imported yet)"
                                }
                            }
                        ]
                    }
                }]
            )
            return False
    except Exception as e:
        logging.error(f"Error creating page link for {title}: {str(e)}")
        return False

def build_section(notion, parent_id, section, level=1, parent_section="", delay_seconds=0.5, is_child=False, indent_level=0, process_content=True):
    """
    Recursively build a section of the TOC with proper nesting.
    
    Uses toggle blocks for:
    - Top-level sections (level 1)
    - Sections that have many subsections (> 15)
    - Just-in-Time Learning Modules subsections
    
    Otherwise, creates direct links for articles with proper indentation for children.
    """
    title = section.get("title", "Untitled Section")
    link = section.get("link", "")
    subsections = section.get("sections", [])
    article_id = None
    
    if link:
        # Extract article ID from link
        article_id = link.split("/")[-1].replace(".md", "")
    
    # Determine if this section should be a toggle
    should_be_toggle = False
    
    # Rule 1: Top-level sections are always toggles
    if level == 1:
        should_be_toggle = True
    
    # Rule 2: "Just-in-Time Learning Modules" subsections are toggles
    elif parent_section == "Just-in-Time Learning Modules":
        should_be_toggle = True
    
    # Rule 3: Sections with many subsections (>15) are toggles
    elif len(subsections) > 15:
        should_be_toggle = True
    
    # Create toggle or direct link based on rules
    if should_be_toggle:
        # Create toggle for this section
        container_id = create_toggle(notion, parent_id, title, level)
        
        if not container_id:
            return
            
        # Add a slight delay to prevent rate limiting
        time.sleep(delay_seconds)
        
        # If this section has a link, create a page link inside the toggle
        if link and article_id:
            page_id = create_page_link(notion, container_id, title, article_id, process_content=process_content)
            time.sleep(delay_seconds)
        
        # Process subsections - they're all children of the toggle
        # Reset the indent level inside a toggle
        for subsection in subsections:
            build_section(notion, container_id, subsection, level + 1, title, delay_seconds, is_child=False, indent_level=0, process_content=process_content)
    else:
        # For non-toggle sections, just create a direct link
        if link and article_id:
            page_id = create_page_link(notion, parent_id, title, article_id, is_child=is_child, indent_level=indent_level, process_content=process_content)
            time.sleep(delay_seconds)
            
            # If this non-toggle has subsections, process them under the parent
            # but mark them as children for visual indentation
            # and increment the indent level for proper hierarchy
            if subsections:
                for subsection in subsections:
                    build_section(
                        notion, 
                        parent_id, 
                        subsection, 
                        level + 1, 
                        title, 
                        delay_seconds, 
                        is_child=True, 
                        indent_level=indent_level + 1,
                        process_content=process_content
                    )

def build_translate_section(use_remote=True, process_content=True, section_limit=None):
    """
    Build the Translate section structure according to the TOC.
    
    Args:
        use_remote: Whether to fetch TOC data from remote or local file
        process_content: Whether to process article content (images and links)
        section_limit: Optional limit for number of top-level sections to process
    """
    # Load the TOC data
    toc_data = load_toc_data(use_remote=use_remote)
    
    if not toc_data:
        logging.error("Failed to load TOC data")
        return False
    
    # Use the specified page ID directly
    parent_page_id = "1c372d5af2de80e08b11cd7748a1467d"
    
    # Create a toggle for "Translate" on the parent page
    translate_toggle_id = create_toggle(notion, parent_page_id, "Translate", level=1)
    
    if not translate_toggle_id:
        logging.error("Failed to create Translate toggle")
        return False
    
    logging.info(f"Created Translate toggle with ID: {translate_toggle_id}")
    
    # Get sections to process
    sections = toc_data.get("sections", [])
    
    # Apply limit if specified
    if section_limit and isinstance(section_limit, int) and section_limit > 0:
        sections = sections[:section_limit]
        logging.info(f"Limited to first {section_limit} sections")
    
    # Process all top-level sections
    for section in sections:
        build_section(notion, translate_toggle_id, section, is_child=False, indent_level=0, process_content=process_content)
        # Add a short delay between sections
        time.sleep(0.5)
    
    logging.info("Successfully built Translate section structure")
    return True

if __name__ == "__main__":
    logging.info("Starting to build TOC structure")
    # Set use_remote=False to use local toc.yaml file
    # Set process_content=True to process article content (images and web links)
    # Set section_limit=2 to process only the first 2 sections (for testing)
    success = build_translate_section(use_remote=False, process_content=True, section_limit=2)
    
    # Update the translate-process page with the image
    logging.info("Updating the translate-process page with flowchart image")
    update_page_with_image(
        "translate-process", 
        "https://cdn.door43.org/ta/jpg/translation_process.png",
        "Simple translation process flowchart"
    )
    
    # Also verify using the known page ID
    logging.info("Verifying with known page ID")
    add_image_to_page(
        notion,
        "1c472d5af2de81cbb7d2fd6f130529fd",
        "https://cdn.door43.org/ta/jpg/translation_process.png",
        "Simple translation process flowchart"
    )
    
    if success:
        logging.info("TOC structure built successfully")
    else:
        logging.error("Failed to build TOC structure") 