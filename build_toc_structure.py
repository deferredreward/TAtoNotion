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

def create_toggle(notion, parent_id, title, level=1, is_heading=False):
    """Create a toggle block with specified title and heading level."""
    try:
        # Use heading toggle for level 1 or if specifically requested
        if level == 1 or is_heading:
            toggle_block = {
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
                    ],
                    "is_toggleable": True,
                    "color": "default"
                }
            }
        else:
            # Use the paragraph toggle for other levels
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

def process_markdown_to_notion_blocks(markdown_text):
    """Convert markdown text to Notion blocks with proper formatting."""
    import re
    
    blocks = []
    
    # Split content into paragraphs
    paragraphs = markdown_text.split('\n\n')
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # Check if this is a heading
        heading_match = re.match(r'^(#+)\s+(.+)$', paragraph)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            
            if level == 1:
                block_type = "heading_1"
            elif level == 2:
                block_type = "heading_2"
            elif level == 3:
                block_type = "heading_3"
            else:
                block_type = "paragraph"  # Fallback for h4+
                
            blocks.append({
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": text
                            }
                        }
                    ],
                    "color": "default"
                }
            })
        
        # Check if this is a list item
        elif paragraph.startswith('* ') or paragraph.startswith('- '):
            text = paragraph[2:]
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": text
                            }
                        }
                    ],
                    "color": "default"
                }
            })
        
        # Check if this is a numbered list item
        elif re.match(r'^\d+\.\s+', paragraph):
            text = re.sub(r'^\d+\.\s+', '', paragraph)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": text
                            }
                        }
                    ],
                    "color": "default"
                }
            })
        
        # Otherwise, it's a regular paragraph
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": paragraph
                            }
                        }
                    ]
                }
            })
    
    return blocks

def create_article_page(notion, title, article_id, parent_id=None):
    """Create a new article page and populate it with content."""
    try:
        # If parent_id is provided, use it as the parent, otherwise use the main page
        if parent_id:
            parent_data = {"page_id": parent_id}
        else:
            parent_data = {"page_id": "1c372d5af2de80e08b11cd7748a1467d"}
        
        # Create the page
        page_data = {
            "parent": parent_data,
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
            # Process markdown content to Notion blocks with formatting
            blocks = process_markdown_to_notion_blocks(content)
            
            # Add blocks in batches to avoid rate limiting
            batch_size = 10
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i+batch_size]
                notion.blocks.children.append(
                    block_id=page_id,
                    children=batch
                )
                time.sleep(0.5)  # Small delay to prevent rate limiting
            
            # Process images and links
            images = extract_images_from_markdown(content)
            for img in images:
                add_image_to_page(notion, page_id, img["url"], img["caption"])
                time.sleep(0.5)
                
            links = extract_web_links_from_markdown(content)
            for link in links:
                add_web_link_to_page(notion, page_id, link["text"], link["url"])
                time.sleep(0.5)
        
        return page_id
    except Exception as e:
        logging.error(f"Error creating article page {title}: {str(e)}")
        return None

def create_section_page(notion, title, parent_id=None):
    """Create a new section page that will contain subsections."""
    try:
        # If parent_id is provided, use it as the parent, otherwise use the main page
        if parent_id:
            parent_data = {"page_id": parent_id}
        else:
            parent_data = {"page_id": "1c372d5af2de80e08b11cd7748a1467d"}
        
        # Create the page
        page_data = {
            "parent": parent_data,
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            }
        }
        
        response = notion.pages.create(**page_data)
        page_id = response.get("id")
        logging.info(f"Created new section page: {title} with ID: {page_id}")
        
        # Add a header with the section title
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
        
        return page_id
    except Exception as e:
        logging.error(f"Error creating section page {title}: {str(e)}")
        return None

def add_page_link_to_toggle(notion, parent_id, title, page_id, is_child=False, indent_level=0):
    """Add a link to a page in the TOC structure."""
    try:
        # Use different icons for different indentation levels
        if is_child:
            # Level 1 indentation: right arrow
            if indent_level == 1:
                prefix = "    → "
            # Level 2 indentation: small circle
            elif indent_level == 2:
                prefix = "        ○ "
            # Level 3+ indentation: small dot
            else:
                prefix = "            • "
        else:
            prefix = "📄 "
            
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
        return True
    except Exception as e:
        logging.error(f"Error creating page link for {title}: {str(e)}")
        return False

def build_section(notion, parent_id, section, parent_page_id=None, level=1, parent_section="", delay_seconds=0.5, indent_level=0, process_content=True):
    """
    Recursively build a section of the TOC with a hierarchical page structure.
    
    Top-level sections are created as toggles.
    Subsections are created as indented links with visual indicators (arrows, circles, dots).
    Pages are only created for actual articles with content.
    """
    title = section.get("title", "Untitled Section")
    link = section.get("link", "")
    subsections = section.get("sections", [])
    article_id = None
    
    if link:
        # Extract article ID from link
        article_id = link.split("/")[-1].replace(".md", "")
    
    # Create the actual page in the page hierarchy ONLY if it has article content
    page_id = None
    
    # If this section has article content, create a content page
    if article_id and process_content:
        # Check if the page already exists
        existing_page_id = find_page_by_title(notion, title)
        
        if existing_page_id:
            page_id = existing_page_id
            logging.info(f"Found existing page: {title}")
        else:
            # Create a new article page directly under the main page
            # We don't want to create a hierarchy of empty pages, so place all articles directly under the main page
            page_id = create_article_page(notion, title, article_id, "1c372d5af2de80e08b11cd7748a1467d")
            time.sleep(1)  # Delay to prevent rate limiting
    
    # Determine how to present this section in the TOC
    # Only top-level sections (level 1) and Just-in-Time Learning Modules are toggles
    should_be_toggle = (level == 1 or parent_section == "Just-in-Time Learning Modules")
    
    if should_be_toggle:
        # Create a toggle for this section
        container_id = create_toggle(notion, parent_id, title, level)
        
        if not container_id:
            return None
            
        time.sleep(delay_seconds)
        
        # Add a link to the page in the TOC if a page was created
        if page_id:
            add_page_link_to_toggle(notion, container_id, title, page_id)
            time.sleep(delay_seconds)
        
        # Process subsections under this toggle
        for subsection in subsections:
            build_section(
                notion, 
                container_id,  # Add under this toggle
                subsection, 
                None,         # Don't create a page hierarchy, all articles are top-level
                level + 1, 
                title,
                delay_seconds,
                indent_level=0,  # Reset indent level inside toggle
                process_content=process_content
            )
    else:
        # Create a visually indented link for this section
        if page_id:
            add_page_link_to_toggle(notion, parent_id, title, page_id, is_child=True, indent_level=indent_level)
            time.sleep(delay_seconds)
        else:
            # For sections without a page, just add them as text with indentation
            prefix = ""
            if indent_level == 1:
                prefix = "    → "
            elif indent_level == 2:
                prefix = "        ○ "
            else:
                prefix = "            • "
                
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
                                    "content": f"{prefix}{title}"
                                },
                                "annotations": {
                                    "bold": True
                                }
                            }
                        ]
                    }
                }]
            )
            time.sleep(delay_seconds)
        
        # Process subsections with increased indentation
        for subsection in subsections:
            build_section(
                notion, 
                parent_id,  # Add under the same parent (no toggle)
                subsection, 
                None,      # Don't create a page hierarchy, all articles are top-level
                level + 1, 
                title,
                delay_seconds,
                indent_level=indent_level + 1,  # Increase indentation
                process_content=process_content
            )
    
    return page_id

def build_translate_section(use_remote=True, process_content=True, section_limit=None, start_section=0):
    """
    Build the Translate section structure according to the TOC.
    
    Args:
        use_remote: Whether to fetch TOC data from remote or local file
        process_content: Whether to process article content (images and links)
        section_limit: Optional limit for number of top-level sections to process
        start_section: Index of the section to start processing from (default: 0)
    """
    # Load the TOC data
    toc_data = load_toc_data(use_remote=use_remote)
    
    if not toc_data:
        logging.error("Failed to load TOC data")
        return False
    
    # Use the specified page ID directly
    parent_page_id = "1c372d5af2de80e08b11cd7748a1467d"
    
    # Create a toggle for "Translate" on the parent page using H1 style
    translate_toggle_id = create_toggle(notion, parent_page_id, "Translate", level=1, is_heading=True)
    
    if not translate_toggle_id:
        logging.error("Failed to create Translate toggle")
        return False
    
    logging.info(f"Created H1 Translate toggle with ID: {translate_toggle_id}")
    
    # Get sections to process
    sections = toc_data.get("sections", [])
    
    # Apply start_section and limit if specified
    if start_section > 0 and start_section < len(sections):
        logging.info(f"Starting from section {start_section} ({sections[start_section]['title']})")
        sections = sections[start_section:]
    
    # Apply limit if specified
    if section_limit and isinstance(section_limit, int) and section_limit > 0:
        sections = sections[:section_limit]
        logging.info(f"Limited to {section_limit} sections")
    
    # Process all selected sections
    for section in sections:
        build_section(
            notion, 
            translate_toggle_id,  # Add to the Translate toggle in the TOC
            section, 
            None,                # Don't use page hierarchy, all articles are top-level
            level=1,
            parent_section="",
            delay_seconds=0.5,
            indent_level=0,
            process_content=process_content
        )
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