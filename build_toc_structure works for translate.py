import os
import yaml
import time
import logging
import requests
import base64
import json
import re # Added for regex operations
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

# Parent Notion page ID (Main page where the TOC toggle lives)
VISUAL_TOC_PARENT_PAGE_ID = "1c372d5af2de80e08b11cd7748a1467d" 

# Gitea API settings
GITEA_API_BASE = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_API_KEY = os.environ.get("GITEA_API_KEY")

# --- Cache ---
# Global cache for created/found pages (maps title/article_id to page_id)
# Also caches fetched Gitea content to reduce API calls
page_cache = {}
# A separate mapping from Gitea URLs to Notion page IDs for post-processing
url_to_page_id_map = {}

# --- Gitea Fetching ---

def fetch_gitea_content(path):
    """Fetch content from Gitea API, using cache."""
    # Check cache first
    if path in page_cache:
         # logging.debug(f"Cache hit for Gitea content: {path}")
         return page_cache[path]
         
    url = f"{GITEA_API_BASE}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/contents/{path}"
    headers = {}
    if GITEA_API_KEY:
        headers["Authorization"] = f"token {GITEA_API_KEY}"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        # Ensure content is present and not empty
        if "content" in data and data["content"]:
             content = base64.b64decode(data["content"]).decode("utf-8")
             # Cache the fetched content
             page_cache[path] = content 
             #logging.info(f"Fetched Gitea content: {path}")
             return content
        else:
            logging.warning(f"No content found or empty content for Gitea path: {path}")
            page_cache[path] = None # Cache the miss (empty or no content)
            return None
    except Exception as e:
        logging.error(f"Failed to fetch content from Gitea ({path}): {str(e)}")
        # Cache the failure to avoid retrying
        page_cache[path] = None 
        return None

def load_toc_data(file_path="toc.yaml", use_remote=True):
    """Load Table of Contents data from file or Gitea."""
    toc_path = "translate/toc.yaml"
    if use_remote:
        logging.info("Fetching TOC data from Gitea...")
        content = fetch_gitea_content(toc_path)
        if content:
            try:
                return yaml.safe_load(content)
            except Exception as e:
                logging.error(f"Error parsing remote TOC data: {str(e)}")
                # Fall back to local file
    
    # Load from local file if remote failed or not requested
    try:
        logging.info(f"Loading TOC data from local file: {file_path}")
        with open(file_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file.read())
    except Exception as e:
        logging.error(f"Error loading TOC data from {file_path}: {str(e)}")
        return {}

def fetch_article_content(article_id):
    """Fetch main article content (01.md) from Gitea."""
    path = f"translate/{article_id}/01.md"
    return fetch_gitea_content(path)
    
# --- Notion Helpers ---

def find_page_by_title(notion, title, parent_id=None):
    """
    Find a Notion page by title. 
    If parent_id is provided, tries to find it within that parent (less reliable).
    Otherwise searches globally.
    """
    # Check cache first
    if title in page_cache:
        # logging.debug(f"Cache hit for page title '{title}': {page_cache[title]}")
        return page_cache[title]
        
    logging.debug(f"Searching for page with title: '{title}'")
    try:
        # Global search is more reliable for finding pages by title
        response = notion.search(
            query=title,
            filter={
                "property": "object",
                "value": "page"
            }
        )
        
        results = response.get("results", [])
        if results:
            for page in results:
                page_title_prop = page.get("properties", {}).get("title", {}).get("title", [])
                if page_title_prop:
                    title_text = page_title_prop[0].get("text", {}).get("content", "")
                    # Case-insensitive comparison for robustness
                    if title_text.lower() == title.lower():
                        page_id = page.get("id")
                        # Update cache
                        page_cache[title] = page_id
                        logging.debug(f"Found page '{title}' via global search: {page_id}")
                        return page_id
        
        # No matching page found via global search
        logging.debug(f"Page '{title}' not found via global search.")
        page_cache[title] = None # Cache the miss
        return None
    except Exception as e:
        logging.error(f"Error searching for page {title}: {str(e)}")
        return None

def create_toggle(notion, parent_id, title, level=1, is_heading=False):
    """Create a toggle block with specified title and heading level."""
    logging.debug(f"Creating toggle: '{title}' under parent: {parent_id}")
    try:
        if level == 1 or is_heading:
            toggle_block_data = {
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": title}}],
                    "is_toggleable": True,
                    "color": "default"
                }
            }
            block_type = "heading_1"
        else:
             toggle_block_data = {
                "toggle": {
                    "rich_text": [{"type": "text", "text": {"content": title}}],
                    "color": "default"
                }
            }
             block_type = "toggle"

        response = notion.blocks.children.append(
            block_id=parent_id,
            children=[{"type": block_type, **toggle_block_data}]
        )
        
        toggle_id = response.get("results", [{}])[0].get("id")
        if toggle_id:
             logging.info(f"Created level {level} toggle: '{title}' ({toggle_id})")
        else:
             logging.warning(f"Toggle creation for '{title}' seemed successful but no ID found in response.")
        return toggle_id
    except Exception as e:
        logging.error(f"Error creating toggle '{title}': {str(e)}")
        return None

def add_image_to_page(notion, page_id, image_url, caption=""):
    """Add an image to a specific Notion page."""
    logging.debug(f"Adding image '{image_url}' to page {page_id}")
    try:
        notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": image_url},
                    "caption": [{"type": "text", "text": {"content": caption}}] if caption else []
                }
            }]
        )
        # logging.info(f"Added image to page {page_id}: {image_url}")
        return True
    except Exception as e:
        logging.error(f"Error adding image to page {page_id}: {str(e)}")
        return False

def add_web_link_to_page(notion, page_id, link_text, link_url):
    """Add a web link as a paragraph block to a Notion page."""
    logging.debug(f"Adding web link '{link_text}' -> '{link_url}' to page {page_id}")
    try:
        notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "🔗 "}},
                        {
                            "type": "text",
                            "text": {"content": link_text, "link": {"url": link_url}},
                            "annotations": {"color": "blue"}
                        }
                    ]
                }
            }]
        )
        # logging.info(f"Added web link to page {page_id}: {link_text} → {link_url}")
        return True
    except Exception as e:
        logging.error(f"Error adding web link '{link_text}' to page {page_id}: {str(e)}")
        return False
        
def add_page_link_to_toggle(notion, parent_id, title, page_id, is_child=False, indent_level=0):
    """Add a link to a page in the visual TOC structure."""
    logging.debug(f"Adding page link '{title}' ({page_id}) to visual TOC under {parent_id}")
    try:
        # Determine prefix based on indentation level for visual hierarchy
        prefix = "📄 " # Default for items directly under a toggle (level 0 indent within toggle)
        if is_child:
            prefix = "    " * indent_level # Use 4 spaces per indent level
            if indent_level == 1: prefix += "→ "
            elif indent_level == 2: prefix += "○ "
            elif indent_level >= 3: prefix += "• "
            else: prefix = "→ " # Fallback if indent_level is 0 but is_child is true
            
        notion.blocks.children.append(
            block_id=parent_id,
            children=[{
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": prefix}},
                        {
                            "type": "text",
                            "text": {
                                "content": title,
                                "link": {"url": f"https://www.notion.so/{page_id.replace('-', '')}"}
                            },
                            "annotations": {"bold": True, "color": "blue"}
                        }
                    ]
                }
            }]
        )
        # logging.info(f"Added page link to visual TOC: {title}")
        return True
    except Exception as e:
        logging.error(f"Error creating page link for {title} in visual TOC: {str(e)}")
        return False

# --- Markdown Extraction Helpers (Keep for now, might be used later) ---

def extract_images_from_markdown(markdown_text):
    """Extract image URLs and captions from markdown text."""
    # Pattern: ![caption](url)
    image_pattern = r'!\[(.*?)\]\((.*?)\)'
    images = []
    for match in re.finditer(image_pattern, markdown_text):
        caption = match.group(1)
        url = match.group(2)
        # Basic validation: Check if URL looks like an image URL (common extensions)
        if url and re.search(r'\.(jpeg|jpg|gif|png|svg|webp)$', url.lower()):
            images.append({"url": url, "caption": caption})
            logging.debug(f"Extracted image: URL='{url}', Caption='{caption}'")
        else:
             logging.warning(f"Skipping potential image with non-standard URL: {url}")
    return images

def extract_web_links_from_markdown(markdown_text):
    """Extract external web links (http/https) from markdown text."""
    # Pattern: [text](url) - only match http/https URLs and Gitea URLs
    link_pattern = r'\[(.*?)\]\((https?://.*?|.*?git\.door43\.org/.*?)\)'
    links = []
    for match in re.finditer(link_pattern, markdown_text):
        text = match.group(1)
        url = match.group(2)
        # Ensure Gitea links are properly formed
        if "git.door43.org" in url and not url.startswith("http"):
            url = "https://" + url
        # Exclude placeholder or obviously invalid URLs if necessary
        if url and text:
            links.append({"text": text, "url": url})
            logging.debug(f"Extracted web link: Text='{text}', URL='{url}'")
    return links

# --- Advanced Formatting & Parsing (Adapted from ta_to_notion individual files working.py) ---

def parse_rich_text(text):
    """Parse markdown text to create Notion's rich text objects with formatting."""
    rich_text = []
    
    # First, handle basic formatting (bold and italic)
    # Process bold formatting (**text**)
    bold_pattern = r'\*\*([^*]+)\*\*'
    # Process italic formatting (*text*)
    italic_pattern = r'\*([^*]+)\*'
    # Process footnote references ([^n])
    footnote_ref_pattern = r'\[\^(\d+)\]'
    
    # Improved pattern to handle regular links, internal links, and Gitea links
    # This pattern matches:
    # [link text](url) - regular link
    # [link text](../folder/01.md) - internal link to article
    # [link text](../folder/) - internal link to folder
    # [link text](https://git.door43.org/...) - Gitea link
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    # Handle formatting first
    formatted_text = text
    
    # Temporary placeholders to preserve formatting
    placeholders = {}
    placeholder_count = 0
    
    # Handle bold text
    bold_matches = list(re.finditer(bold_pattern, formatted_text))
    for match in bold_matches:
        placeholder = f"__BOLD_PLACEHOLDER_{placeholder_count}__"
        placeholders[placeholder] = {
            "type": "bold",
            "content": match.group(1)
        }
        formatted_text = formatted_text.replace(match.group(0), placeholder, 1)
        placeholder_count += 1
    
    # Handle italic text
    italic_matches = list(re.finditer(italic_pattern, formatted_text))
    for match in italic_matches:
        # Skip if this looks like it might be part of a bold pattern or inside a placeholder
        if "__BOLD_PLACEHOLDER_" in match.group(0):
            continue
            
        placeholder = f"__ITALIC_PLACEHOLDER_{placeholder_count}__"
        placeholders[placeholder] = {
            "type": "italic",
            "content": match.group(1)
        }
        formatted_text = formatted_text.replace(match.group(0), placeholder, 1)
        placeholder_count += 1
    
    # Handle footnote references - mark them for special handling
    footnote_matches = list(re.finditer(footnote_ref_pattern, formatted_text))
    for match in footnote_matches:
        placeholder = f"__FOOTNOTE_PLACEHOLDER_{placeholder_count}__"
        placeholders[placeholder] = {
            "type": "footnote",
            "content": match.group(1)  # Just the number
        }
        formatted_text = formatted_text.replace(match.group(0), placeholder, 1)
        placeholder_count += 1
    
    # Process each part, replacing placeholders
    # If there are no placeholders in the text, just add it as a single text object
    if not any(placeholder in formatted_text for placeholder in placeholders):
        # Now handle links with the placeholders in place
        parts = re.split(link_pattern, formatted_text)
        
        # Process each part
        i = 0
        while i < len(parts):
            if i < len(parts) and parts[i]:
                rich_text.append({
                    "type": "text",
                    "text": {"content": parts[i]}
                })
            
            # Link (if available)
            if i + 2 < len(parts):
                link_text = parts[i + 1]
                link_url = parts[i + 2]
                
                # Check if this is a Gitea link
                is_gitea_link = "git.door43.org" in link_url
                
                # Ensure Gitea URLs have the proper http prefix
                if is_gitea_link and not link_url.startswith("http"):
                    link_url = "https://" + link_url
                    logging.debug(f"Fixed Gitea URL to: {link_url}")
                
                # Check for internal article link
                article_id = extract_article_id_from_link(link_url)
                notion_page_id = None
                
                if article_id:
                    notion_page_id = find_or_create_page_id_from_article_id(article_id, link_text)
                
                if notion_page_id:
                    # Internal link to a Notion page
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": link_text,
                            "link": {"url": f"https://www.notion.so/{notion_page_id.replace('-', '')}"}
                        },
                        "annotations": {"color": "blue"}
                    })
                else:
                    # Regular external link
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": link_text,
                            "link": {"url": link_url}
                        }
                    })
                i += 2
            
            i += 1
    else:
        # Handle text with placeholders
        # First split text by placeholders to identify segments
        segments = []
        remaining_text = formatted_text
        
        # Find all positions of placeholders in the text
        placeholder_positions = []
        for placeholder in placeholders:
            pos = remaining_text.find(placeholder)
            if pos != -1:
                placeholder_positions.append((pos, placeholder))
        
        # Sort positions
        placeholder_positions.sort()
        
        # Extract segments
        last_pos = 0
        for pos, placeholder in placeholder_positions:
            # Add text before placeholder
            if pos > last_pos:
                segments.append(("text", remaining_text[last_pos:pos]))
            
            # Add the placeholder
            segments.append(("placeholder", placeholder))
            
            # Update last position
            last_pos = pos + len(placeholder)
        
        # Add any remaining text
        if last_pos < len(remaining_text):
            segments.append(("text", remaining_text[last_pos:]))
        
        # Process segments
        for segment_type, segment_content in segments:
            if segment_type == "text":
                # Process links in this text segment
                link_parts = re.split(link_pattern, segment_content)
                
                j = 0
                while j < len(link_parts):
                    if j < len(link_parts) and link_parts[j]:
                        rich_text.append({
                            "type": "text",
                            "text": {"content": link_parts[j]}
                        })
                    
                    # Link (if available)
                    if j + 2 < len(link_parts):
                        link_text = link_parts[j + 1]
                        link_url = link_parts[j + 2]
                        
                        # Check if this is a Gitea link
                        is_gitea_link = "git.door43.org" in link_url
                        
                        # Ensure Gitea URLs have the proper http prefix
                        if is_gitea_link and not link_url.startswith("http"):
                            link_url = "https://" + link_url
                            logging.debug(f"Fixed Gitea URL to: {link_url}")
                        
                        # Check for internal article link
                        article_id = extract_article_id_from_link(link_url)
                        notion_page_id = None
                        
                        if article_id:
                            notion_page_id = find_or_create_page_id_from_article_id(article_id, link_text)
                        
                        if notion_page_id:
                            # Internal link to a Notion page
                            rich_text.append({
                                "type": "text",
                                "text": {
                                    "content": link_text,
                                    "link": {"url": f"https://www.notion.so/{notion_page_id.replace('-', '')}"}
                                },
                                "annotations": {"color": "blue"}
                            })
                        else:
                            # Regular external link
                            rich_text.append({
                                "type": "text",
                                "text": {
                                    "content": link_text,
                                    "link": {"url": link_url}
                                }
                            })
                        j += 2
                    
                    j += 1
            
            elif segment_type == "placeholder":
                # Get placeholder data
                data = placeholders[segment_content]
                
                if data["type"] == "bold":
                    rich_text.append({
                        "type": "text",
                        "text": {"content": data["content"]},
                        "annotations": {"bold": True}
                    })
                elif data["type"] == "italic":
                    rich_text.append({
                        "type": "text",
                        "text": {"content": data["content"]},
                        "annotations": {"italic": True}
                    })
                elif data["type"] == "footnote":
                    # Create a small superscript-like representation using unicode
                    superscript_map = {
                        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
                        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
                    }
                    # Convert digits to superscript
                    superscript_num = ''.join(superscript_map.get(c, c) for c in data['content'])
                    rich_text.append({
                        "type": "text",
                        "text": {"content": superscript_num}
                    })
    
    # If no text was processed (empty string), add an empty text object
    if not rich_text:
        rich_text.append({
            "type": "text",
            "text": {"content": ""}
        })
    
    return rich_text

def process_nested_blockquotes(lines, start_index):
    """Process nested blockquotes and return blocks for them along with parent-child relationships."""
    blocks = []
    parent_child_relations = []  # List of (parent_index, child_block) tuples
    i = start_index
    
    # Group lines by blockquote level
    current_level = 0
    current_lines = []
    level_groups = []  # List of (level, lines) tuples
    
    # First pass: group consecutive lines by their blockquote level
    while i < len(lines) and lines[i].strip().startswith(">"):
        line = lines[i].strip()
        
        # Count the number of '>' characters
        level = 0
        for char in line:
            if char == '>':
                level += 1
            elif not char.isspace():
                break
        
        # If level changed, start a new group
        if level != current_level and current_lines:
            level_groups.append((current_level, current_lines))
            current_lines = []
            current_level = level
        
        # Remove the '>' characters and add to current group
        content_line = line
        for _ in range(level):
            if content_line.startswith(">"):
                content_line = content_line[1:].lstrip()
        
        if content_line or not current_lines:  # Skip empty lines unless it's the first line
            current_lines.append(content_line)
        
        i += 1
    
    # Add the final group
    if current_lines:
        level_groups.append((current_level, current_lines))
    
    # Second pass: create blocks for each group
    for idx, (level, group_lines) in enumerate(level_groups):
        # Skip entirely empty groups
        if not any(line.strip() for line in group_lines):
            continue
            
        quote_content = "\n".join(group_lines)
        
        block = {
            "object": "block",
            "type": "quote",
            "quote": {
                "rich_text": parse_rich_text(quote_content)
            }
        }
        
        # For level 2+ blockquotes, track them for later addition as children
        if level >= 2 and blocks:
            # Remember to add this as a child of the previous block
            parent_index = len(blocks) - 1
            parent_child_relations.append((parent_index, block))
        else:
            blocks.append(block)
    
    return blocks, parent_child_relations, i

def convert_markdown_to_notion_blocks(markdown_content):
    """Convert markdown content to Notion blocks with proper nesting for lists."""
    if not markdown_content:
        return [], []
    
    # Clean up any duplicate lines in the content
    content_lines = markdown_content.splitlines()
    clean_lines = []
    
    # Deduplicate adjacent identical content - sometimes the same content appears twice
    prev_line = None
    for line in content_lines:
        # Skip if line is identical to previous line
        if line == prev_line:
            continue
        clean_lines.append(line)
        prev_line = line
    
    markdown_content = "\n".join(clean_lines)
    
    # Split content into lines for processing
    lines = markdown_content.splitlines()
    
    # Process footnotes first (extract them for later use)
    footnotes = {}
    footnote_pattern = r'\[\^(\d+)\]:\s*(.*?)(?=\n\n|\n\[\^|$)'
    footnote_matches = re.finditer(footnote_pattern, markdown_content, re.DOTALL)
    for match in footnote_matches:
        footnote_num = match.group(1)
        footnote_text = match.group(2).strip()
        footnotes[footnote_num] = footnote_text
    
    # Main blocks array - This will hold the top-level blocks
    blocks = []
    
    # Track current list state to handle nesting
    # Stack items: {'type': 'numbered'/'bulleted', 'indent': int, 'block': dict}
    # 'block' points to the actual list item dictionary object for easy child appending
    list_stack = []
    current_list_type = None  # Track current list type (numbered or bulleted)
    
    # Track the last top-level list item's dictionary object
    last_list_item_block = None
    in_list_content = False  # Flag to track if we're inside list content that shouldn't break the list
    
    i = 0
    while i < len(lines):
        original_line = lines[i] # Keep original line for indent calculation
        line = original_line.strip()
        
        # Skip empty lines but consider them when determining list continuity
        if not line:
            # Check if next line continues a list
            if list_stack and i+1 < len(lines):
                next_line = lines[i+1].strip()
                is_ordered = re.match(r'^\\s*\\d+\\.\\s', lines[i+1])
                is_unordered = lines[i+1].lstrip().startswith(('* ', '- '))
                
                # Only clear stack if list type changes or it's not a list at all
                if not (is_ordered or is_unordered):
                    # Not a list item next, so we terminate the list unless it's
                    # unindented text that should be part of the list content
                    in_list_content = False
                    list_stack = []
                    current_list_type = None
                # If list type changes, clear stack but keep track of new type
                elif (is_ordered and current_list_type == 'bulleted') or (is_unordered and current_list_type == 'numbered'):
                    list_stack = []
                    current_list_type = 'numbered' if is_ordered else 'bulleted'
            i += 1
            continue
        
        # Determine line type and indentation
        current_indent = len(original_line) - len(original_line.lstrip())
        
        # --- Handle Headings (always terminate lists) ---
        if line.startswith('# '):
            list_stack = []; current_list_type = None; in_list_content = False
            blocks.append({
                "object": "block", "type": "heading_1",
                "heading_1": {"rich_text": parse_rich_text(line[2:])}
            })
            i += 1; continue
        elif line.startswith('## '):
            list_stack = []; current_list_type = None; in_list_content = False
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": parse_rich_text(line[3:])}
            })
            i += 1; continue
        elif line.startswith('### '):
            list_stack = []; current_list_type = None; in_list_content = False
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": parse_rich_text(line[4:])}
            })
            i += 1; continue
        elif line.startswith('#### '):
            list_stack = []; current_list_type = None; in_list_content = False
            blocks.append({
                "object": "block", "type": "heading_3", # Notion only has h1-h3
                "heading_3": {"rich_text": parse_rich_text(line[5:])}
            })
            i += 1; continue
        
        # --- Handle Blockquotes (terminate lists) ---
        elif line.startswith('> '):
            list_stack = []; current_list_type = None; in_list_content = False
            # Process blockquotes and append to main blocks list
            # Note: process_nested_blockquotes needs refinement if it uses a similar flattening logic
            quote_blocks, quote_relations, new_i = process_nested_blockquotes(lines, i)
            blocks.extend(quote_blocks)
            # TODO: Handle quote_relations if Notion API requires separate child appends for nested quotes
            i = new_i; continue
        
        # Handle empty blockquote separator
        elif line == '>':
            list_stack = []; current_list_type = None; in_list_content = False
            blocks.append({
                "object": "block", "type": "quote",
                "quote": {"rich_text": [{"type": "text", "text": {"content": " "}}]}
            })
            i += 1; continue
        
        # --- Handle Numbered Lists ---
        elif re.match(r'^\\d+\\.\\s', line):
            match = re.match(r'^(\\d+)\\.\\s+(.*)', line)
            if not match: i+=1; continue

            content = match.group(2)
            list_type = 'numbered'
            
            # --- List Item Processing Logic ---
            # Adjust stack based on indent: pop items with >= indent
            while list_stack and list_stack[-1]['indent'] >= current_indent:
                list_stack.pop()

            # Create the list item block (as a dictionary)
            list_item = {
                "object": "block",
                "type": f"{list_type}_list_item",
                f"{list_type}_list_item": {"rich_text": parse_rich_text(content), "children": []}
            }

            # Determine parent and add item
            if list_stack and list_stack[-1]['indent'] < current_indent:
                # This is a child of the item on top of the stack
                parent_block_dict = list_stack[-1]['block']
                parent_list_type = list_stack[-1]['type']
                # Append child directly to parent's children list (in the dictionary)
                parent_block_dict[f"{parent_list_type}_list_item"]['children'].append(list_item)
            else:
                # This is a top-level list item (or start of a new list)
                blocks.append(list_item)
                last_list_item_block = list_item # Track last top-level item

            # Push the current item onto the stack
            list_stack.append({
                'type': list_type,
                'indent': current_indent,
                'block': list_item # Store reference to the list item dictionary
            })

            current_list_type = list_type
            in_list_content = True
            i += 1
            continue
            # --- End List Item Processing ---

        # --- Handle Bulleted Lists ---
        elif line.lstrip().startswith(('* ', '- ')):
             if line.lstrip().startswith('* '): content = line.lstrip()[2:]
             else: content = line.lstrip()[2:]
             list_type = 'bulleted'

             # --- List Item Processing Logic ---
             # Adjust stack based on indent: pop items with >= indent
             while list_stack and list_stack[-1]['indent'] >= current_indent:
                 list_stack.pop()

             # Create the list item block (as a dictionary)
             list_item = {
                 "object": "block",
                 "type": f"{list_type}_list_item",
                 f"{list_type}_list_item": {"rich_text": parse_rich_text(content), "children": []}
             }

             # Determine parent and add item
             if list_stack and list_stack[-1]['indent'] < current_indent:
                 # This is a child of the item on top of the stack
                 parent_block_dict = list_stack[-1]['block']
                 parent_list_type = list_stack[-1]['type']
                 # Append child directly to parent's children list (in the dictionary)
                 parent_block_dict[f"{parent_list_type}_list_item"]['children'].append(list_item)
             else:
                 # This is a top-level list item (or start of a new list)
                 blocks.append(list_item)
                 last_list_item_block = list_item # Track last top-level item

             # Push the current item onto the stack
             list_stack.append({
                 'type': list_type,
                 'indent': current_indent,
                 'block': list_item # Store reference to the list item dictionary
             })

             current_list_type = list_type
             in_list_content = True
             i += 1
             continue
             # --- End List Item Processing ---
        
        # --- Handle Code Blocks ---
        elif line.startswith('```'):
            list_stack = []; current_list_type = None; in_list_content = False
            code_language = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "object": "block", "type": "code",
                "code": {"rich_text": [{"type": "text", "text": {"content": "\\n".join(code_lines)}}],
                         "language": code_language if code_language else "plain text"}
            })
            if i < len(lines): i += 1 # Skip closing ```
            continue
        
        # --- Handle Footnote Definitions ---
        elif re.match(r'\\[\\^(\\d+)\\]:', line):
            # Skip footnote definitions as we already extracted them
            i += 1
            continue
        
        # --- Special case: unindented text that should continue the previous list item ---
        # Check if we are in a list context and the line is unindented text
        elif list_stack and not current_indent and in_list_content:
            # Append this line to the last list item block encountered
            target_block = list_stack[-1]['block'] # Append to the item on stack top
            target_list_type = list_stack[-1]['type']
            
            if target_block:
                # Get existing rich text
                rich_text_list = target_block[f"{target_list_type}_list_item"]["rich_text"]
                existing_text = ""
                for text_obj in rich_text_list:
                     if text_obj["type"] == "text":
                         existing_text += text_obj["text"]["content"]
                
                # Append the new line with a space
                new_content = existing_text.rstrip() + " " + line
                
                # Replace the rich text with the combined content
                target_block[f"{target_list_type}_list_item"]["rich_text"] = parse_rich_text(new_content)
                
                i += 1
                continue
            else:
                 # Fallback: treat as paragraph if we somehow lost the last list item
                 logging.warning("Trying to append list content, but couldn't find target block.")
                 pass # Fall through to paragraph handling

        # --- Default to Paragraph ---
        else:
            # Paragraphs terminate lists unless it's handled by the special case above
            should_terminate_list = not list_stack or line.startswith(('# ', '## ', '### ', '```', '> '))
            
            if should_terminate_list:
                list_stack = []; current_list_type = None; in_list_content = False
            
            # Collect multi-line paragraphs
            paragraph_lines = [line]
            next_i = i + 1
            while (next_i < len(lines) and 
                   lines[next_i].strip() and 
                   not lines[next_i].strip().startswith(('# ', '## ', '### ', '#### ', '> ', '* ', '- ', '```', '[^')) and
                   not re.match(r'^\\s*\\d+\\.\\s', lines[next_i])):
                paragraph_lines.append(lines[next_i].strip())
                next_i += 1
            
            paragraph_content = " ".join(paragraph_lines)
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": parse_rich_text(paragraph_content)}
            })
            
            i = next_i
            continue
    
    # --- Add Footnotes ---
    if footnotes:
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "Footnotes"}}]}
        })
        for num, text in sorted(footnotes.items()):
            footnote_content = f"[{num}] {text}"
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": parse_rich_text(footnote_content)}
            })
    
    # The 'blocks' list now contains the hierarchical structure.
    # The caller function (create_article_page) needs to handle sending this structure
    # to Notion, potentially requiring modification if it expects a flat list.
    # For now, we return the structured 'blocks'. The flattening logic is removed.
    
    # Return the list of top-level blocks (which contain nested children)
    # The parent_child_relations list is no longer needed as nesting is implicit.
    return blocks, [] # Return empty list for relations

def extract_children(blocks, flattened_blocks):
    """DEPRECATED: This function is no longer used as nesting is handled directly."""
    pass

def extract_article_id_from_link(link_url):
    """Extract article ID from an internal link."""
    article_id = None
    
    # Check for the pattern ../folder/01.md or ../folder/
    if "../" in link_url:
        # Pattern 1: ../folder/01.md
        if "01.md" in link_url:
            match = re.search(r'\.\.\/([^\/]+)\/01\.md', link_url)
            if match:
                article_id = match.group(1)
        # Pattern 2: ../folder/
        elif link_url.endswith("/"):
            match = re.search(r'\.\.\/([^\/]+)\/', link_url)
            if match:
                article_id = match.group(1)
        # Additional pattern: 01-article-name.md
        elif re.search(r'(\d+-[^\/]+)\.md$', link_url):
            match = re.search(r'(\d+-[^\/]+)\.md$', link_url)
            if match:
                article_id = match.group(1)
    
    return article_id

def find_or_create_page_id_from_article_id(article_id, link_text=""):
    """Find a Notion page ID corresponding to an article ID or title."""
    
    # First, check if we have a direct match in our page cache
    if article_id and article_id in page_cache:
        return page_cache[article_id]
    
    # Try various likely article ID formats
    potential_ids = [article_id]
    
    # Remove common suffixes like "01" or numbers
    if article_id:
        base_id = re.sub(r'\d+$', '', article_id).rstrip('-')
        if base_id != article_id:
            potential_ids.append(base_id)
    
    # Try the link text which often contains the article title
    potential_titles = []
    if link_text:
        potential_titles.append(link_text)
        
        # Common format: article title (see: About something)
        title_match = re.match(r'(.+?)\s*\(.*\)', link_text)
        if title_match:
            potential_titles.append(title_match.group(1).strip())
    
    # Check all potential IDs
    for potential_id in potential_ids:
        if potential_id in page_cache:
            return page_cache[potential_id]
    
    # Check all potential titles
    for potential_title in potential_titles:
        if potential_title in page_cache:
            return page_cache[potential_title]
    
    # If we're here, we didn't find it
    logging.warning(f"Could not find Notion page for internal link: article_id={article_id}, link_text={link_text}")
    
    # Special case: look for a normalized version of the title
    # (e.g., "Translator Qualifications" vs "translator-qualifications")
    for cached_id, page_id in page_cache.items():
        # Skip non-page ids
        if not cached_id or len(cached_id) < 3:
            continue
            
        # Check if this cache entry looks like a page title
        if re.match(r'^[A-Z]', cached_id):
            # Normalize both titles for comparison (lowercase, remove spaces and punctuation)
            normalized_cached = re.sub(r'[^a-z0-9]', '', cached_id.lower())
            
            for potential_title in potential_titles:
                normalized_potential = re.sub(r'[^a-z0-9]', '', potential_title.lower())
                
                # If normalized versions match, use this page ID
                if normalized_cached == normalized_potential:
                    logging.info(f"Found fuzzy match for '{potential_title}' -> '{cached_id}' (ID: {page_id})")
                    return page_id
    
    return None

# --- Post-Processing for Links ---

def update_page_links(notion, page_id):
    """
    Update links in a page by replacing Gitea links with internal Notion links
    where possible.
    """
    if not page_id:
        return False
        
    try:
        # Get all blocks in the page
        blocks_response = notion.blocks.children.list(block_id=page_id)
        blocks = blocks_response.get("results", [])
        
        # Handle pagination if there are many blocks
        while blocks_response.get("has_more", False):
            next_cursor = blocks_response.get("next_cursor")
            if next_cursor:
                blocks_response = notion.blocks.children.list(
                    block_id=page_id, 
                    start_cursor=next_cursor
                )
                blocks.extend(blocks_response.get("results", []))
            else:
                break
        
        update_count = 0
        link_count = 0
        
        # Process each block
        for block in blocks:
            block_id = block.get("id")
            block_type = block.get("type")
            
            if not block_id or not block_type:
                continue
                
            # Get rich text content from the block based on its type
            rich_text = None
            if block_type == "paragraph":
                rich_text = block.get("paragraph", {}).get("rich_text", [])
            elif block_type == "heading_1":
                rich_text = block.get("heading_1", {}).get("rich_text", [])
            elif block_type == "heading_2":
                rich_text = block.get("heading_2", {}).get("rich_text", [])
            elif block_type == "heading_3":
                rich_text = block.get("heading_3", {}).get("rich_text", [])
            elif block_type == "bulleted_list_item":
                rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
            elif block_type == "numbered_list_item":
                rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
            elif block_type == "quote":
                rich_text = block.get("quote", {}).get("rich_text", [])
            
            if not rich_text:
                continue
                
            # Check for links that need updating
            updated_rich_text = []
            modified = False
            
            for text_obj in rich_text:
                if text_obj.get("type") == "text":
                    link = text_obj.get("text", {}).get("link")
                    
                    if link and isinstance(link, dict) and "url" in link:
                        link_url = link["url"]
                        link_count += 1
                        
                        # Check if this is a Gitea link that can be converted
                        is_gitea_link = ("git.door43.org" in link_url and 
                                         GITEA_REPO_OWNER in link_url and 
                                         GITEA_REPO_NAME in link_url)
                        
                        # Also check if the link is in our URL mapping
                        matching_page_id = None
                        
                        # Try exact match first
                        if link_url in url_to_page_id_map:
                            matching_page_id = url_to_page_id_map[link_url]
                        # Then try variations (for relative paths)
                        else:
                            # Check for article ID in the URL
                            article_id = extract_article_id_from_link(link_url)
                            if article_id and article_id in page_cache:
                                matching_page_id = page_cache[article_id]
                            # Try different URL formats
                            elif "translate/" in link_url:
                                # Extract the part after "translate/"
                                match = re.search(r'translate/([^/]+)(?:/01\.md)?', link_url)
                                if match:
                                    article_id = match.group(1)
                                    if article_id in page_cache:
                                        matching_page_id = page_cache[article_id]
                        
                        if matching_page_id:
                            # Update the link to internal Notion link
                            updated_text_obj = text_obj.copy()
                            updated_text_obj["text"]["link"]["url"] = f"https://www.notion.so/{matching_page_id.replace('-', '')}"
                            updated_rich_text.append(updated_text_obj)
                            modified = True
                            update_count += 1
                            logging.debug(f"Updated link from {link_url} to Notion page {matching_page_id}")
                        else:
                            # Keep original link but log
                            if is_gitea_link:
                                logging.warning(f"Could not find matching Notion page for Gitea link: {link_url}")
                            updated_rich_text.append(text_obj)
                    else:
                        # Not a link or no URL, keep as is
                        updated_rich_text.append(text_obj)
                else:
                    # Not a text object, keep as is
                    updated_rich_text.append(text_obj)
            
            # Update the block if modified
            if modified:
                try:
                    update_data = {
                        block_type: {
                            "rich_text": updated_rich_text
                        }
                    }
                    
                    notion.blocks.update(block_id=block_id, **update_data)
                    time.sleep(0.3)  # Avoid rate limiting
                except Exception as update_err:
                    logging.error(f"Error updating block {block_id}: {str(update_err)}")
        
        # Report results
        if link_count > 0:
            logging.info(f"Processed {link_count} links in page {page_id}, updated {update_count} links to internal Notion links")
        
        return update_count > 0
    
    except Exception as e:
        logging.error(f"Error updating links in page {page_id}: {str(e)}")
        return False

def process_all_pages_links():
    """
    Second phase: Process all pages to update Gitea links to internal Notion links.
    Uses the URL mapping built during page creation.
    """
    logging.info(f"Starting phase 2: Updating internal links in all pages...")
    logging.info(f"Found {len(page_cache)} pages in cache to process")
    
    # Keep track of unique page IDs (since the cache maps both titles and IDs to page_ids)
    processed_page_ids = set()
    update_count = 0
    
    for key, page_id in page_cache.items():
        # Skip non-page entries or already processed pages
        if not page_id or page_id in processed_page_ids or len(key) < 3:
            continue
            
        processed_page_ids.add(page_id)
        
        # Update links in this page
        if update_page_links(notion, page_id):
            update_count += 1
        
        # Add a small delay to avoid rate limiting
        time.sleep(0.3)
    
    logging.info(f"Link update process complete. Updated links in {update_count} pages.")
    return update_count > 0

# --- Page Creation (Updated to record URL mappings) ---

def create_article_page(notion, title, article_id, parent_page_id):
    """Create an article page, populating with correctly formatted content."""
    logging.info(f"Attempting to create article page '{title}' ({article_id}) under parent {parent_page_id}")
    try:
        if not parent_page_id:
             logging.error(f"Cannot create page '{title}', invalid parent_page_id provided.")
             return None
             
        page_props = {"title": {"title": [{"type": "text", "text": {"content": title}}]}}
        
        # Get content first
        content = fetch_article_content(article_id)
        if not content:
            logging.warning(f"No content fetched for article {article_id} ('{title}').")
            content = "" # Create empty page if no content
            
        # Convert markdown to blocks. This now returns a *structured* list.
        # The second return value (parent_child_relations) is now empty.
        structured_blocks, _ = convert_markdown_to_notion_blocks(content)
        
        # Add H1 title at the beginning if it doesn't exist
        has_h1_title = False
        if structured_blocks and structured_blocks[0].get("type") == "heading_1":
             has_h1_title = True
             
        initial_blocks = []
        if not has_h1_title:
            initial_blocks.append({
                "object": "block", 
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": title}}]}
            })
        
        # Combine initial blocks with content blocks
        all_blocks_structured = initial_blocks + structured_blocks
            
        # Notion API can handle nested blocks directly in the 'children' array during page creation
        # or block appending, as long as the structure is correct JSON.
        # We need to ensure the structure built by convert_markdown_to_notion_blocks is correct.
        
        page_id = None
        # Try creating page with all blocks (up to Notion's limit)
        try:
             page_data = {
                 "parent": {"page_id": parent_page_id}, 
                 "properties": page_props, 
                 # Send the structured blocks directly
                 "children": all_blocks_structured[:100] # Limit initial creation
             }
             response = notion.pages.create(**page_data)
             page_id = response.get("id")
             if not page_id:
                  logging.error(f"Failed to create page '{title}' (no ID received).")
                  return None
             logging.info(f"Created article page: '{title}' with ID: {page_id}")
             
             # If there were more blocks, append them
             if len(all_blocks_structured) > 100:
                  logging.info(f"Appending remaining {len(all_blocks_structured) - 100} blocks...")
                  for i in range(100, len(all_blocks_structured), 100):
                       batch = all_blocks_structured[i:i+100]
                       try:
                           notion.blocks.children.append(block_id=page_id, children=batch)
                           logging.debug(f"Appended batch of {len(batch)} content blocks to page {page_id}.")
                           time.sleep(0.5) # Rate limit between batches
                       except Exception as append_err:
                           logging.error(f"Error appending content block batch to page {page_id}: {append_err}")
                           # Continue trying to append remaining batches
                           
        except Exception as create_err:
             # Log the detailed error, including potentially malformed block structure
             logging.error(f"Error creating page '{title}' with blocks: {create_err}", exc_info=True)
             # Attempt to create the page with just the title if block creation failed
             if not page_id:
                  try:
                       page_data_simple = {
                           "parent": {"page_id": parent_page_id}, 
                           "properties": page_props
                       }
                       response = notion.pages.create(**page_data_simple)
                       page_id = response.get("id")
                       if page_id:
                            logging.warning(f"Created page '{title}' (ID: {page_id}) without initial content due to block error.")
                       else:
                            logging.error(f"Failed to create page '{title}' even without content.")
                            return None
                  except Exception as simple_create_err:
                       logging.error(f"Error creating simple page '{title}': {simple_create_err}")
                       return None

        # Update cache and URL mapping if page was created
        if page_id:
            page_cache[title] = page_id
            if article_id: 
                page_cache[article_id] = page_id 
                gitea_url = get_gitea_article_url(article_id)
                map_url_to_page_id(gitea_url, page_id)
                relative_url = f"../{article_id}/"
                map_url_to_page_id(relative_url, page_id)
                relative_url_md = f"../{article_id}/01.md"
                map_url_to_page_id(relative_url_md, page_id)
            
            # No need to process parent_child_relations separately anymore
            save_cache_to_file()
            return page_id
        else:
            return None
            
    except Exception as e:
        # Use exc_info=True to log the full traceback for debugging
        logging.error(f"Unexpected error in create_article_page for '{title}' ({article_id}): {e}", exc_info=True) 
        return None

def create_section_page(notion, title, parent_page_id):
    """Create a new section page (used as a container in the hierarchy)."""
    logging.info(f"Creating section page '{title}' under parent {parent_page_id}")
    try:
        if not parent_page_id:
             logging.error(f"Cannot create section page '{title}', invalid parent_page_id provided.")
             return None
             
        page_data = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title}}]}
            },
            "children": [{
                 "object": "block", "type": "heading_1",
                 "heading_1": {"rich_text": [{"type": "text", "text": {"content": title}}]}
            }]
        }
        
        response = notion.pages.create(**page_data)
        page_id = response.get("id")
        logging.info(f"Created new section page: '{title}' with ID: {page_id}")
        return page_id
    except Exception as e:
        logging.error(f"Error creating section page '{title}': {str(e)}")
        return None

# --- TOC Building Logic (Updated to add post-processing phase) ---

def build_translate_section(use_remote=True, process_content=True, section_limit=None, start_section=0, update_links=True):
    """Build the Translate section structure according to the TOC."""
    # Load TOC data
    toc_data = load_toc_data(use_remote=use_remote)
    if not toc_data: return False

    # --- Visual TOC Setup ---
    translate_toggle_id = create_toggle(notion, VISUAL_TOC_PARENT_PAGE_ID, "Translate", level=1, is_heading=True)
    if not translate_toggle_id:
        logging.error("Failed to create Translate toggle for visual TOC")
        return False
    logging.info(f"Created H1 Translate toggle (visual TOC root) with ID: {translate_toggle_id}")

    # --- Page Hierarchy Setup ---
    translate_page_id = find_page_by_title(notion, "Translate") 
    if translate_page_id:
        logging.info(f"Found existing top-level Translate page for hierarchy: {translate_page_id}")
    else:
        translate_page_id = create_section_page(notion, "Translate", VISUAL_TOC_PARENT_PAGE_ID)
        if not translate_page_id:
            logging.error("Failed to create top-level Translate page for hierarchy")
            return False
        logging.info(f"Created top-level Translate page for hierarchy: {translate_page_id}")
        time.sleep(1)
        
    page_cache["Translate"] = translate_page_id 

    # --- Process Sections ---
    all_sections = toc_data.get("sections", [])
    sections_to_process = all_sections
    
    if start_section > 0 and start_section < len(all_sections):
        logging.info(f"Starting from section index {start_section} ('{all_sections[start_section].get('title', 'N/A')}')")
        sections_to_process = all_sections[start_section:]
    
    if section_limit is not None and section_limit > 0:
        sections_to_process = sections_to_process[:section_limit]
        logging.info(f"Processing {len(sections_to_process)} sections (limited to {section_limit})")
    else:
         logging.info(f"Processing {len(sections_to_process)} sections.")

    # Phase 1: Create all pages and build the page/URL mapping
    logging.info("Starting phase 1: Creating all pages and building URL mapping...")
    for section in sections_to_process:
        build_section(
            notion, 
            translate_toggle_id,  # Parent for visual TOC items
            section, 
            translate_page_id,    # Parent for the actual pages
            level=1,              
            parent_section="",    
            delay_seconds=0.5,
            indent_level=0,       
            process_content=process_content
        )
        time.sleep(0.5)
    
    logging.info(f"Phase 1 complete. Created {len(page_cache)} cached page entries and {len(url_to_page_id_map)} URL mappings")
    
    # Phase 2: Update internal links in all pages (if requested)
    if update_links:
        process_all_pages_links()
    else:
        logging.info("Skipping phase 2 (link updating) as requested")
    
    # Save final cache
    save_cache_to_file()
    
    logging.info("Successfully built Translate section structure (Visual TOC and Page Hierarchy)")
    return True

# --- Main Execution --- 
# Kept for standalone testing, but main logic is in import_all.py
if __name__ == "__main__":
    logging.info("Starting standalone build TOC structure")
    # Example: Build sections starting from index 1 (Defining a Good Translation), limit to 1 section
    success = build_translate_section(use_remote=True, process_content=True, section_limit=1, start_section=1)
    
    if success:
        logging.info("Standalone TOC structure build successful")
    else:
        logging.error("Standalone TOC structure build failed") 

def get_gitea_article_url(article_id):
    """Convert an article ID to its full Gitea URL."""
    return f"https://git.door43.org/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/src/branch/master/translate/{article_id}/01.md"

def map_url_to_page_id(url, page_id):
    """Add a mapping from a Gitea URL to a Notion page ID for post-processing."""
    if url and page_id:
        url = url.strip()
        # Handle various URL formats
        if "01.md" not in url and url.endswith("/"):
            # Map both the directory and the 01.md file
            url_to_page_id_map[url] = page_id
            url_to_page_id_map[f"{url}01.md"] = page_id
        elif "01.md" in url:
            url_to_page_id_map[url] = page_id
            # Also map the directory version
            dir_url = url.replace("01.md", "")
            url_to_page_id_map[dir_url] = page_id
        else:
            url_to_page_id_map[url] = page_id
            
        # Also map with and without https://
        if url.startswith("https://"):
            non_https = url[8:]
            url_to_page_id_map[non_https] = page_id
        else:
            https_url = f"https://{url}"
            url_to_page_id_map[https_url] = page_id 

def save_cache_to_file(filename="page_cache.json"):
    """Save page cache to a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump({
                "page_cache": page_cache,
                "url_map": url_to_page_id_map
            }, f, indent=2)
        logging.info(f"Saved {len(page_cache)} page cache entries and {len(url_to_page_id_map)} URL mappings to {filename}")
        return True
    except Exception as e:
        logging.error(f"Error saving cache to {filename}: {str(e)}")
        return False 

def build_section(notion, parent_id, section, parent_page_id, level=1, parent_section="", delay_seconds=0.5, indent_level=0, process_content=True):
    """
    Recursively build a section of the TOC and the parallel page structure.
    
    Visual TOC:
      - Top-level sections (level 1) and Just-in-Time Learning Modules are toggles.
      - Subsections are indented links with visual indicators.
    Page Hierarchy:
      - Pages are created for sections with subsections or articles.
      - Pages are nested under their parent section's page.
    """
    title = section.get("title", "Untitled Section")
    link = section.get("link", "")
    subsections = section.get("sections", [])
    article_id = None
    current_page_id = None # This will hold the ID of the page created for THIS section/article

    if link:
        # Extract article_id from link like '../qualities/' -> 'qualities'
        parts = [p for p in link.strip('/').split('/') if p and p != '..']
        if parts:
            article_id = parts[-1]
        if not article_id:
             logging.warning(f"Could not extract article_id from link: {link} for title '{title}'")

    # --- Create the Page in the Hierarchy --- 
    # Create a page if it's an article OR if it's a section with subsections
    needs_page = bool(article_id or subsections) 

    if needs_page:
        # Check cache first by title, then by article_id
        existing_page_id = page_cache.get(title) or (article_id and page_cache.get(article_id))

        if existing_page_id:
            current_page_id = existing_page_id
            logging.info(f"Cache hit for page '{title}': {current_page_id}")
        else:
             # Page not in cache, try finding it via API (less preferred due to potential slowness)
             existing_page_id_api = find_page_by_title(notion, title) 
             if existing_page_id_api:
                  current_page_id = existing_page_id_api
                  logging.info(f"Found existing page for '{title}' via API: {current_page_id}")
                  # Update cache
                  page_cache[title] = current_page_id
                  if article_id: page_cache[article_id] = current_page_id
             else:
                 # Page doesn't exist, create it
                 logging.info(f"Creating page for '{title}' under parent {parent_page_id}")
                 if article_id:
                     # Use the SIMPLIFIED create_article_page
                     current_page_id = create_article_page(notion, title, article_id, parent_page_id)
                 elif subsections: # Only create section pages if they have children and NO article link
                     current_page_id = create_section_page(notion, title, parent_page_id)
                 
                 # If page creation failed, current_page_id will be None
                 if not current_page_id:
                     logging.error(f"Failed to create page for '{title}'.")
                     # No page created, cannot proceed with subsections under it
                     # We still need to create the visual TOC entry though

    # --- Create the Visual TOC Entry --- 
    should_be_toggle_in_visual_toc = (level == 1 or parent_section == "Just-in-Time Learning Modules")
    visual_toc_container_id = parent_id 

    if should_be_toggle_in_visual_toc:
        toggle_id = create_toggle(notion, parent_id, title, level)
        if not toggle_id:
            logging.error(f"Failed to create visual TOC toggle for '{title}'")
            return None # Stop processing this branch if toggle fails
            
        visual_toc_container_id = toggle_id 
        time.sleep(delay_seconds)
        
        # Add link inside toggle if a corresponding page was created/found
        if current_page_id:
            add_page_link_to_toggle(notion, visual_toc_container_id, title, current_page_id, is_child=False) 
            time.sleep(delay_seconds)

    else: # Not a toggle in the visual TOC
        # Add indented link if a page exists
        if current_page_id:
            add_page_link_to_toggle(notion, parent_id, title, current_page_id, is_child=True, indent_level=indent_level)
            time.sleep(delay_seconds)
        # Otherwise, add indented text block (e.g., for a section header without its own content page)
        elif subsections: 
            prefix = "    " * indent_level
            if indent_level == 1: prefix += "→ "
            elif indent_level == 2: prefix += "○ "
            else: prefix += "• "
            try:
                notion.blocks.children.append(
                    block_id=parent_id,
                    children=[{ "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"{prefix}{title}"}, "annotations": {"bold": True}}]}}]
                )
                time.sleep(delay_seconds)
            except Exception as e:
                 logging.error(f"Failed to add text block for section header '{title}': {e}")

    # --- Process Subsections Recursively --- 
    # Only proceed if a valid parent page exists for the hierarchy
    # Use the created current_page_id as the parent for the next level's pages
    # The visual TOC parent (visual_toc_container_id) is handled separately
    if current_page_id or not needs_page: # Proceed if page created or if it's just a leaf node with no subsections
        next_indent_level = indent_level + 1 if not should_be_toggle_in_visual_toc else 0
        
        for subsection in subsections:
            # Pass current_page_id as the parent_page_id for the hierarchy
            # If current_page_id is None (e.g., creation failed), subsequent pages won't be created under it
            build_section(
                notion, 
                visual_toc_container_id, # Parent for visual TOC items
                subsection, 
                current_page_id,     # Parent for the actual pages in hierarchy
                level + 1, 
                title,               # Pass current title as parent_section
                delay_seconds,
                indent_level=next_indent_level,
                process_content=process_content # Pass this flag down
            )
    else:
        logging.warning(f"Skipping subsections for '{title}' because its page could not be created/found.")

    return current_page_id # Return the ID of the page created/found for this section 