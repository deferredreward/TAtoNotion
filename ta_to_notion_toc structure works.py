import os
import re
import yaml
import logging
import argparse
import time
from dotenv import load_dotenv
import requests
import markdown
import base64
from notion_client import Client
from notion_client.errors import APIResponseError

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ta_to_notion_toc.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))
gitea_api_key = os.environ.get("GITEA_API_KEY")

# Gitea API base URL
GITEA_API_BASE = "https://git.door43.org/api/v1"
REPO_OWNER = "unfoldingWord"
REPO_NAME = "en_ta"

# Notion parent page ID (where to create content)
NOTION_PARENT_ID = os.environ.get("NOTION_PARENT_ID", "1c372d5a-f2de-80e0-8b11-cd7748a1467d")

# Global cache for created pages to avoid duplicate lookups
page_cache = {}

def load_toc_data(file_path="toc.yaml", use_remote=True):
    """Load table of contents data from YAML file or remote repository."""
    try:
        if use_remote:
            # Fetch from repository
            endpoint = f"{GITEA_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/translate/toc.yaml"
            headers = {"Authorization": f"token {gitea_api_key}"}
            
            response = requests.get(endpoint, headers=headers)
            response.raise_for_status()
            content_data = response.json()
            
            if 'content' in content_data:
                content = base64.b64decode(content_data['content']).decode('utf-8')
                return yaml.safe_load(content)
            else:
                logger.error("No content found for TOC data")
                # Fall back to local file
                logger.info("Falling back to local TOC file")
                use_remote = False
        
        if not use_remote:
            with open(file_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
    except Exception as e:
        logger.error(f"Error loading TOC data: {str(e)}")
        if use_remote:
            logger.info("Falling back to local TOC file")
            return load_toc_data(file_path, use_remote=False)
        return None

def load_config_data(file_path="config.yaml", use_remote=True):
    """Load config data (dependencies and recommendations) from YAML file or remote repository."""
    try:
        if use_remote:
            # Fetch from repository
            endpoint = f"{GITEA_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/translate/config.yaml"
            headers = {"Authorization": f"token {gitea_api_key}"}
            
            response = requests.get(endpoint, headers=headers)
            response.raise_for_status()
            content_data = response.json()
            
            if 'content' in content_data:
                content = base64.b64decode(content_data['content']).decode('utf-8')
                return yaml.safe_load(content)
            else:
                logger.error("No content found for config data")
                # Fall back to local file
                logger.info("Falling back to local config file")
                use_remote = False
        
        if not use_remote:
            with open(file_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
    except Exception as e:
        logger.error(f"Error loading config data: {str(e)}")
        if use_remote:
            logger.info("Falling back to local config file")
            return load_config_data(file_path, use_remote=False)
        return None

def fetch_gitea_content(article_folder, file_path):
    """Fetch content from Gitea API."""
    endpoint = f"{GITEA_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/translate/{article_folder}/{file_path}"
    headers = {"Authorization": f"token {gitea_api_key}"}
    
    # Check if we've already cached this content
    cache_key = f"{article_folder}_{file_path}"
    if cache_key in page_cache:
        return page_cache[cache_key]
    
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        content_data = response.json()
        if 'content' in content_data:
            content = base64.b64decode(content_data['content']).decode('utf-8')
            # Cache the content for future use
            page_cache[cache_key] = content
            
            # If we're fetching a title file, also store it with a special key
            if file_path == "title.md":
                title = content.strip()
                page_cache[f"{article_folder}_title"] = title
                logger.info(f"Cached title for {article_folder}: {title}")
            
            return content
        else:
            logger.error(f"No content found for {article_folder}/{file_path}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error fetching {article_folder}/{file_path}: {str(e)}")
        return None

def create_top_level_page(title, update_existing=False):
    """
    Create or find a top-level page under the parent database.
    
    Args:
        title (str): The title of the page
        update_existing (bool): Whether to update an existing page
        
    Returns:
        str: The page ID
    """
    # Check if the page already exists
    page_id = find_page_by_title(NOTION_PARENT_ID, title)
    
    if page_id:
        logger.info(f"Found existing top-level page: {title} ({page_id})")
        return page_id
    
    # Create a new page
    try:
        response = notion.pages.create(
            parent={"page_id": NOTION_PARENT_ID},
            properties={
                "title": [
                    {
                        "type": "text",
                        "text": {"content": title}
                    }
                ]
            }
        )
        page_id = response["id"]
        logger.info(f"Created new top-level page: {title} ({page_id})")
        return page_id
    except Exception as e:
        logger.error(f"Error creating top-level page: {e}")
        return None

def create_section_page(parent_id, title, level=2, update_existing=False):
    """Create a section page with appropriate heading level or update an existing one."""
    try:
        if not parent_id:
            logger.error(f"Cannot create section page '{title}': Invalid parent ID")
            return None
            
        # Make sure level is between 1 and 3
        safe_level = max(1, min(level, 3))
        heading_type = f"heading_{safe_level}"
        
        # Check if the page already exists
        existing_page_id = None
        if update_existing:
            existing_page_id = find_page_by_title(parent_id, title)
        
        if existing_page_id and update_existing:
            # Update existing page
            children = [
                {
                    "object": "block",
                    "type": heading_type,
                    heading_type: {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    }
                }
            ]
            
            if update_page_content(existing_page_id, children):
                logger.info(f"Updated section page: {title}")
                return existing_page_id
            else:
                logger.error(f"Failed to update section page: {title}")
                return None
        else:
            # Create new page
            page_data = {
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    }
                },
                "children": [
                    {
                        "object": "block",
                        "type": heading_type,
                        heading_type: {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": title
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
            
            response = notion.pages.create(**page_data)
            logger.info(f"Created section page: {title} (level: {safe_level})")
            
            # Also store in page cache
            section_id = response["id"]
            page_cache[title] = section_id
            
            return section_id
    except Exception as e:
        logger.error(f"Error creating/updating section page {title}: {str(e)}")
        return None

def check_article_exists(title):
    """Check if an article with the given title already exists in Notion."""
    if title in page_cache:
        return page_cache[title]

    try:
        response = notion.databases.query(
            database_id=NOTION_PARENT_ID,
            filter={
                "property": "title",
                "title": {
                    "equals": title
                }
            }
        )
        
        if response["results"]:
            page_id = response["results"][0]["id"]
            page_cache[title] = page_id
            return page_id
        return None
    except Exception as e:
        logger.error(f"Error checking if article exists: {str(e)}")
        return None

def parse_rich_text(text):
    """Parse markdown text for basic formatting (bold, italic, links)."""
    # Process bold formatting (**text**)
    bold_pattern = r'\*\*([^*]+)\*\*'
    # Process italic formatting (*text*)
    italic_pattern = r'\*([^*]+)\*'
    # Process links - find all [text](url) patterns
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    # Find all formatting matches
    rich_text = []
    
    # Process links first
    if re.search(link_pattern, text):
        link_matches = list(re.finditer(link_pattern, text))
        
        # Process text with links
        last_end = 0
        for match in link_matches:
            # Add any text before the link
            if match.start() > last_end:
                before_text = text[last_end:match.start()]
                if before_text:
                    # Process the text before for bold/italic
                    rich_text.extend(process_formatting(before_text))
            
            # Add the link itself
            link_text = match.group(1)
            link_url = match.group(2)
            
            # Check if this is an internal link to another article
            is_internal_link = False
            article_id = None
            
            # Parse internal links like "../figs-apostrophe/01.md"
            if "../" in link_url and "/01.md" in link_url:
                parts = link_url.split("/")
                article_id = next((part for part in parts if part and part != ".." and part != "01.md"), None)
                is_internal_link = bool(article_id)
                logger.debug(f"Found internal link to article: {article_id}")
            
            # Process formatting within link text
            link_text_items = process_formatting(link_text)
            
            # Apply the link to all items
            for item in link_text_items:
                if item["type"] == "text":
                    # If it's an internal link and we have the page ID in cache, link to the Notion page
                    if is_internal_link and article_id and article_id in page_cache:
                        notion_url = f"https://www.notion.so/{page_cache[article_id].replace('-', '')}"
                        item["text"]["link"] = {"url": notion_url}
                        logger.debug(f"Created Notion link for article: {article_id} -> {notion_url}")
                    elif is_internal_link:
                        # We have an internal link but no page ID in cache
                        # Try to find the title for the article to at least make it bold
                        title_key = f"{article_id}_title"
                        if title_key in page_cache:
                            # Just add the article name with bold formatting for now
                            # The links can be updated later when we have IDs
                            item["annotations"] = item.get("annotations", {})
                            item["annotations"]["bold"] = True
                            logger.debug(f"No page ID for article: {article_id}, using bold formatting")
                        else:
                            # Still use the link as-is but mark it for potential later processing
                            item["text"]["link"] = {"url": link_url}
                            # Store the article ID in the page cache to facilitate later processing
                            if article_id:
                                page_cache[f"{article_id}_pending"] = True
                                logger.debug(f"Marked article {article_id} for pending link processing")
                    else:
                        # External link or file link - use as-is
                        item["text"]["link"] = {"url": link_url}
            
            rich_text.extend(link_text_items)
            last_end = match.end()
        
        # Add any text after the last link
        if last_end < len(text):
            after_text = text[last_end:]
            if after_text:
                rich_text.extend(process_formatting(after_text))
    else:
        # No links, just process formatting
        rich_text.extend(process_formatting(text))
    
    # If no text was processed, add an empty text object
    if not rich_text:
        rich_text.append({
            "type": "text",
            "text": {"content": text}
        })
    
    return rich_text

def process_formatting(text):
    """Process bold and italic formatting in text."""
    # Process bold formatting (**text**)
    bold_pattern = r'\*\*([^*]+)\*\*'
    # Process italic formatting (*text*)
    italic_pattern = r'\*([^*]+)\*'
    
    rich_text = []
    
    # First check for combined formatting patterns
    combined_matches = list(re.finditer(r'\*\*\*([^*]+)\*\*\*', text))
    
    if combined_matches:
        last_end = 0
        for match in combined_matches:
            # Add any text before with normal formatting
            if match.start() > last_end:
                before_text = text[last_end:match.start()]
                if before_text:
                    rich_text.extend(process_simple_formatting(before_text))
            
            # Add the combined bold+italic text
            content = match.group(1)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": True, "italic": True}
            })
            last_end = match.end()
        
        # Add any text after the last match
        if last_end < len(text):
            after_text = text[last_end:]
            if after_text:
                rich_text.extend(process_simple_formatting(after_text))
    else:
        # No combined formatting, process separately
        rich_text.extend(process_simple_formatting(text))
    
    return rich_text

def process_simple_formatting(text):
    """Process bold and italic separately."""
    # Process bold formatting (**text**)
    bold_pattern = r'\*\*([^*]+)\*\*'
    # Process italic formatting (*text*)
    italic_pattern = r'\*([^*]+)\*'
    
    rich_text = []
    
    # Process bold
    bold_matches = list(re.finditer(bold_pattern, text))
    
    if bold_matches:
        last_end = 0
        for match in bold_matches:
            # Add any text before
            if match.start() > last_end:
                before_text = text[last_end:match.start()]
                if before_text:
                    # Process for italic
                    italic_text = process_italic(before_text)
                    rich_text.extend(italic_text)
            
            # Add the bold text
            content = match.group(1)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": True}
            })
            last_end = match.end()
        
        # Add any text after the last bold
        if last_end < len(text):
            after_text = text[last_end:]
            if after_text:
                italic_text = process_italic(after_text)
                rich_text.extend(italic_text)
    else:
        # No bold, just process italic
        italic_text = process_italic(text)
        rich_text.extend(italic_text)
    
    return rich_text

def process_italic(text):
    """Process only italic formatting."""
    italic_pattern = r'\*([^*]+)\*'
    
    rich_text = []
    italic_matches = list(re.finditer(italic_pattern, text))
    
    if italic_matches:
        last_end = 0
        for match in italic_matches:
            # Add any text before
            if match.start() > last_end:
                before_text = text[last_end:match.start()]
                if before_text:
                    rich_text.append({
                        "type": "text",
                        "text": {"content": before_text}
                    })
            
            # Add the italic text
            content = match.group(1)
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"italic": True}
            })
            last_end = match.end()
        
        # Add any text after the last italic
        if last_end < len(text):
            after_text = text[last_end:]
            if after_text:
                rich_text.append({
                    "type": "text",
                    "text": {"content": after_text}
                })
    else:
        # No formatting, just plain text
        rich_text.append({
            "type": "text",
            "text": {"content": text}
        })
    
    return rich_text

def convert_to_unicode_superscript(match):
    text = match.group(1)
    # For any text inside <sup>, convert all characters to superscript
    return convert_number_to_superscript(text)

def convert_number_to_superscript(text):
    superscript_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
        'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
        'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
        'p': 'ᵖ', 'q': 'ᵠ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ',
        'u': 'ᵘ', 'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ',
        'z': 'ᶻ', 'A': 'ᴬ', 'B': 'ᴮ', 'C': 'ᶜ', 'D': 'ᴰ',
        'E': 'ᴱ', 'F': 'ᶠ', 'G': 'ᴳ', 'H': 'ᴴ', 'I': 'ᴵ',
        'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ', 'M': 'ᴹ', 'N': 'ᴺ',
        'O': 'ᴼ', 'P': 'ᴾ', 'Q': 'ᵠ', 'R': 'ᴿ', 'S': 'ˢ',
        'T': 'ᵀ', 'U': 'ᵁ', 'V': 'ⱽ', 'W': 'ᵂ', 'X': 'ˣ',
        'Y': 'ʸ', 'Z': 'ᶻ', '+': '⁺', '-': '⁻', '=': '⁼',
        '(': '⁽', ')': '⁾', '[': '⁽', ']': '⁾'
    }
    result = ""
    for char in text:
        if char in superscript_map:
            result += superscript_map[char]
        else:
            result += char  # Keep as is if no superscript equivalent
    return result

def convert_markdown_to_notion_blocks(markdown_content, optimize_blocks=True, block_limit=95):
    """Convert markdown content to Notion blocks with header level promotion and block optimization."""
    # Define the superscript conversion function first
    
    # Pre-process the content to handle specific formatting cases
    # 1. Handle escaped brackets like \[text\]
    markdown_content = re.sub(r'\\\[(.*?)\\\]', r'[\1]', markdown_content)
    
    # 2. Handle specific footnote pattern like: > 53 \[Then everyone... [2]\]
    # This pattern refers to normal numbered references, not in superscript
    # We'll leave these as is, because we want to preserve these brackets
    
    # 3. Handle superscript tags <sup>text</sup>
    markdown_content = re.sub(r'<sup>(.*?)</sup>', convert_to_unicode_superscript, markdown_content)
    
    # 4. Apply superscript conversion for ^{} notation
    markdown_content = re.sub(r'\^\{(.*?)\}', convert_to_unicode_superscript, markdown_content)
    
    blocks = []
    
    # Split the content into lines
    lines = markdown_content.splitlines()
    
    # First, analyze header levels in the content
    header_levels = []
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            header_levels.append(1)
        elif line.startswith("## "):
            header_levels.append(2)
        elif line.startswith("### "):
            header_levels.append(3)
        elif line.startswith("#### "):
            header_levels.append(4)
        elif line.startswith("##### "):
            header_levels.append(5)
        elif line.startswith("###### "):
            header_levels.append(6)
    
    # Count total potential blocks to see if we need optimization
    potential_block_count = len([line for line in lines if line.strip()])
    logger.info(f"Potential block count before optimization: {potential_block_count}")
    
    # Calculate how many levels to promote
    # We want the minimum header to be h1 and max not to exceed h3
    promotion_levels = 0
    
    # New promotion logic:
    # 1. If header levels are between 3-4, promote one level
    # 2. If header levels are between 3-5, promote two levels
    # 3. If header levels are between 2-4, don't promote and make h4 bold
    if header_levels:
        min_header = min(header_levels)
        max_header = max(header_levels)
        
        if min_header == 3 and max_header == 4:
            promotion_levels = 1
            logger.info(f"Header levels found: {header_levels}, promoting by {promotion_levels} levels (3-4 range)")
        elif min_header == 3 and max_header == 5:
            promotion_levels = 2
            logger.info(f"Header levels found: {header_levels}, promoting by {promotion_levels} levels (3-5 range)")
        elif min_header == 2 and max_header == 4:
            promotion_levels = 0
            logger.info(f"Header levels found: {header_levels}, no promotion (2-4 range, will convert h4 to bold)")
        else:
            # Default promotion logic from before
            promotion_levels = min_header - 1 if min_header > 1 else 0
            
            # If after promotion we still have h4+, calculate additional promotion
            if max_header - promotion_levels > 3:
                promotion_levels = max_header - 3
            
            logger.info(f"Header levels found: {header_levels}, promoting by {promotion_levels} levels (default logic)")
    else:
        logger.info("No headers found in content")
    
    i = 0
    current_paragraph = []
    
    # Track consecutive paragraphs for optimization
    paragraph_buffer = []
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Handle paragraph breaks
        if not line:
            if current_paragraph:
                # Join the paragraph lines
                paragraph_text = " ".join(current_paragraph)
                
                if optimize_blocks and len(blocks) > 0 and len(blocks) + potential_block_count > block_limit:
                    # Add to paragraph buffer for potential consolidation
                    paragraph_buffer.append(paragraph_text)
                else:
                    # Add as regular paragraph block
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Check if we have multiple paragraphs buffered and need to consolidate
            if optimize_blocks and paragraph_buffer and (i == len(lines) - 1 or lines[i+1].strip().startswith("#") or 
                lines[i+1].strip().startswith("* ") or lines[i+1].strip().startswith("- ") or 
                re.match(r'^\d+\.\s', lines[i+1].strip())):
                # Combine buffered paragraphs with double line breaks between them
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block")
                paragraph_buffer = []
            
            i += 1
            continue
        
        # Check for headings with promotion
        if line.startswith("# "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a heading
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before heading")
                paragraph_buffer = []
            
            # Promote h1
            promoted_level = max(1, 1 - promotion_levels)
            if promoted_level <= 3:
                blocks.append({
                    "object": "block",
                    "type": f"heading_{promoted_level}",
                    f"heading_{promoted_level}": {
                        "rich_text": parse_rich_text(line[2:])
                    }
                })
            else:
                # Convert to bold paragraph if we can't promote to h1-h3
                bold_text = parse_rich_text(line[2:])
                for item in bold_text:
                    if item["type"] == "text":
                        if "annotations" not in item:
                            item["annotations"] = {}
                        item["annotations"]["bold"] = True
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": bold_text
                    }
                })
        elif line.startswith("## "):
            # Similar logic for h2, h3, h4, h5, h6 (same pattern as h1 above)
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a heading
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before heading")
                paragraph_buffer = []
            
            # Promote h2
            promoted_level = max(1, 2 - promotion_levels)
            if promoted_level <= 3:
                blocks.append({
                    "object": "block",
                    "type": f"heading_{promoted_level}",
                    f"heading_{promoted_level}": {
                        "rich_text": parse_rich_text(line[3:])
                    }
                })
            else:
                # Convert to bold paragraph if we can't promote to h1-h3
                bold_text = parse_rich_text(line[3:])
                for item in bold_text:
                    if item["type"] == "text":
                        if "annotations" not in item:
                            item["annotations"] = {}
                        item["annotations"]["bold"] = True
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": bold_text
                    }
                })
        elif line.startswith("### "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a heading
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before numbered list")
                paragraph_buffer = []
            
            # Promote h3
            promoted_level = max(1, 3 - promotion_levels)
            if promoted_level <= 3:
                blocks.append({
                    "object": "block",
                    "type": f"heading_{promoted_level}",
                    f"heading_{promoted_level}": {
                        "rich_text": parse_rich_text(line[4:])
                    }
                })
            else:
                # Convert to bold paragraph if we can't promote to h1-h3
                bold_text = parse_rich_text(line[4:])
                for item in bold_text:
                    if item["type"] == "text":
                        if "annotations" not in item:
                            item["annotations"] = {}
                        item["annotations"]["bold"] = True
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": bold_text
                    }
                })
        elif line.startswith("#### "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a heading
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before heading")
                paragraph_buffer = []
            
            # Promote h4
            promoted_level = max(1, 4 - promotion_levels)
            if promoted_level <= 3:
                blocks.append({
                    "object": "block",
                    "type": f"heading_{promoted_level}",
                    f"heading_{promoted_level}": {
                        "rich_text": parse_rich_text(line[5:])
                    }
                })
            else:
                # Convert to bold paragraph if we can't promote to h1-h3
                bold_text = parse_rich_text(line[5:])
                for item in bold_text:
                    if item["type"] == "text":
                        if "annotations" not in item:
                            item["annotations"] = {}
                        item["annotations"]["bold"] = True
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": bold_text
                    }
                })
        elif line.startswith("##### "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a heading
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before heading")
                paragraph_buffer = []
            
            # Promote h5
            promoted_level = max(1, 5 - promotion_levels)
            if promoted_level <= 3:
                blocks.append({
                    "object": "block",
                    "type": f"heading_{promoted_level}",
                    f"heading_{promoted_level}": {
                        "rich_text": parse_rich_text(line[6:])
                    }
                })
            else:
                # Convert to bold paragraph if we can't promote to h1-h3
                bold_text = parse_rich_text(line[6:])
                for item in bold_text:
                    if item["type"] == "text":
                        if "annotations" not in item:
                            item["annotations"] = {}
                        item["annotations"]["bold"] = True
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": bold_text
                    }
                })
        # Check for lists
        elif line.startswith("* ") or line.startswith("- "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a list
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before list")
                paragraph_buffer = []
            
            # Start of a list
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("* ") or lines[i].strip().startswith("- ")):
                list_item = lines[i].strip()[2:]  # Remove the "* " or "- "
                list_items.append(list_item)
                i += 1
            
            # If we need to optimize and there are multiple list items, we can combine them into one paragraph with bullets
            if optimize_blocks and len(list_items) > 3 and len(blocks) + potential_block_count > block_limit:
                combined_list = "\n• " + "\n• ".join(list_items)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_list)
                    }
                })
                logger.info(f"Consolidated {len(list_items)} list items into one paragraph block")
            else:
                # Create a bulleted list block for each item
                for item in list_items:
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": parse_rich_text(item)
                        }
                    })
            
            continue  # Skip the increment at the end
        # Check for numbered lists
        elif re.match(r'^\d+\.\s', line):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a list
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before numbered list")
                paragraph_buffer = []
            
            # Start of a numbered list
            list_items = []
            while i < len(lines) and re.match(r'^\d+\.\s', lines[i].strip()):
                list_item = re.sub(r'^\d+\.\s', '', lines[i].strip())
                list_items.append(list_item)
                i += 1
            
            # If we need to optimize and there are multiple list items, we can combine them into one paragraph with numbers
            if optimize_blocks and len(list_items) > 3 and len(blocks) + potential_block_count > block_limit:
                combined_list_items = []
                for idx, item in enumerate(list_items, 1):
                    combined_list_items.append(f"{idx}. {item}")
                combined_list = "\n".join(combined_list_items)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_list)
                    }
                })
                logger.info(f"Consolidated {len(list_items)} numbered list items into one paragraph block")
            else:
                # Create a numbered list block for each item
                for item in list_items:
                    blocks.append({
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": parse_rich_text(item)
                        }
                    })
            
            continue  # Skip the increment at the end
        # Check for blockquotes
        elif line.startswith("> "):
            # Flush any pending paragraph
            if current_paragraph:
                paragraph_text = " ".join(current_paragraph)
                if optimize_blocks and len(blocks) + potential_block_count > block_limit:
                    paragraph_buffer.append(paragraph_text)
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": parse_rich_text(paragraph_text)
                        }
                    })
                current_paragraph = []
            
            # Flush paragraph buffer before adding a blockquote
            if paragraph_buffer:
                combined_text = "\n\n".join(paragraph_buffer)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(combined_text)
                    }
                })
                logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one block before blockquote")
                paragraph_buffer = []
            
            # Collect consecutive blockquote lines
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_line = lines[i].strip()[2:]  # Remove the "> "
                quote_lines.append(quote_line)
                i += 1
            
            quote_content = " ".join(quote_lines)
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": parse_rich_text(quote_content)
                }
            })
            continue  # Skip the increment at the end
        # Default: collect lines for paragraph
        else:
            current_paragraph.append(line)
        
        i += 1
    
    # Add any remaining paragraph content
    if current_paragraph:
        paragraph_text = " ".join(current_paragraph)
        if optimize_blocks and paragraph_buffer:
            paragraph_buffer.append(paragraph_text)
            combined_text = "\n\n".join(paragraph_buffer)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(combined_text)
                }
            })
            logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one final block")
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(paragraph_text)
                }
            })
    elif paragraph_buffer:
        # Flush any remaining paragraph buffer
        combined_text = "\n\n".join(paragraph_buffer)
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": parse_rich_text(combined_text)
            }
        })
        logger.info(f"Consolidated {len(paragraph_buffer)} paragraphs into one final block")
    
    # Add block count logging
    logger.info(f"Final block count after optimization: {len(blocks)}")
    
    return blocks

def create_article_page(parent_id, article_id, config_data, update_existing=False):
    """Create a Notion page for an article with dependencies and recommendations or update an existing one."""
    # Fetch article content
    title_content = fetch_gitea_content(article_id, "title.md")
    subtitle_content = fetch_gitea_content(article_id, "sub-title.md")
    article_content = fetch_gitea_content(article_id, "01.md")
    
    if not title_content or not article_content:
        logger.error(f"Failed to fetch all components for {article_id}")
        return None
    
    # Clean up content
    title = title_content.strip()
    subtitle = subtitle_content.strip() if subtitle_content else ""
    
    # Cache the title to help with resolving links
    page_cache[f"{article_id}_title"] = title
    
    # Parse dependencies and recommendations
    dependencies = []
    recommendations = []
    if article_id in config_data:
        dependencies = config_data[article_id].get("dependencies", [])
        recommendations = config_data[article_id].get("recommended", [])
    
    try:
        # Special handling for known large articles like Metaphor
        optimize_blocks = False
        if article_id == "figs-metaphor" or len(article_content) > 5000:
            optimize_blocks = True
            logger.info(f"Optimizing blocks for large article: {title} ({article_id}) with content length {len(article_content)}")
        
        # Convert markdown to Notion blocks
        content_blocks = convert_markdown_to_notion_blocks(article_content, optimize_blocks=optimize_blocks)
        
        # Count total required blocks including non-content blocks (title, callouts, etc.)
        total_blocks = len(content_blocks) + 1  # Title heading
        if subtitle:
            total_blocks += 1
        if dependencies:
            total_blocks += 1
        if recommendations:
            total_blocks += 1
        
        logger.info(f"Article {title} requires {total_blocks} blocks total")
        
        # If still over 100 blocks, try more aggressive optimization
        if total_blocks > 95:
            logger.info(f"Article {title} still over limit, performing more aggressive optimization")
            content_blocks = convert_markdown_to_notion_blocks(article_content, optimize_blocks=True, block_limit=90)
            
            # Recalculate total blocks
            total_blocks = len(content_blocks) + 1  # Title heading
            if subtitle:
                total_blocks += 1
            if dependencies:
                total_blocks += 1
            if recommendations:
                total_blocks += 1
            
            logger.info(f"After aggressive optimization, article {title} requires {total_blocks} blocks total")
            
            # If still too large, we'll need to truncate
            if total_blocks > 100:
                logger.warning(f"Article {title} still exceeds the 100 block limit after optimization. Content will be truncated.")
                # Keep most important blocks (beginning content + essential metadata)
                max_content_blocks = 100 - 1  # Title heading
                if subtitle:
                    max_content_blocks -= 1
                if dependencies:
                    max_content_blocks -= 1
                if recommendations:
                    max_content_blocks -= 1
                
                # Truncate content blocks
                content_blocks = content_blocks[:max_content_blocks]
                
                # Add a note about truncation
                content_blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "This article has been truncated to fit within Notion's block limits. Please see the original content for complete information."
                                }
                            }
                        ],
                        "icon": {
                            "type": "emoji",
                            "emoji": "⚠️"
                        },
                        "color": "yellow_background"
                    }
                })
        
        # Create children blocks for page
        children = [
            # Article title as heading - now using h1 instead of h2
            {
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
            }
        ]
        
        # Add subtitle as callout if available
        if subtitle:
            subtitle_block = {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "This article answers the question: "
                            }
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": subtitle
                            },
                            "annotations": {
                                "italic": True
                            }
                        }
                    ],
                    "icon": {
                        "type": "emoji",
                        "emoji": "❓"
                    }
                }
            }
            children.append(subtitle_block)
        
        # Add dependencies callout if available
        if dependencies:
            dep_text = []
            for dep in dependencies:
                # Get the title for the dependency article
                title_key = f"{dep}_title"
                article_title = page_cache.get(title_key, dep)
                
                # Add a link if we have the page ID in cache
                if dep in page_cache:
                    dep_text.append({
                        "type": "text",
                        "text": {
                            "content": "• ",
                        }
                    })
                    dep_text.append({
                        "type": "text",
                        "text": {
                            "content": article_title,
                            "link": {
                                "url": f"https://www.notion.so/{page_cache[dep].replace('-', '')}"
                            }
                        }
                    })
                    dep_text.append({
                        "type": "text",
                        "text": {
                            "content": "\n"
                        }
                    })
                else:
                    # No link available
                    dep_text.append({
                        "type": "text",
                        "text": {
                            "content": f"• {article_title}\n",
                        }
                    })
            
            dependencies_block = {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "In order to understand this topic, it would be good to read:\n"
                            }
                        },
                        *dep_text
                    ],
                    "icon": {
                        "type": "emoji",
                        "emoji": "📚"
                    },
                    "color": "gray_background"
                }
            }
            children.append(dependencies_block)
        
        # Add content blocks
        children.extend(content_blocks)
        
        # Add recommendations callout if available
        if recommendations:
            rec_text = []
            for rec in recommendations:
                # Get the title for the recommendation article
                title_key = f"{rec}_title"
                article_title = page_cache.get(title_key, rec)
                
                # Add a link if we have the page ID in cache
                if rec in page_cache:
                    rec_text.append({
                        "type": "text",
                        "text": {
                            "content": "• ",
                        }
                    })
                    rec_text.append({
                        "type": "text",
                        "text": {
                            "content": article_title,
                            "link": {
                                "url": f"https://www.notion.so/{page_cache[rec].replace('-', '')}"
                            }
                        }
                    })
                    rec_text.append({
                        "type": "text",
                        "text": {
                            "content": "\n"
                        }
                    })
                else:
                    # No link available
                    rec_text.append({
                        "type": "text",
                        "text": {
                            "content": f"• {article_title}\n",
                        }
                    })
            
            recommendations_block = {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "Next we recommend you learn about:\n"
                            }
                        },
                        *rec_text
                    ],
                    "icon": {
                        "type": "emoji",
                        "emoji": "👉"
                    },
                    "color": "blue_background"
                }
            }
            children.append(recommendations_block)
        
        # Check if the page already exists
        existing_page_id = None
        if update_existing:
            existing_page_id = find_page_by_title(parent_id, title)
        
        if existing_page_id and update_existing:
            # Update existing page
            if update_page_content(existing_page_id, children):
                logger.info(f"Updated article page: {title}")
                
                # Store the page ID in cache
                page_cache[title] = existing_page_id
                page_cache[article_id] = existing_page_id
                
                # Also store the mapping from article ID to title
                page_cache[f"{article_id}_title"] = title
                
                # Process links in page content after a short delay
                time.sleep(0.5)
                process_links_in_content(existing_page_id)
                
                return existing_page_id
            else:
                logger.error(f"Failed to update article page: {title}")
                return None
        else:
            # Create new page
            page_data = {
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    }
                },
                "children": children
            }
            
            try:
                logger.info(f"Creating page with {len(children)} blocks for article: {title}")
                response = notion.pages.create(**page_data)
                logger.info(f"Created article page: {title}")
                
                # Store the page ID in cache with both article ID and title
                page_id = response["id"]
                page_cache[title] = page_id
                page_cache[article_id] = page_id
                
                # Also store the mapping from article ID to title
                page_cache[f"{article_id}_title"] = title
                
                # Process links in page content after a short delay
                time.sleep(0.5)
                process_links_in_content(page_id)
                
                return page_id
            except APIResponseError as e:
                # If error is because of too many blocks, try more aggressive optimization
                if "body.children.length should be ≤ `100`" in str(e):
                    logger.warning(f"Too many blocks ({len(children)}) for article {title}, trying emergency truncation")
                    # Keep only essential content: title, first few blocks, and a note about truncation
                    emergency_children = [children[0]]  # Title
                    
                    # Add a few content blocks - prioritize keeping headings and important content
                    content_start = 1  # Start after title
                    if subtitle:
                        emergency_children.append(children[1])  # Subtitle callout
                        content_start += 1
                    if dependencies:
                        emergency_children.append(children[content_start])  # Dependencies callout
                        content_start += 1
                    
                    # Add first ~85 blocks of content
                    max_blocks = 95 - len(emergency_children)
                    emergency_children.extend(children[content_start:content_start+max_blocks])
                    
                    # Add truncation notice
                    emergency_children.append({
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "⚠️ This article has been severely truncated to fit within Notion's block limits. Please see the original content for complete information."
                                    }
                                }
                            ],
                            "icon": {
                                "type": "emoji",
                                "emoji": "⚠️"
                            },
                            "color": "yellow_background"
                        }
                    })
                    
                    # Try again with fewer blocks
                    page_data["children"] = emergency_children
                    logger.info(f"Retrying with {len(emergency_children)} blocks for article: {title}")
                    response = notion.pages.create(**page_data)
                    logger.info(f"Created truncated article page: {title}")
                    
                    # Store the page ID in cache
                    page_id = response["id"]
                    page_cache[title] = page_id
                    page_cache[article_id] = page_id
                    page_cache[f"{article_id}_title"] = title
                    
                    # Process links in page content after a short delay
                    time.sleep(0.5)
                    process_links_in_content(page_id)
                    
                    return page_id
                else:
                    # If error is for other reasons, re-raise
                    raise
    except Exception as e:
        logger.error(f"Error creating/updating article page {title}: {str(e)}")
        return None

def process_section(parent_id, section, level=1, config_data=None):
    """Process a section from the TOC, creating pages for it and its subsections."""
    title = section.get("title", "")
    link = section.get("link", None)
    subsections = section.get("sections", [])
    
    # Create page for this section
    section_id = parent_id
    if title:
        section_id = create_section_page(parent_id, title, level+1)
    
    # Create page for the article if there's a link
    if link and config_data:
        article_page_id = create_article_page(section_id, link, config_data, update_existing=False)
    
    # Process subsections
    for subsection in subsections:
        process_section(section_id, subsection, level+1, config_data)

def update_links_in_callouts(page_id, dependencies=None, recommendations=None):
    """Update the links in dependencies and recommendations callouts."""
    if not dependencies and not recommendations:
        return
    
    try:
        # Get existing blocks
        blocks = notion.blocks.children.list(block_id=page_id)
        
        for block in blocks["results"]:
            # Check for dependency callout block
            if dependencies and block["type"] == "callout" and "In order to understand this topic" in block["callout"]["rich_text"][0]["text"]["content"]:
                # Create updated links
                dep_text = []
                for dep in dependencies:
                    # Get the title for the dependency article
                    title_key = f"{dep}_title"
                    article_title = page_cache.get(title_key, dep)
                    
                    if dep in page_cache:
                        # Found the page ID, create a link
                        dep_text.append({
                            "type": "text",
                            "text": {
                                "content": "• ",
                            }
                        })
                        dep_text.append({
                            "type": "text",
                            "text": {
                                "content": article_title,
                                "link": {
                                    "url": f"https://www.notion.so/{page_cache[dep].replace('-', '')}"
                                }
                            }
                        })
                        dep_text.append({
                            "type": "text",
                            "text": {
                                "content": "\n"
                            }
                        })
                    else:
                        # No link available
                        dep_text.append({
                            "type": "text",
                            "text": {
                                "content": f"• {article_title}\n",
                            }
                        })
                
                # Update callout with links
                updated_callout = {
                    "callout": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "In order to understand this topic, it would be good to read:\n"
                                }
                            },
                            *dep_text
                        ],
                        "icon": {
                            "type": "emoji",
                            "emoji": "📚"
                        },
                        "color": "gray_background"
                    }
                }
                
                notion.blocks.update(block_id=block["id"], **updated_callout)
                logger.info(f"Updated dependency links in page {page_id}")
            
            # Check for recommendation callout block
            if recommendations and block["type"] == "callout" and "Next we recommend you learn about" in block["callout"]["rich_text"][0]["text"]["content"]:
                # Create updated links
                rec_text = []
                for rec in recommendations:
                    # Get the title for the recommendation article
                    title_key = f"{rec}_title"
                    article_title = page_cache.get(title_key, rec)
                    
                    if rec in page_cache:
                        # Found the page ID, create a link
                        rec_text.append({
                            "type": "text",
                            "text": {
                                "content": "• ",
                            }
                        })
                        rec_text.append({
                            "type": "text",
                            "text": {
                                "content": article_title,
                                "link": {
                                    "url": f"https://www.notion.so/{page_cache[rec].replace('-', '')}"
                                }
                            }
                        })
                        rec_text.append({
                            "type": "text",
                            "text": {
                                "content": "\n"
                            }
                        })
                    else:
                        # No link available
                        rec_text.append({
                            "type": "text",
                            "text": {
                                "content": f"• {article_title}\n",
                            }
                        })
                
                # Update callout with links
                updated_callout = {
                    "callout": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Next we recommend you learn about:\n"
                                }
                            },
                            *rec_text
                        ],
                        "icon": {
                            "type": "emoji",
                            "emoji": "👉"
                        },
                        "color": "blue_background"
                    }
                }
                
                notion.blocks.update(block_id=block["id"], **updated_callout)
                logger.info(f"Updated recommendation links in page {page_id}")
    
    except Exception as e:
        logger.error(f"Error updating links in page {page_id}: {str(e)}")

def find_page_by_title(parent_id, title):
    """
    Find a page by title under a specific parent ID.
    
    Args:
        parent_id (str): The parent page ID to search under
        title (str): The title to search for
        
    Returns:
        str: The page ID if found, None otherwise
    """
    has_more = True
    start_cursor = None
    
    title_lower = title.lower().strip()
    
    while has_more:
        # Query for child pages under the parent
        try:
            if start_cursor:
                response = notion.blocks.children.list(
                    block_id=parent_id,
                    page_size=100,
                    start_cursor=start_cursor
                )
            else:
                response = notion.blocks.children.list(
                    block_id=parent_id,
                    page_size=100
                )
            
            # Check each block's title
            for block in response.get("results", []):
                if block.get("type") == "child_page":
                    page_title = block.get("child_page", {}).get("title", "").lower().strip()
                    if page_title == title_lower:
                        return block.get("id")
            
            # Check if there are more results
            has_more = response.get("has_more", False)
            if has_more:
                start_cursor = response.get("next_cursor")
            
        except Exception as e:
            logger.error(f"Error finding page by title: {e}")
            return None
    
    return None

def find_section_in_toc(toc_data, section_title):
    """
    Find a section in the TOC by title at any level.
    
    Args:
        toc_data (dict): The TOC data
        section_title (str): The section title to find
        
    Returns:
        tuple: (section dict, section path string, parent sections list)
    """
    def search_sections(sections, path="", parent_sections=None):
        if parent_sections is None:
            parent_sections = []
        
        for section in sections:
            title = section.get("title", "")
            new_path = f"{path}/{title}" if path else title
            new_parent_sections = parent_sections.copy()
            
            if title == section_title:
                return section, new_path, new_parent_sections
            
            # Search in subsections
            subsections = section.get("sections", [])
            if subsections:
                new_parent_sections.append(section)
                result = search_sections(subsections, new_path, new_parent_sections)
                if result[0]:  # Found
                    return result
        
        return None, "", []
    
    return search_sections(toc_data.get("sections", []))

def update_page_content(page_id, children):
    """Update the content of an existing page."""
    try:
        # First, get existing content
        existing_blocks = notion.blocks.children.list(block_id=page_id)
        
        # Delete all existing blocks
        for block in existing_blocks.get("results", []):
            try:
                notion.blocks.delete(block_id=block["id"])
            except Exception as e:
                logger.error(f"Error deleting block {block['id']}: {str(e)}")
        
        # Add new content
        notion.blocks.children.append(block_id=page_id, children=children)
        logger.info(f"Updated content for page {page_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating page content for {page_id}: {str(e)}")
        return False

def create_toggle_block(title, children=None):
    """Create a toggle block with optional children."""
    if children is None:
        children = []
    
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
            "color": "default",
            "children": children
        }
    }
    return toggle_block

def build_toc_structure(parent_id, toc_data, update_existing=False):
    """Recursively build TOC structure with toggle blocks for sections and links for articles."""
    if not toc_data or "sections" not in toc_data:
        return
    
    # Process each section in the TOC
    for section in toc_data.get("sections", []):
        title = section.get("title", "")
        link = section.get("link", None)
        subsections = section.get("sections", [])
        
        logger.info(f"Processing TOC item: {title}")
        
        # If it has both a link and subsections, it's an article with subsections
        if link and subsections:
            # First create the article
            article_page_id = create_article_page(parent_id, link, {}, update_existing)
            if article_page_id:
                logger.info(f"Created/updated article page with subsections: {title}")
                # Then create subsections under it
                build_toc_structure(article_page_id, section, update_existing)
        # If it has only a link, it's just an article
        elif link:
            article_page_id = create_article_page(parent_id, link, {}, update_existing)
            if article_page_id:
                logger.info(f"Created/updated article page: {title}")
        # If it has only subsections, it's a section header with toggle
        elif subsections:
            # Check if this section page already exists
            section_page_id = find_page_by_title(parent_id, title)
            
            if section_page_id and update_existing:
                # Update existing section page with toggle
                logger.info(f"Updating existing section page with toggle: {title}")
                
                # Create toggle block for the section with empty children
                toggle_block = create_toggle_block(title)
                
                # Update the page with the toggle block
                children = [
                    {
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
                    },
                    toggle_block
                ]
                
                if update_page_content(section_page_id, children):
                    logger.info(f"Updated section toggle page: {title}")
                    # Process subsections recursively
                    build_toc_structure(section_page_id, section, update_existing)
                else:
                    logger.error(f"Failed to update section toggle page: {title}")
            else:
                # Create new section page with toggle
                logger.info(f"Creating new section page with toggle: {title}")
                
                # Create toggle block for the section with empty children
                toggle_block = create_toggle_block(title)
                
                # Create the section page
                page_data = {
                    "parent": {"page_id": parent_id},
                    "properties": {
                        "title": {
                            "title": [
                                {
                                    "text": {
                                        "content": title
                                    }
                                }
                            ]
                        }
                    },
                    "children": [
                        {
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
                        },
                        toggle_block
                    ]
                }
                
                try:
                    response = notion.pages.create(**page_data)
                    section_page_id = response["id"]
                    logger.info(f"Created section toggle page: {title}")
                    
                    # Store in cache
                    page_cache[title] = section_page_id
                    
                    # Process subsections recursively
                    build_toc_structure(section_page_id, section, update_existing)
                except Exception as e:
                    logger.error(f"Error creating section toggle page {title}: {str(e)}")
        # If it has neither, it's just a placeholder (shouldn't happen in well-formed TOC)
        else:
            logger.warning(f"Section {title} has no link or subsections, skipping")

def main():
    """Main function to process the TOC and create pages."""
    parser = argparse.ArgumentParser(description="Import Translation Academy content to Notion with TOC structure")
    parser.add_argument("--section", help="Process a specific section at any level in the TOC")
    parser.add_argument("--article", help="Process only a specific article ID")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls in seconds")
    parser.add_argument("--local", action="store_true", help="Use local YAML files instead of fetching from repo")
    parser.add_argument("--update", action="store_true", help="Update existing pages instead of creating new ones")
    parser.add_argument("--skip-existing", action="store_true", help="Skip creating articles that already exist")
    parser.add_argument("--build-toc", action="store_true", help="Build complete TOC structure with toggle blocks")
    parser.add_argument("--process-links", action="store_true", help="Process links in existing pages")
    args = parser.parse_args()
    
    logger.info(f"Using Notion page ID: {NOTION_PARENT_ID}")
    
    # Load TOC and config data
    use_local = args.local
    update_existing = args.update
    skip_existing = args.skip_existing
    toc_data = load_toc_data(use_remote=not use_local)
    config_data = load_config_data(use_remote=not use_local)
    
    if not toc_data or not config_data:
        logger.error("Failed to load required data files")
        return
    
    # Debug - List all sections in the TOC
    logger.info("Available top-level sections in TOC:")
    for section in toc_data.get("sections", []):
        logger.info(f"  - {section.get('title', 'Untitled')}")
    
    # If just processing links in existing pages
    if args.process_links:
        # First build a cache of all article IDs and their page IDs
        logger.info("Building cache of article IDs and page IDs...")
        
        # If processing a specific section, only handle articles in that section
        if args.section:
            # Find the section at any level in the TOC
            target_section, section_path, parent_sections = find_section_in_toc(toc_data, args.section)
            
            if target_section:
                logger.info(f"Found section: {args.section} at path: {section_path}")
                
                # Find the section page ID in Notion
                translate_page_id = create_top_level_page("Translate", update_existing=False)
                current_parent_id = translate_page_id
                
                # First try to find all parent sections and their page IDs
                path_parts = section_path.split("/")
                if len(path_parts) > 1:  # Only if we have parent sections
                    parent_section_names = path_parts[:-1]  # Exclude the target section itself
                    
                    # Find each parent section in order
                    for parent_name in parent_section_names:
                        if parent_name:  # Skip empty names
                            parent_id = find_page_by_title(current_parent_id, parent_name)
                            if parent_id:
                                current_parent_id = parent_id
                                logger.info(f"Found parent section: {parent_name} with ID {parent_id}")
                
                # Find the target section page ID
                section_id = find_page_by_title(current_parent_id, args.section)
                
                if section_id:
                    logger.info(f"Found section page: {args.section} with ID {section_id}")
                    
                    # Find all article pages under this section
                    # First get all the article IDs in this section
                    article_ids = []
                    for article in target_section.get("sections", []):
                        article_id = article.get("link")
                        if article_id:
                            article_ids.append(article_id)
                    
                    logger.info(f"Found {len(article_ids)} articles in section {args.section}")
                    
                    # Find all article pages under this section
                    for article_id in article_ids:
                        title_content = fetch_gitea_content(article_id, "title.md")
                        if title_content:
                            title = title_content.strip()
                            page_id = find_page_by_title(section_id, title)
                            if page_id:
                                page_cache[title] = page_id
                                page_cache[article_id] = page_id
                                page_cache[f"{article_id}_title"] = title
                                logger.info(f"Cached page ID for {title}: {page_id}")
                                
                                # Process links
                                logger.info(f"Processing links in {title}")
                                process_links_in_content(page_id)
                                time.sleep(args.delay)
                    
                    logger.info(f"Completed processing links in all articles in section {args.section}")
                else:
                    logger.error(f"Could not find section page for {args.section}")
            else:
                logger.error(f"Section '{args.section}' not found in the TOC")
        
        # If processing a specific article, only handle that article
        elif args.article:
            article_id = args.article
            title_content = fetch_gitea_content(article_id, "title.md")
            if title_content:
                title = title_content.strip()
                page_id = find_page_by_title(NOTION_PARENT_ID, title)
                if page_id:
                    page_cache[title] = page_id
                    page_cache[article_id] = page_id
                    page_cache[f"{article_id}_title"] = title
                    logger.info(f"Cached page ID for {title}: {page_id}")
                    
                    # Process links
                    logger.info(f"Processing links in {title}")
                    process_links_in_content(page_id)
                    
                    logger.info(f"Completed processing links in article {title}")
                else:
                    logger.error(f"Could not find page for article {article_id}")
        
        # Otherwise process all articles
        else:
            # Cache all article IDs from the config
            for article_id in config_data.keys():
                title_content = fetch_gitea_content(article_id, "title.md")
                if title_content:
                    title = title_content.strip()
                    page_id = find_page_by_title(NOTION_PARENT_ID, title)
                    if page_id:
                        page_cache[title] = page_id
                        page_cache[article_id] = page_id
                        page_cache[f"{article_id}_title"] = title
                        logger.info(f"Cached page ID for {title}: {page_id}")
                        
                        # Process links
                        logger.info(f"Processing links in {title}")
                        process_links_in_content(page_id)
                        time.sleep(args.delay)
            
            logger.info("Completed processing links in all pages")
        
        return
    
    # If processing a specific article only
    if args.article:
        article_id = args.article
        # Check if the article already exists and should be skipped
        title_content = fetch_gitea_content(article_id, "title.md")
        if title_content:
            title = title_content.strip()
            existing_page_id = find_page_by_title(NOTION_PARENT_ID, title)
            if existing_page_id and skip_existing:
                logger.info(f"Skipping existing article: {title}")
                return
        
        article_page = create_article_page(NOTION_PARENT_ID, article_id, config_data, update_existing)
        if article_page:
            logger.info(f"Created/updated page for article: {article_id}")
            
            # Get dependencies and recommendations
            dependencies = config_data[article_id].get("dependencies", [])
            recommendations = config_data[article_id].get("recommended", [])
            
            # Update links
            if dependencies or recommendations:
                time.sleep(args.delay)
                update_links_in_callouts(article_page, dependencies, recommendations)
        else:
            logger.error(f"Failed to create/update page for article: {article_id}")
        return
    
    # Create the top-level pages
    translate_page_id = create_top_level_page("Translate", update_existing)
    
    # If top-level page creation failed, exit
    if not translate_page_id:
        logger.error("Failed to create/update top-level page. Exiting.")
        return
    
    # If building complete TOC structure
    if args.build_toc:
        logger.info("Building complete TOC structure with toggle blocks")
        build_toc_structure(translate_page_id, toc_data, update_existing)
        logger.info("Completed building TOC structure")
        return
    
    # Rest of the function as before...
    # Process specific section if requested
    if args.section:
        # Find the section at any level in the TOC
        target_section, section_path, parent_sections = find_section_in_toc(toc_data, args.section)
        
        if target_section:
            logger.info(f"Found section: {args.section} at path: {section_path}")
            
            # Create parent section pages if needed
            current_parent_id = translate_page_id
            
            # Extract all parent section names from the path
            path_parts = section_path.split("/")
            if len(path_parts) > 1:  # Only if we have parent sections
                parent_section_names = path_parts[:-1]  # Exclude the target section itself
                logger.info(f"Parent section names: {parent_section_names}")
                
                # Create each parent section in order
                for i, parent_name in enumerate(parent_section_names):
                    if parent_name:  # Skip empty names
                        logger.info(f"Finding/creating parent section: {parent_name} under {current_parent_id}")
                        
                        # Try to find the parent section first
                        parent_id = find_page_by_title(current_parent_id, parent_name)
                        
                        if parent_id:
                            logger.info(f"Found existing parent section: {parent_name} ({parent_id})")
                            current_parent_id = parent_id
                        else:
                            # Create the parent section
                            parent_level = i + 1
                            logger.info(f"Creating parent section: {parent_name} at level {parent_level}")
                            parent_id = create_section_page(current_parent_id, parent_name, parent_level, update_existing)
                            
                            if not parent_id:
                                logger.error(f"Failed to create parent section: {parent_name}. Exiting.")
                                return
                            
                            current_parent_id = parent_id
            
            # Create the target section page (use the last level + 1)
            section_level = len(path_parts)
            logger.info(f"Creating target section: {args.section} at level {section_level} under parent {current_parent_id}")
            
            # Try to find the target section first
            section_id = find_page_by_title(current_parent_id, args.section)
            
            if section_id:
                logger.info(f"Found existing target section: {args.section} ({section_id})")
            else:
                # Create the target section
                section_id = create_section_page(current_parent_id, args.section, section_level, update_existing)
                
                if not section_id:
                    logger.error(f"Failed to create target section: {args.section}. Exiting.")
                    return
            
            # Process all articles in this section
            logger.info(f"Articles in section {args.section}:")
            for article in target_section.get("sections", []):
                article_link = article.get("link", "")
                article_title = article.get("title", "")
                logger.info(f"  - {article_title} ({article_link})")
            
            for article in target_section.get("sections", []):
                article_id = article.get("link")
                if article_id:
                    # Check if article already exists and should be skipped
                    title_content = fetch_gitea_content(article_id, "title.md")
                    if title_content:
                        title = title_content.strip()
                        existing_page_id = find_page_by_title(section_id, title)
                        if existing_page_id and skip_existing:
                            logger.info(f"Skipping existing article: {title}")
                            continue
                    
                    time.sleep(args.delay)
                    article_page = create_article_page(section_id, article_id, config_data, update_existing)
                    
                    if article_page:
                        # Get dependencies and recommendations
                        dependencies = config_data.get(article_id, {}).get("dependencies", [])
                        recommendations = config_data.get(article_id, {}).get("recommended", [])
                        
                        # Create dependencies first
                        for dep in dependencies:
                            if dep not in page_cache:
                                # Check if dependency already exists and should be skipped
                                dep_title_content = fetch_gitea_content(dep, "title.md")
                                if dep_title_content:
                                    dep_title = dep_title_content.strip()
                                    dep_existing_page_id = find_page_by_title(translate_page_id, dep_title)
                                    if dep_existing_page_id and skip_existing:
                                        logger.info(f"Skipping existing dependency: {dep_title}")
                                        page_cache[dep] = dep_existing_page_id
                                        page_cache[dep_title] = dep_existing_page_id
                                        page_cache[f"{dep}_title"] = dep_title
                                        continue
                                
                                time.sleep(args.delay)
                                dep_page = create_article_page(translate_page_id, dep, config_data, update_existing)
                                logger.info(f"Created/updated page for dependency: {dep}")
                        
                        # Create recommendations
                        for rec in recommendations:
                            if rec not in page_cache:
                                # Check if recommendation already exists and should be skipped
                                rec_title_content = fetch_gitea_content(rec, "title.md")
                                if rec_title_content:
                                    rec_title = rec_title_content.strip()
                                    rec_existing_page_id = find_page_by_title(translate_page_id, rec_title)
                                    if rec_existing_page_id and skip_existing:
                                        logger.info(f"Skipping existing recommendation: {rec_title}")
                                        page_cache[rec] = rec_existing_page_id
                                        page_cache[rec_title] = rec_existing_page_id
                                        page_cache[f"{rec}_title"] = rec_title
                                        continue
                                
                                time.sleep(args.delay)
                                rec_page = create_article_page(translate_page_id, rec, config_data, update_existing)
                                logger.info(f"Created/updated page for recommendation: {rec}")
                        
                        # Update links
                        time.sleep(args.delay)
                        update_links_in_callouts(article_page, dependencies, recommendations)
                        
                        logger.info(f"Processed article: {article_id}")
            
            logger.info(f"Completed processing section: {args.section}")
        else:
            logger.error(f"Section '{args.section}' not found in the TOC")
    else:
        # Test with just figs-activepassive article and its dependencies/recommendations
        article_id = "figs-activepassive"
        dependencies = config_data[article_id].get("dependencies", [])
        recommendations = config_data[article_id].get("recommended", [])
        
        # First create dependencies
        for dep in dependencies:
            # Check if dependency already exists and should be skipped
            if skip_existing:
                dep_title_content = fetch_gitea_content(dep, "title.md")
                if dep_title_content:
                    dep_title = dep_title_content.strip()
                    dep_existing_page_id = find_page_by_title(translate_page_id, dep_title)
                    if dep_existing_page_id:
                        logger.info(f"Skipping existing dependency: {dep_title}")
                        page_cache[dep] = dep_existing_page_id
                        page_cache[dep_title] = dep_existing_page_id
                        page_cache[f"{dep}_title"] = dep_title
                        continue
            
            time.sleep(args.delay)
            dep_page = create_article_page(translate_page_id, dep, config_data, update_existing)
            if dep_page:
                logger.info(f"Created/updated page for dependency: {dep}")
            else:
                logger.error(f"Failed to create/update page for dependency: {dep}")
        
        # Then create recommendations
        for rec in recommendations:
            # Check if recommendation already exists and should be skipped
            if skip_existing:
                rec_title_content = fetch_gitea_content(rec, "title.md")
                if rec_title_content:
                    rec_title = rec_title_content.strip()
                    rec_existing_page_id = find_page_by_title(translate_page_id, rec_title)
                    if rec_existing_page_id:
                        logger.info(f"Skipping existing recommendation: {rec_title}")
                        page_cache[rec] = rec_existing_page_id
                        page_cache[rec_title] = rec_existing_page_id
                        page_cache[f"{rec}_title"] = rec_title
                        continue
            
            time.sleep(args.delay)
            rec_page = create_article_page(translate_page_id, rec, config_data, update_existing)
            if rec_page:
                logger.info(f"Created/updated page for recommendation: {rec}")
            else:
                logger.error(f"Failed to create/update page for recommendation: {rec}")
        
        # Check if article already exists and should be skipped
        if skip_existing:
            title_content = fetch_gitea_content(article_id, "title.md")
            if title_content:
                title = title_content.strip()
                existing_page_id = find_page_by_title(translate_page_id, title)
                if existing_page_id:
                    logger.info(f"Skipping existing article: {title}")
                    # Still update links for dependencies and recommendations
                    time.sleep(args.delay)
                    update_links_in_callouts(existing_page_id, dependencies, recommendations)
                    logger.info("Completed test import of figs-activepassive and related articles")
                    return
        
        # Finally create the main article
        article_page = create_article_page(translate_page_id, article_id, config_data, update_existing)
        if article_page:
            logger.info(f"Created/updated page for article: {article_id}")
            
            # Update links now that all pages are created
            time.sleep(args.delay)
            update_links_in_callouts(article_page, dependencies, recommendations)
        else:
            logger.error(f"Failed to create/update page for article: {article_id}")
        
        logger.info("Completed test import of figs-activepassive and related articles")

def process_links_in_content(page_id, cache_map=None):
    """Update any links in the content of a page once all pages are created."""
    if not cache_map:
        cache_map = page_cache
        
    try:
        # Get existing blocks
        response = notion.blocks.children.list(block_id=page_id)
        blocks = response.get("results", [])
        
        for block in blocks:
            # Skip non-text blocks
            if block["type"] not in ["paragraph", "heading_1", "heading_2", "heading_3", 
                                     "bulleted_list_item", "numbered_list_item", "callout"]:
                continue
                
            # Get rich text array from the block
            rich_text_array = block[block["type"]].get("rich_text", [])
            
            # Check if any text chunks have non-Notion links that could be internal articles
            update_needed = False
            for text_item in rich_text_array:
                if text_item["type"] == "text" and text_item.get("text", {}).get("link"):
                    link_url = text_item["text"]["link"]["url"]
                    
                    # Check if this is a relative link to an article
                    if "../" in link_url and "/01.md" in link_url:
                        parts = link_url.split("/")
                        article_id = next((part for part in parts if part and part != ".." and part != "01.md"), None)
                        
                        # If we found an article ID and have it in cache, update the link
                        if article_id and article_id in cache_map:
                            notion_url = f"https://www.notion.so/{cache_map[article_id].replace('-', '')}"
                            text_item["text"]["link"]["url"] = notion_url
                            update_needed = True
                            logger.info(f"Updated internal link to {article_id} in page {page_id}")
            
            # If we updated any links, update the block
            if update_needed:
                try:
                    notion.blocks.update(
                        block_id=block["id"],
                        **{block["type"]: {"rich_text": rich_text_array}}
                    )
                    logger.info(f"Updated links in block {block['id']}")
                except Exception as e:
                    logger.error(f"Error updating links in block {block['id']}: {str(e)}")
        
        # Check if there are more blocks
        if response.get("has_more"):
            # Process next batch of blocks
            next_cursor = response.get("next_cursor")
            process_next_batch(page_id, next_cursor, cache_map)
            
    except Exception as e:
        logger.error(f"Error processing links in page {page_id}: {str(e)}")

def process_next_batch(page_id, cursor, cache_map=None):
    """Process the next batch of blocks in a page."""
    if not cache_map:
        cache_map = page_cache
        
    try:
        # Get next batch of blocks
        response = notion.blocks.children.list(block_id=page_id, start_cursor=cursor)
        blocks = response.get("results", [])
        
        for block in blocks:
            # Skip non-text blocks
            if block["type"] not in ["paragraph", "heading_1", "heading_2", "heading_3", 
                                     "bulleted_list_item", "numbered_list_item", "callout"]:
                continue
                
            # Get rich text array from the block
            rich_text_array = block[block["type"]].get("rich_text", [])
            
            # Check if any text chunks have non-Notion links that could be internal articles
            update_needed = False
            for text_item in rich_text_array:
                if text_item["type"] == "text" and text_item.get("text", {}).get("link"):
                    link_url = text_item["text"]["link"]["url"]
                    
                    # Check if this is a relative link to an article
                    if "../" in link_url and "/01.md" in link_url:
                        parts = link_url.split("/")
                        article_id = next((part for part in parts if part and part != ".." and part != "01.md"), None)
                        
                        # If we found an article ID and have it in cache, update the link
                        if article_id and article_id in cache_map:
                            notion_url = f"https://www.notion.so/{cache_map[article_id].replace('-', '')}"
                            text_item["text"]["link"]["url"] = notion_url
                            update_needed = True
                            logger.info(f"Updated internal link to {article_id} in page {page_id}")
            
            # If we updated any links, update the block
            if update_needed:
                try:
                    notion.blocks.update(
                        block_id=block["id"],
                        **{block["type"]: {"rich_text": rich_text_array}}
                    )
                    logger.info(f"Updated links in block {block['id']}")
                except Exception as e:
                    logger.error(f"Error updating links in block {block['id']}: {str(e)}")
        
        # Check if there are more blocks
        if response.get("has_more"):
            # Process next batch of blocks
            next_cursor = response.get("next_cursor")
            process_next_batch(page_id, next_cursor, cache_map)
            
    except Exception as e:
        logger.error(f"Error processing links in next batch for page {page_id}: {str(e)}")

if __name__ == "__main__":
    main() 