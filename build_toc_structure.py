# build_toc_structure.py
# Updated version incorporating link parsing fixes, multi-manual support, and callouts.
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

# Configure logging (Use logger obtained from main script or default)
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Notion client (Should be passed or configured globally)
notion_auth_key = os.environ.get("NOTION_API_KEY")
if not notion_auth_key:
    logger.critical("NOTION_API_KEY not found in environment variables!")
    # Handle error appropriately - perhaps raise exception
    notion = None
else:
    # Add error handling for Notion client initialization
    try:
        notion = Client(auth=notion_auth_key)
        # Optionally test connection, e.g., notion.users.me()
    except Exception as e:
        logger.critical(f"Failed to initialize Notion client: {e}")
        notion = None


# Parent Notion page ID (Main page where the TOC toggles live)
VISUAL_TOC_MAIN_PARENT_PAGE_ID = "1c372d5af2de80e08b11cd7748a1467d" # TODO: Make this configurable
HIERARCHY_MAIN_PARENT_ID = "1c372d5af2de80e08b11cd7748a1467d" # TODO: Make this configurable


# Gitea API settings
GITEA_API_BASE = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_API_KEY = os.environ.get("GITEA_API_KEY")

# --- Cache ---
# Global caches (Manage access carefully if using threading/async later)
page_cache = {}             # Maps various keys (title:X, id:Y, gitea_content:Z) to values (page_id or content)
url_to_page_id_map = {}   # Maps Gitea/relative URLs to Notion Page IDs
config_cache = {}           # Maps config keys (config:manual_name) to loaded config data
id_title_map_global = {}  # Maps article_id to its primary display title

# --- Gitea Fetching ---

def fetch_gitea_content(path, is_binary=False):
    """Fetch content from Gitea API, using cache."""
    cache_key = f"gitea_content:{path}"
    if cache_key in page_cache:
         return page_cache[cache_key]

    url = f"{GITEA_API_BASE}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/contents/{path}"
    headers = {}
    if GITEA_API_KEY:
        headers["Authorization"] = f"token {GITEA_API_KEY}"

    logger.debug(f"Fetching Gitea content from: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=30) # Increased timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Check if content field exists and is not null/empty
        if data and "content" in data and data["content"]:
             content_raw = base64.b64decode(data["content"])
             if is_binary:
                 content = content_raw
             else:
                 try:
                     content = content_raw.decode("utf-8")
                 except UnicodeDecodeError:
                     logger.warning(f"UTF-8 decode error for Gitea path: {path}. Trying latin-1.")
                     content = content_raw.decode("latin-1", errors='ignore') # Ignore errors on fallback

             page_cache[cache_key] = content # Cache successful fetch
             return content
        else:
            # Log if content is missing or empty in a valid response
            logger.warning(f"No content found or empty content field for Gitea path: {path}")
            page_cache[cache_key] = None # Cache the miss (empty/no content)
            return None
    except requests.exceptions.Timeout:
         logger.error(f"Timeout while fetching Gitea content: {path}")
         page_cache[cache_key] = None
         return None
    except requests.exceptions.HTTPError as e:
         # Handle HTTP errors (like 404 Not Found, 401 Unauthorized, etc.)
         status_code = e.response.status_code
         if status_code == 404:
             logger.warning(f"Gitea content not found (404): {path}")
         elif status_code == 401:
              logger.error(f"Gitea authorization failed (401) for {path}. Check GITEA_API_KEY.")
         else:
              logger.error(f"HTTP error fetching content from Gitea ({path}), Status: {status_code}. Error: {e}")
         page_cache[cache_key] = None # Cache the failure
         return None
    except requests.exceptions.RequestException as e:
         # Handle other potential network errors (DNS, connection refused, etc.)
         logger.error(f"Network error fetching content from Gitea ({path}): {str(e)}")
         page_cache[cache_key] = None
         return None
    except Exception as e:
        # Catch any other unexpected errors during fetch/decode
        logger.error(f"Unexpected error fetching/processing Gitea content ({path}): {str(e)}", exc_info=True)
        page_cache[cache_key] = None
        return None

def load_toc_data(manual_name):
    """Load Table of Contents data from Gitea for a specific manual."""
    toc_path = f"{manual_name}/toc.yaml"
    logger.info(f"Fetching TOC data from Gitea for manual '{manual_name}'...")
    content = fetch_gitea_content(toc_path)
    if content:
        try:
            # Add more robust YAML check
            if not isinstance(content, str) or ':' not in content:
                 logger.error(f"Content fetched for {toc_path} does not appear to be valid YAML.")
                 return None
            toc_data = yaml.safe_load(content)
            # Basic validation of TOC structure
            if isinstance(toc_data, dict) and 'sections' in toc_data:
                return toc_data
            else:
                logger.error(f"Parsed TOC data for {manual_name} is not in expected format (dict with 'sections').")
                return None
        except yaml.YAMLError as e:
            logger.error(f"Error parsing TOC YAML for {manual_name}: {str(e)}")
            logger.debug(f"Content was: {content[:500]}")
        except Exception as e:
             logger.error(f"Unexpected error loading TOC YAML for {manual_name}: {str(e)}")
    return None

def load_config_data(manual_name):
    """Load config data (dependencies/recommendations) from Gitea."""
    config_key = f"config:{manual_name}"
    if config_key in config_cache:
        return config_cache[config_key]

    config_path = f"{manual_name}/config.yaml"
    logger.info(f"Fetching config data from Gitea for manual '{manual_name}'...")
    content = fetch_gitea_content(config_path)
    if content:
        try:
             if not isinstance(content, str) or ':' not in content:
                  logger.error(f"Content fetched for {config_path} does not appear to be valid YAML.")
                  config_cache[config_key] = None; return None
             config_data = yaml.safe_load(content)
             if isinstance(config_data, dict): # Basic validation
                 config_cache[config_key] = config_data
                 return config_data
             else:
                 logger.error(f"Parsed Config data for {manual_name} is not a dictionary.")
                 config_cache[config_key] = None; return None
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config YAML for {manual_name}: {str(e)}")
            logger.debug(f"Content was: {content[:500]}")
        except Exception as e:
             logger.error(f"Unexpected error loading config YAML for {manual_name}: {str(e)}")

    config_cache[config_key] = None
    return None

def fetch_article_content(manual_name, article_id):
    """Fetch main article content (01.md) from Gitea."""
    path = f"{manual_name}/{article_id}/01.md"
    return fetch_gitea_content(path)

def fetch_article_title(manual_name, article_id):
    """Fetch article title (title.md) from Gitea."""
    path = f"{manual_name}/{article_id}/title.md"
    content = fetch_gitea_content(path)
    return content.strip() if content else None

def fetch_article_subtitle(manual_name, article_id):
    """Fetch article subtitle (sub-title.md) from Gitea."""
    path = f"{manual_name}/{article_id}/sub-title.md"
    content = fetch_gitea_content(path)
    return content.strip() if content else None


# --- Notion Helpers ---

def find_page_by_title(title):
    """Find a Notion page by title, using cache first. Searches globally."""
    if not notion or not title: return None
    cache_key = f"title:{title}"
    if cache_key in page_cache:
        return page_cache[cache_key]

    logger.debug(f"API Search for page title: '{title}'")
    query = title[:100]

    try:
        response = notion.search(query=query, filter={"property": "object", "value": "page"})
        results = response.get("results", [])
        for page in results:
            page_props = page.get("properties", {})
            if "title" in page_props:
                page_title_list = page_props["title"].get("title", [])
                if page_title_list:
                    title_text = page_title_list[0].get("plain_text", "")
                    if title_text.lower() == title.lower():
                        page_id = page.get("id")
                        logger.info(f"Found existing page '{title}' via API: {page_id}")
                        page_cache[cache_key] = page_id
                        return page_id
        logger.debug(f"Page '{title}' not found via API search.")
        page_cache[cache_key] = None
        return None
    except Exception as e:
        logger.error(f"Error searching for page '{title}': {getattr(e, 'body', str(e))}")
        return None

def create_toggle(parent_id, title, level=1, is_heading=False):
    """Create a toggle block with specified title and heading level."""
    if not notion: return None
    logger.debug(f"Creating toggle: '{title}' under parent: {parent_id}")
    try:
        block_type = "toggle"
        toggle_data = {"rich_text": [{"type": "text", "text": {"content": title}}], "color": "default"}
        if level == 1 or is_heading:
             block_type = "heading_1"; toggle_data["is_toggleable"] = True; toggle_data.pop("color", None)
             block_data = {"heading_1": toggle_data}
        else: block_data = {"toggle": toggle_data}

        response = notion.blocks.children.append(block_id=parent_id, children=[{"type": block_type, **block_data}])
        results = response.get("results")
        if results and results[0] and results[0].get("id"):
            toggle_id = results[0].get("id")
            logger.info(f"Created level {level} toggle: '{title}' ({toggle_id})")
            return toggle_id
        logger.warning(f"Toggle creation for '{title}' succeeded but no ID found in response.")
        return None # Or return a default/error indicator
    except Exception as e:
        logger.error(f"Error creating toggle '{title}' under {parent_id}: {getattr(e, 'body', str(e))}")
        return None

def add_page_link_to_toggle(parent_id, title, page_id, is_child=False, indent_level=0):
    """Add a link to a page in the visual TOC structure (within a toggle)."""
    if not notion: return False
    logger.debug(f"Adding page link '{title}' ({page_id}) to visual TOC under {parent_id}")
    try:
        prefix = "📄 "
        if is_child:
            prefix = "    " * indent_level + ("→ " if indent_level == 1 else ("○ " if indent_level == 2 else "• "))
        notion.blocks.children.append(
            block_id=parent_id,
            children=[{"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": prefix}},
                {"type": "text", "text": {"content": title, "link": {"url": f"https://www.notion.so/{page_id.replace('-', '')}"}}, "annotations": {"bold": True, "color": "blue"}}
            ]}}]
        )
        return True
    except Exception as e:
        logger.error(f"Error creating page link for '{title}' in visual TOC under {parent_id}: {getattr(e, 'body', str(e))}")
        return False

# --- Advanced Formatting & Parsing ---

def parse_rich_text(text):
    """Parse markdown text to create Notion's rich text objects with formatting, including bold, italic, and links, even inside lists."""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return [{"type": "text", "text": {"content": ""}}]

    # Patterns
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    bold_pattern = r'\*\*([^*]+)\*\*'
    italic_pattern = r'\*([^*]+)\*'
    underscore_italic_pattern = r'(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)'
    footnote_pattern = r'\[\^(\d+)\]'

    # Recursive function to parse formatting
    def parse_segment(segment):
        # Links (outermost)
        parts = []
        last_end = 0
        for m in re.finditer(link_pattern, segment):
            start, end = m.span()
            if start > last_end:
                parts.extend(parse_bold_italic(segment[last_end:start]))
            link_text = m.group(1)
            link_url = m.group(2)
            # Recursively parse link text for formatting
            link_rich = parse_bold_italic(link_text)
            # Try to resolve internal link
            article_id = extract_article_id_from_link(link_url)
            notion_page_id = find_or_create_page_id_from_article_id(article_id, link_text) if article_id else None
            final_url = f"https://www.notion.so/{notion_page_id.replace('-', '')}" if notion_page_id else link_url
            for part in link_rich:
                part["text"]["link"] = {"url": final_url}
                if notion_page_id:
                    if "annotations" not in part:
                        part["annotations"] = {}
                    part["annotations"]["color"] = "blue"
            parts.extend(link_rich)
            last_end = end
        if last_end < len(segment):
            parts.extend(parse_bold_italic(segment[last_end:]))
        return parts

    def parse_bold_italic(segment):
        # Bold
        def bold_repl(m):
            return f"\0BOLD{m.group(1)}\0"
        segment = re.sub(bold_pattern, bold_repl, segment)
        # Italic (asterisk)
        def italic_repl(m):
            return f"\0ITALIC{m.group(1)}\0"
        segment = re.sub(italic_pattern, italic_repl, segment)
        # Italic (underscore)
        segment = re.sub(underscore_italic_pattern, italic_repl, segment)
        # Footnote (superscript)
        def footnote_repl(m):
            num = m.group(1)
            superscript_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
            return ''.join(superscript_map.get(c, c) for c in num)
        segment = re.sub(footnote_pattern, footnote_repl, segment)
        # Now split and build rich text
        parts = []
        tokens = re.split(r'(\0BOLD[^\0]+\0|\0ITALIC[^\0]+\0)', segment)
        for token in tokens:
            if not token:
                continue
            if token.startswith("\0BOLD"):
                content = token[5:-1] if token.endswith("\0") else token[5:]
                parts.append({"type": "text", "text": {"content": content}, "annotations": {"bold": True}})
            elif token.startswith("\0ITALIC"):
                content = token[7:-1] if token.endswith("\0") else token[7:]
                parts.append({"type": "text", "text": {"content": content}, "annotations": {"italic": True}})
            else:
                parts.append({"type": "text", "text": {"content": token}})
        return parts

    return parse_segment(text)


def convert_markdown_to_notion_blocks(markdown_content):
    """Convert markdown content to Notion blocks with nesting for lists."""
    if not notion or markdown_content is None:
        return []
    text = markdown_content
    # Convert HTML line breaks to paragraph breaks
    text = text.replace('<br>', '\n\n').replace('<br/>', '\n\n')
    # Unescape literal brackets \[ and \]
    text = text.replace('\\[', '[').replace('\\]', ']')
    # Convert HTML <sup> tags to unicode superscript (numbers, bracketed notes, combined cases)
    superscript_map = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    def sup_full_repl(m):
        content = m.group(1).strip()
        # Combined numeric and bracket footnote: e.g. '16 [1]'
        cm = re.match(r'^(?P<num>\d+)\s*\[\s*(?P<foot>\d+)\s*\]$', content)
        if cm:
            num_sup = ''.join(superscript_map.get(c, c) for c in cm.group('num'))
            foot_sup = ''.join(superscript_map.get(c, c) for c in cm.group('foot'))
            return f"{num_sup}⁽{foot_sup}⁾"
        # Bracket-only footnote: e.g. '[1]'
        bm = re.match(r'^\[\s*(\d+)\s*\]$', content)
        if bm:
            foot_sup = ''.join(superscript_map.get(c, c) for c in bm.group(1))
            return f"⁽{foot_sup}⁾"
        # Numeric superscript: e.g. '16'
        nm = re.match(r'^(\d+)$', content)
        if nm:
            return ''.join(superscript_map.get(c, c) for c in nm.group(1))
        # Fallback: convert any digits
        return ''.join(superscript_map.get(c, c) for c in content)
    text = re.sub(r'<sup>(.*?)</sup>', sup_full_repl, text)
    # Now proceed with cleaned text
    lines = text.splitlines()
    if not lines:
        return []
    # Initialize footnotes storage
    footnotes = {}
    blocks = []
    list_stack = []
    i = 0
    while i < len(lines):
        original_line = lines[i]; line = original_line.strip()

        if not line: # Handle blank lines and list context
            is_list_cont = False
            if list_stack and i + 1 < len(lines):
                 next_indent = len(lines[i+1]) - len(lines[i+1].lstrip())
                 next_line_strip = lines[i+1].strip()
                 is_list = re.match(r'^\d+\.\s', next_line_strip) or next_line_strip.startswith(('* ', '- '))
                 if is_list and next_indent >= list_stack[-1]['indent']: is_list_cont = True
            if not is_list_cont: list_stack = []
            i += 1; continue

        current_indent = len(original_line) - len(original_line.lstrip())

        # --- Handle Non-List Blocks ---
        matched_non_list = False
        if line.startswith('#'):
            level = line.count('#', 0, 5); heading_level = min(level, 3)
            blocks.append({"object": "block", "type": f"heading_{heading_level}", f"heading_{heading_level}": {"rich_text": parse_rich_text(line[level:].strip())}})
            matched_non_list = True
        elif line == '>':
            # Empty blockquote line: use a quote block with a single space
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": " "}}],
                    "children": []
                }
            })
            i += 1; list_stack = []; continue
        elif line.startswith('> '):
            # Handle nested blockquotes with content
            quote_blocks, new_i = process_nested_blockquotes(lines, i)
            blocks.extend(quote_blocks)
            i = new_i; list_stack = []; continue
        elif line.startswith('```'):
            lang = line[3:].strip(); code = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'): code.append(lines[i]); i += 1
            blocks.append({"object": "block", "type": "code", "code": {"rich_text": [{"type": "text", "text": {"content": "\n".join(code)}}], "language": lang or "plain text"}})
            matched_non_list = True
        if matched_non_list: list_stack = []; i += 1; continue

        # --- Handle List Items ---
        ordered_m = re.match(r'^(\d+)\.\s+(.*)', line)
        unordered_m = re.match(r'^([*\\-])\s+(.*)', line)
        if ordered_m or unordered_m:
            ltype = 'numbered' if ordered_m else 'bulleted'
            content = ordered_m.group(2) if ordered_m else unordered_m.group(2)
            while list_stack and list_stack[-1]['indent'] >= current_indent: list_stack.pop()
            item = {"object": "block", "type": f"{ltype}_list_item", f"{ltype}_list_item": {"rich_text": parse_rich_text(content), "children": []}}
            if list_stack and list_stack[-1]['indent'] < current_indent:
                parent_block = list_stack[-1]['block']; parent_type = list_stack[-1]['type']
                parent_block[f"{parent_type}_list_item"]['children'].append(item)
            else: blocks.append(item)
            list_stack.append({'type': ltype, 'indent': current_indent, 'block': item}); i += 1; continue

        # --- Handle Text Continuation within Lists ---
        elif list_stack and current_indent >= list_stack[-1]['indent']:
             target_block = list_stack[-1]['block']; target_type = list_stack[-1]['type']
             if target_block:
                 existing_rich = target_block[f"{target_type}_list_item"]["rich_text"]
                 existing_text = "".join(t.get("text", {}).get("content", "") for t in existing_rich if t.get("type") == "text")
                 new_content = existing_text.rstrip() + " " + line
                 target_block[f"{target_type}_list_item"]["rich_text"] = parse_rich_text(new_content)
                 i += 1; continue
             else: logger.warning("List continuation failed: stack invalid.")

        # --- Default to Paragraph ---
        list_stack = [] # Terminate list if none of above matched
        para_lines = [line]; next_i = i + 1
        while (next_i < len(lines) and lines[next_i].strip() and
               not lines[next_i].strip().startswith(('#', '>', '*', '-')) and
               not re.match(r'^\d+\.\s', lines[next_i].strip()) and
               not lines[next_i].startswith('```')):
            para_lines.append(lines[next_i].strip()); next_i += 1
        blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": parse_rich_text(" ".join(para_lines))}})
        i = next_i; continue

    # --- Add Footnotes ---
    if footnotes:
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "Footnotes"}}]} })
        for num, text in sorted(footnotes.items(), key=lambda item: int(item[0])):
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": parse_rich_text(f"[{num}] {text}")}})

    return blocks


def process_nested_blockquotes(lines, start_index):
    """Process consecutive blockquote lines into nested quote block dicts and return them with the next index."""
    blocks = []
    level_groups = []  # List of (level, lines)
    current_level = 0
    current_lines = []
    i = start_index

    # First pass: group lines by markdown nesting level (counting all '>' characters)
    while i < len(lines) and lines[i].strip().startswith('>'):
        line = lines[i].strip()
        # Count '>' characters ignoring spaces
        level = 0
        for char in line:
            if char == '>':
                level += 1
            elif char.isspace():
                continue
            else:
                break

        # Remove exactly 'level' '>' characters to get content
        content = line
        for _ in range(level):
            if content.startswith('>'):
                content = content[1:].lstrip()

        # When level changes, store the previous group
        if level != current_level and current_lines:
            level_groups.append((current_level, current_lines))
            current_lines = []
            current_level = level

        # Add content line (including blanks at first of group)
        if content or not current_lines:
            current_lines.append(content)

        i += 1

    # Add any remaining group
    if current_lines:
        level_groups.append((current_level, current_lines))

    # Second pass: build nested quote blocks
    stack = []  # stack[level-1] = block at that level
    for level, group_lines in level_groups:
        # Skip if all lines blank
        if not any(l.strip() for l in group_lines):
            continue
        # Clean any <sup> HTML tags to unicode superscript in quote content
        quote_content_raw = '\n'.join(group_lines)
        # Combined numeric and bracket: 16 [1] -> ¹⁶⁽¹⁾
        quote_content = re.sub(
            r'<sup>\s*(\d+)\s*\[\s*(\d+)\s*\]\s*</sup>',
            lambda m: f"{''.join({'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}.get(c, c) for c in m.group(1))}⁽{''.join({'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}.get(c, c) for c in m.group(2))}⁾",
            quote_content_raw
        )
        # Bracketed only: [1] -> ⁽¹⁾
        quote_content = re.sub(
            r'<sup>\s*\[\s*(\d+)\s*\]\s*</sup>',
            lambda m: f"⁽{''.join({'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}.get(c, c) for c in m.group(1))}⁾",
            quote_content
        )
        # Plain numeric: 16 -> ¹⁶
        quote_content = re.sub(
            r'<sup>\s*(\d+)\s*</sup>',
            lambda m: ''.join({'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}.get(c, c) for c in m.group(1)),
            quote_content
        )
        block = {
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": parse_rich_text(quote_content), "children": []}
        }
        if level > 1 and len(stack) >= level-1:
            parent = stack[level-2]
            parent['quote']['children'].append(block)
        else:
            blocks.append(block)
        # Update stack for this level
        stack = stack[:level-1] + [block]

    return blocks, i


def extract_article_id_from_link(link_url):
    """Extract article ID (slug) from various internal link formats."""
    if not link_url or not isinstance(link_url, str): return None
    # Regex updated for more robustness: optional '../', manual name capture, slug capture
    # Handles: ../slug/, ../slug/01.md, /manual/slug/, /manual/slug/01.md
    match = re.search(r'(?:\.\./|/)(?:intro|process|checking|translate)/([^/]+)(?:/01\.md|/)?$', link_url)
    if match:
        return match.group(1)
    # Fallback for just ../slug/ or ../slug/01.md without manual name (less reliable)
    relative_match = re.search(r'\.\./([^/]+)(?:/01\.md|/)?$', link_url)
    if relative_match:
        return relative_match.group(1)
    return None


def find_or_create_page_id_from_article_id(article_id, link_text=""):
    """Find Notion page ID from cache using article_id or title (link_text). Does NOT create."""
    if not article_id: return None
    cache_key_id = f"id:{article_id}"
    if cache_key_id in page_cache: return page_cache[cache_key_id]

    if link_text:
         cache_key_title_exact = f"title:{link_text}"
         if cache_key_title_exact in page_cache: return page_cache[cache_key_title_exact]
         normalized_link_text = re.sub(r'[^a-z0-9]', '', link_text.lower())
         if normalized_link_text:
            for key, page_id in page_cache.items():
                 if key.startswith("title:"):
                      normalized_cached = re.sub(r'[^a-z0-9]', '', key[len("title:"):].lower())
                      if normalized_cached == normalized_link_text:
                           logger.debug(f"Resolved link via fuzzy title: '{link_text}' -> '{key[len('title:'):]}' (ID: {page_id})")
                           return page_id

    logger.warning(f"Link resolve: Cache miss for article_id='{article_id}', link_text='{link_text}'.")
    return None


# --- Callout Generation ---
def create_dependency_callout(related_articles, id_title_map):
    """Create a Notion callout block for dependencies or recommendations."""
    if not notion or not related_articles: return None
    rich_text = [{"type": "text", "text": {"content": "Related: "}}]
    added_links = 0
    for i, article_id in enumerate(related_articles):
        page_id = find_or_create_page_id_from_article_id(article_id)
        title = id_title_map_global.get(article_id, article_id) # Use global map
        if i > 0: rich_text.append({"type": "text", "text": {"content": " | "}})
        if page_id:
            rich_text.append({"type": "text", "text": {"content": title, "link": {"url": f"https://www.notion.so/{page_id.replace('-', '')}"}}, "annotations": {"color": "gray"}})
            added_links += 1
        else: rich_text.append({"type": "text", "text": {"content": title}, "annotations": {"color": "gray", "italic": True}})
    return {"object": "block", "type": "callout", "callout": {"rich_text": rich_text, "icon": {"type": "emoji", "emoji": "🔗"}, "color": "gray_background"}} if added_links > 0 else None


# --- NEW HELPER FUNCTION ---
def append_blocks_recursive(parent_id, blocks_data):
    """Appends blocks (potentially nested) to Notion recursively."""
    if not notion or not parent_id or not blocks_data:
        return

    # Notion API has a limit of 100 blocks per append call
    for i in range(0, len(blocks_data), 100):
        batch_data = blocks_data[i:i+100]
        blocks_to_append = []
        children_to_process_later = {} # Store children: {index_in_batch: children_list}

        # Prepare batch for API call, separating children
        for idx, block_dict in enumerate(batch_data):
            block_copy = block_dict.copy() # Work on a copy
            children = None
            block_type = block_copy.get("type")
            # Check blocks that support children and extract them
            if block_type == "quote" and "children" in block_copy.get("quote", {}):
                children = block_copy["quote"].pop("children", []) # Remove children for API call
            elif block_type == "toggle" and "children" in block_copy.get("toggle", {}):
                 children = block_copy["toggle"].pop("children", [])
            elif block_type == "numbered_list_item" and "children" in block_copy.get("numbered_list_item", {}):
                 children = block_copy["numbered_list_item"].pop("children", [])
            elif block_type == "bulleted_list_item" and "children" in block_copy.get("bulleted_list_item", {}):
                 children = block_copy["bulleted_list_item"].pop("children", [])
            # Add other block types supporting children if needed (e.g., synced_block?)
            
            blocks_to_append.append(block_copy)
            if children:
                children_to_process_later[idx] = children

        if not blocks_to_append:
            continue

        # Append the batch of blocks (without children)
        try:
            response = notion.blocks.children.append(block_id=parent_id, children=blocks_to_append)
            results = response.get("results", [])
            logger.debug(f"Appended batch of {len(results)} blocks under {parent_id}.")
            
            # Process children recursively using the returned block IDs
            if results and len(results) == len(blocks_to_append):
                 for idx, created_block in enumerate(results):
                     if idx in children_to_process_later:
                         child_block_id = created_block.get("id")
                         children_list = children_to_process_later[idx]
                         if child_block_id and children_list:
                             logger.debug(f"Recursively appending {len(children_list)} children under new block {child_block_id}")
                             append_blocks_recursive(child_block_id, children_list) # Recursive call
                             time.sleep(0.35) # Add delay after recursive call potentially makes many API calls
            elif results:
                 logger.warning(f"Mismatch in appended blocks count vs requested. Requested: {len(blocks_to_append)}, Got: {len(results)}. Child appending might be broken.")
            else:
                 logger.error(f"Failed to append batch under {parent_id}. Response: {response}")
                 return # Stop if batch fails

            time.sleep(0.5) # Delay between batches

        except Exception as e:
            logger.error(f"Error appending block batch under {parent_id}: {getattr(e, 'body', str(e))}")
            # Optionally add retry logic here
            return # Stop processing further batches for this parent if one fails

# --- Page Creation (Updated for Callouts & Multi-Manual) ---

def create_article_page(manual_name, title, article_id, parent_page_id, config_data=None):
    """Create an article page, populate with content, and add dependency callouts."""
    if not notion: return None
    logger.info(f"Attempting to create page: '{title}' ({manual_name}/{article_id}) -> Parent: {parent_page_id}")
    if not parent_page_id: logger.error(f"Invalid parent_page_id for '{title}'."); return None

    page_props = {"title": {"title": [{"type": "text", "text": {"content": title}}]}}
    content = fetch_article_content(manual_name, article_id)
    subtitle = fetch_article_subtitle(manual_name, article_id)
    if content is None: logger.error(f"Failed to fetch content for {manual_name}/{article_id}. Skipping page creation."); return None # Skip if no content

    # --- Generate block structures (potentially nested) ---
    content_block_dicts = convert_markdown_to_notion_blocks(content or "")
    
    # --- Prepare initial blocks (headings, subtitle, callouts) as dictionaries ---
    initial_block_dicts = [] 
    # Add H1 only if content doesn't start with one
    if not (content_block_dicts and content_block_dicts[0].get("type") == "heading_1"):
         initial_block_dicts.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": parse_rich_text(title)}})
    # Add Subtitle Callout
    if subtitle:
        clean_subtitle = subtitle.strip().strip('_')
        # Create callout with prefix text plain and subtitle italicized
        initial_block_dicts.append({
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "This article answers the question: "}},
                    {"type": "text", "text": {"content": clean_subtitle}, "annotations": {"italic": True}}
                ],
                "icon": {"type": "emoji", "emoji": "❓"}, "color": "gray_background"
            }
        })
    # Prepare Dependency/Recommendation Callout dictionary
    related = []
    if config_data and article_id in config_data:
        related.extend(config_data[article_id].get('dependencies', [])); related.extend(config_data[article_id].get('recommended', []))
    callout_block_dict = create_dependency_callout(list(set(related)), id_title_map_global) if related else None 
    divider_block_dict = {"object": "block", "type": "divider", "divider": {}} if callout_block_dict else None

    # --- Combine all block dictionaries in order ---
    final_block_dicts = initial_block_dicts + content_block_dicts
    if divider_block_dict: final_block_dicts.append(divider_block_dict)
    if callout_block_dict: final_block_dicts.append(callout_block_dict)

    page_id = None
    try:
        # --- Create page with ONLY properties, NO children initially ---
        page_data = {"parent": {"page_id": parent_page_id}, "properties": page_props}
        response = notion.pages.create(**page_data)
        page_id = response.get("id")
        if not page_id: logger.error(f"Page create API call failed for '{title}'. Response: {response}"); return None
        logger.info(f"Created empty page: '{title}' ({manual_name}/{article_id}) ID: {page_id}")
        
        # --- Append all blocks recursively ---    
        if final_block_dicts:
             logger.info(f"Appending {len(final_block_dicts)} top-level blocks (with nesting) to {page_id}...")
             append_blocks_recursive(page_id, final_block_dicts)
        else:
             logger.info(f"No content blocks generated for page '{title}' ({page_id}). Page remains empty.")

    except Exception as create_err:
         logger.error(f"Error during page creation or block appending for '{title}': {getattr(create_err, 'body', str(create_err))}", exc_info=False)
         # Handle fallback: If page_id exists, it was created but appending failed.
         # If page_id is None, initial creation failed.
         if not page_id: # Fallback only if page wasn't created at all
              try:
                   logger.warning(f"Attempting fallback page creation (no content) for '{title}'")
                   response = notion.pages.create(parent={"page_id": parent_page_id}, properties=page_props)
                   page_id = response.get("id")
                   if page_id: logger.warning(f"Fallback created page '{title}' (ID: {page_id}) without content due to previous error.")
                   else: logger.error(f"Fallback page creation ALSO failed for '{title}'."); return None
              except Exception as simple_err: logger.error(f"Fallback page creation failed for '{title}': {getattr(simple_err, 'body', str(simple_err))}"); return None
         # If page_id exists but append failed, we just proceed to caching the partially created page ID.

    # --- Update Cache & URL Map --- 
    if page_id:
        cache_key_title = f"title:{title}"; cache_key_id = f"id:{article_id}"
        page_cache[cache_key_title] = page_id; page_cache[cache_key_id] = page_id
        map_url_to_page_id(get_gitea_article_url(manual_name, article_id), page_id)
        map_url_to_page_id(f"../{article_id}/", page_id)
        map_url_to_page_id(f"../{article_id}/01.md", page_id)
        save_cache_to_file() # Save periodically
        return page_id
    return None


def create_section_page(manual_name, title, parent_page_id):
    """Create a new section page (container in hierarchy)."""
    if not notion: return None
    logger.info(f"Creating section page '{title}' ({manual_name}) under parent {parent_page_id}")
    try:
        if not parent_page_id: logger.error(f"Invalid parent_page_id for section '{title}'."); return None
        page_data = {
            "parent": {"page_id": parent_page_id},
            "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
            "children": [{"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": title}}]}}]
        }
        response = notion.pages.create(**page_data)
        page_id = response.get("id")
        if page_id:
             logger.info(f"Created section page: '{title}' ({manual_name}) ID: {page_id}")
             page_cache[f"title:{title}"] = page_id # Cache by title
             save_cache_to_file()
             return page_id
        else: logger.error(f"Section page creation failed for '{title}', no ID."); return None
    except Exception as e: logger.error(f"Error creating section page '{title}': {getattr(e, 'body', str(e))}"); return None

# --- TOC Building Logic (Multi-Manual) ---

def build_manual_section(manual_name, manual_toc_data, manual_config_data,
                         visual_toc_parent_id, hierarchy_parent_page_id,
                         level=1, parent_section_title="",
                         delay_seconds=0.5, indent_level=0, process_content=True, skip_existing=False, skip_until_section=None):
    """Recursively build a section of a specific manual's TOC and page structure."""
    if not notion or not manual_toc_data: return
    title = manual_toc_data.get("title", "Untitled Section")
    article_id_direct = manual_toc_data.get("link") # Link directly on this item
    subsections = manual_toc_data.get("sections", [])
    logger.debug(f"Processing: {manual_name} L{level} I{indent_level} - '{title}' (Direct Link: {article_id_direct})")

    # --- Check for the specific pattern: Container whose first child is an identically named article ---
    is_special_pattern = False
    article_id_from_child = None
    child_article_data = None
    if not article_id_direct and subsections: # Only if this item is a container without its own direct link
        first_child = subsections[0]
        if first_child.get("title") == title and first_child.get("link") and not first_child.get("sections"):
            # Pattern matched! The container's content comes from its first child.
            is_special_pattern = True
            article_id_from_child = first_child.get("link")
            child_article_data = first_child # Store for potential later use if needed
            logger.info(f"Detected special pattern for '{title}'. Using child article '{article_id_from_child}' for content.")
            # We will process subsections[1:] later.
    # --- End pattern check ---

    if skip_until_section and title != skip_until_section:
        logger.debug(f"Skipping section '{title}' until we reach '{skip_until_section}'")
        if subsections:
            # If we are skipping, we need to check *all* subsections, even if special pattern matched.
            sections_to_check = subsections
            for sub_data in sections_to_check:
                 build_manual_section(
                     manual_name, sub_data, manual_config_data,
                     visual_toc_parent_id, hierarchy_parent_page_id, # Pass original hierarchy parent
                     level + 1, title, delay_seconds, indent_level + 1,
                     process_content, skip_existing, skip_until_section
                 )
        return

    if title == skip_until_section:
        skip_until_section = None # Found the target, stop skipping

    # Determine the primary article ID and if this node represents an article page
    article_id = article_id_from_child if is_special_pattern else article_id_direct
    is_article = bool(article_id) # True if direct link OR special pattern matched
    is_container = bool(subsections) # Still a container if it has sections list
    current_page_id = None

    # --- Hierarchy Page ---
    if (is_article or is_container) and process_content: # Page needed if it's an article OR a container
        cache_key_title = f"title:{title}"; cache_key_id = f"id:{article_id}" if article_id else None
        existing_page_id = page_cache.get(cache_key_title) or (cache_key_id and page_cache.get(cache_key_id))

        if is_article and article_id and not id_title_map_global.get(article_id):
             id_title_map_global[article_id] = title

        if existing_page_id:
            current_page_id = existing_page_id
            logger.info(f"Cache hit: Page '{title}' ({manual_name}) ID: {current_page_id}")
            if skip_existing and is_article: logger.info(f"Skipping content creation for existing article '{title}'.")
            if is_article and article_id and article_id not in id_title_map_global: id_title_map_global[article_id] = title
        else:
            existing_page_id_api = find_page_by_title(title)
            if existing_page_id_api:
                current_page_id = existing_page_id_api
                logger.info(f"Found existing page '{title}' via API: {current_page_id}")
                page_cache[cache_key_title] = current_page_id
                if cache_key_id: page_cache[cache_key_id] = current_page_id
                if skip_existing and is_article: logger.info(f"Skipping content creation for existing article '{title}'.")
                if is_article and article_id and article_id not in id_title_map_global: id_title_map_global[article_id] = title
            elif not skip_existing:
                logger.info(f"Creating hierarchy page for '{title}' ({manual_name}) under {hierarchy_parent_page_id}")
                page_title_to_create = id_title_map_global.get(article_id, title)

                # --- Page Creation Logic ---
                if is_article: # Use create_article_page if we have an article_id (direct or from child)
                    current_page_id = create_article_page(manual_name, page_title_to_create, article_id, hierarchy_parent_page_id, manual_config_data)
                    if not current_page_id and is_container: # Fallback ONLY if article fails AND it was meant to be a container
                         logger.warning(f"Falling back to section page creation for container '{title}' due to article creation failure.")
                         current_page_id = create_section_page(manual_name, title, hierarchy_parent_page_id)
                elif is_container: # Only a container, no direct or child article link
                    current_page_id = create_section_page(manual_name, title, hierarchy_parent_page_id)
                # --- End Page Creation ---

                if not current_page_id: logger.error(f"Failed hierarchy page creation for '{title}'.")
                elif is_article: # Update map if article page was potentially created
                     try: # Add try-except for retrieve
                         actual_page_data = notion.pages.retrieve(page_id=current_page_id)
                         actual_title_list = actual_page_data.get("properties", {}).get("title", {}).get("title", [])
                         actual_title = actual_title_list[0].get("plain_text", title) if actual_title_list else title
                         id_title_map_global[article_id] = actual_title
                         logger.info(f"Mapped article ID '{article_id}' to title '{actual_title}'")
                     except Exception as retrieve_err:
                          logger.error(f"Failed to retrieve page {current_page_id} after creation to confirm title: {retrieve_err}")
                          # Map anyway as a fallback
                          if article_id not in id_title_map_global: id_title_map_global[article_id] = title


    # --- Visual TOC Entry ---
    vis_parent = visual_toc_parent_id
    is_toggle = (level == 1 or title == "Just-in-Time Learning Modules")
    if vis_parent:
        display_title = id_title_map_global.get(article_id, title) if is_article else title # Use mapped title if available

        if is_toggle:
            toggle_id = create_toggle(vis_parent, display_title, level, is_heading=(level == 1))
            if toggle_id: vis_parent = toggle_id; time.sleep(delay_seconds)
            else: logger.error(f"Failed visual toggle creation for '{display_title}'."); vis_parent = None

        if vis_parent:
            if current_page_id:
                add_page_link_to_toggle(vis_parent, display_title, current_page_id, is_child=(not is_toggle), indent_level=indent_level)
                time.sleep(delay_seconds)
            # Handle placeholders/text blocks if needed (logic unchanged)
            elif is_container or (is_article and not process_content):
                 prefix = "    " * indent_level + ("→ " if indent_level == 1 else ("○ " if indent_level == 2 else "• ")) if not is_toggle else "📄 "
                 try: notion.blocks.children.append(vis_parent, children=[{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"{prefix}{display_title}"}, "annotations": {"bold": True}}]}}]); time.sleep(delay_seconds)
                 except Exception as e: logger.error(f"Failed to add text block for '{display_title}': {getattr(e, 'body', str(e))}")
            elif is_article and process_content:
                 logger.warning(f"Adding placeholder text for failed article '{display_title}' in visual TOC.")
                 prefix = "    " * indent_level + ("→ " if indent_level == 1 else ("○ " if indent_level == 2 else "• ")) if not is_toggle else "📄 "
                 try: notion.blocks.children.append(vis_parent, children=[{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"{prefix}{display_title} (Content Failed)"}, "annotations": {"color": "red"}}]}}]); time.sleep(delay_seconds)
                 except Exception as e: logger.error(f"Failed to add placeholder text block for '{display_title}': {getattr(e, 'body', str(e))}")


    # --- Process Subsections ---
    if subsections:
         # If special pattern matched, skip the first child (already used for content)
         sections_to_process = subsections[1:] if is_special_pattern else subsections
         
         # Use the created page (article or section) as the parent for subsections
         next_hier_parent = current_page_id if (current_page_id and process_content) else hierarchy_parent_page_id
         next_indent = indent_level + 1 if not is_toggle else 0 # Adjust indent based on whether current item was a toggle
         
         if not sections_to_process:
              logger.debug(f"No further subsections to process under '{title}' after handling special pattern or empty list.")
         
         for sub_data in sections_to_process:
             build_manual_section(
                 manual_name, sub_data, manual_config_data,
                 vis_parent, next_hier_parent, # Pass the created page ID as the hierarchy parent
                 level + 1, title, delay_seconds, next_indent,
                 process_content, skip_existing, skip_until_section
             )


# --- Post-Processing for Links ---

def update_page_links(page_id):
    """Update links within a single Notion page."""
    if not notion or not page_id: return False
    logger.debug(f"Starting link update for page: {page_id}")
    updated_count = 0
    try:
        all_blocks = [] # Fetch all blocks with pagination
        next_cursor = None
        while True:
            response = notion.blocks.children.list(block_id=page_id, start_cursor=next_cursor, page_size=100)
            results = response.get("results", []); all_blocks.extend(results)
            if not response.get("has_more") or not results: break
            next_cursor = response.get("next_cursor"); time.sleep(0.35)
        logger.debug(f"Fetched {len(all_blocks)} blocks for page {page_id}")

        for block in all_blocks: # Process each block
            block_id = block.get("id"); block_type = block.get("type")
            content_key = block_type; rich_text_list = []
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "toggle", "callout", "quote"]:
                 rich_text_list = block.get(content_key, {}).get("rich_text", [])
            if not rich_text_list: continue

            modified_rich_text = []; block_modified = False
            for text_obj in rich_text_list: # Process rich text parts
                link_info = text_obj.get("text", {}).get("link")
                if text_obj.get("type") == "text" and link_info and isinstance(link_info, dict):
                    link_url = link_info["url"]; original_url = link_url
                    notion_page_id = None
                    # Link resolution logic (check map, then try cache)
                    if original_url in url_to_page_id_map: notion_page_id = url_to_page_id_map[original_url]
                    else:
                         article_id = extract_article_id_from_link(original_url)
                         if article_id: notion_page_id = find_or_create_page_id_from_article_id(article_id, text_obj["text"]["content"])

                    if notion_page_id: # If resolved, update URL
                         new_url = f"https://www.notion.so/{notion_page_id.replace('-', '')}"
                         if new_url != original_url:
                              new_text_obj = text_obj.copy()
                              if "link" not in new_text_obj["text"]: new_text_obj["text"]["link"] = {} # Ensure link key exists
                              new_text_obj["text"]["link"]["url"] = new_url
                              if "annotations" not in new_text_obj: new_text_obj["annotations"] = {}
                              new_text_obj["annotations"]["color"] = "blue" # Style internal links
                              modified_rich_text.append(new_text_obj); block_modified = True; updated_count += 1
                         else: modified_rich_text.append(text_obj) # No change needed
                    else: # Keep original link if not resolved
                        if "git.door43.org" in original_url or original_url.startswith("../"):
                             logger.warning(f"Link resolve: Could not resolve internal link in block {block_id}: {original_url}")
                        modified_rich_text.append(text_obj)
                else: modified_rich_text.append(text_obj) # Not a link or no URL

            if block_modified: # Update block if links were changed
                try:
                    update_data = {content_key: {"rich_text": modified_rich_text}}
                    notion.blocks.update(block_id=block_id, **update_data)
                    logger.debug(f"Updated block {block_id} with new links."); time.sleep(0.4) # Rate limit
                except Exception as update_err: logger.error(f"Error updating block {block_id} (Type: {block_type}): {getattr(update_err, 'body', str(update_err))}")

        if updated_count > 0: logger.info(f"Updated {updated_count} links in page {page_id}")
        return updated_count > 0
    except Exception as e: logger.error(f"Error processing links for page {page_id}: {str(e)}", exc_info=True); return False


def process_all_pages_links():
    """Post-process all created pages to update internal links."""
    if not notion: return
    logger.info(f"Starting link update process for all cached pages...")
    processed_ids = set(); updated_pages = 0; error_pages = 0
    all_ids = list(set(v for v in page_cache.values() if v and isinstance(v, str) and '-' in v)) # Get unique page IDs
    logger.info(f"Found {len(all_ids)} unique page IDs in cache to process.")

    for page_id in all_ids:
        if page_id not in processed_ids:
            processed_ids.add(page_id); logger.info(f"Processing links for page: {page_id}")
            try:
                if update_page_links(page_id): updated_pages += 1
                time.sleep(0.4) # Delay between pages
            except Exception as page_err: logger.error(f"Critical error during link update for {page_id}: {page_err}", exc_info=True); error_pages += 1
    logger.info(f"Link update complete. Updated links in {updated_pages} pages. Errors on {error_pages} pages.")

# --- Utility Functions ---

def get_gitea_article_url(manual_name, article_id):
    """Construct the full Gitea URL for an article's 01.md file."""
    return f"https://git.door43.org/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/src/branch/master/{manual_name}/{article_id}/01.md"

def map_url_to_page_id(url, page_id):
    """Add mappings from various URL formats to a Notion page ID."""
    if not url or not page_id: return
    urls_to_map = set([url.strip()])
    u = url.strip()
    # Add variations for relative and absolute paths
    if u.startswith("../"):
        slug_match = re.match(r'\.\./([^/]+)', u)
        if slug_match: slug = slug_match.group(1); urls_to_map.add(f"../{slug}/"); urls_to_map.add(f"../{slug}/01.md")
    gitea_base = f"https://git.door43.org/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/src/branch/master/"
    if u.startswith(gitea_base):
        path_part = u[len(gitea_base):]; path_match = re.match(r'([^/]+)/([^/]+)', path_part)
        if path_match: manual, slug = path_match.groups(); urls_to_map.add(f"{gitea_base}{manual}/{slug}/"); urls_to_map.add(f"{gitea_base}{manual}/{slug}/01.md")
    # Add http/https stripping variations
    stripped_urls = set()
    for u_var in urls_to_map:
        if u_var.startswith("https://"): stripped_urls.add(u_var[8:])
        elif u_var.startswith("http://"): stripped_urls.add(u_var[7:])
    urls_to_map.update(stripped_urls)
    # Update global map
    for norm_url in urls_to_map:
        if norm_url not in url_to_page_id_map: url_to_page_id_map[norm_url] = page_id


def save_cache_to_file(filename="page_cache.json"):
    """Save all caches to a JSON file."""
    try:
        clean_page = {str(k): str(v) for k, v in page_cache.items() if v and isinstance(k, str) and isinstance(v, str)}
        clean_url = {str(k): str(v) for k, v in url_to_page_id_map.items() if v and isinstance(k, str) and isinstance(v, str)}
        clean_config = {str(k): v for k, v in config_cache.items() if v} # Config data can be complex dicts/lists
        clean_id_title = {str(k): str(v) for k, v in id_title_map_global.items() if v and isinstance(k, str) and isinstance(v, str)}
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({"page_cache": clean_page, "url_map": clean_url, "config_cache": clean_config, "id_title_map": clean_id_title}, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved caches ({len(clean_page)} pages, {len(clean_url)} URLs, {len(clean_config)} configs, {len(clean_id_title)} titles) to {filename}")
    except Exception as e: logger.error(f"Error saving cache to {filename}: {str(e)}")

def load_cache_from_file(filename="page_cache.json"):
    """Load all caches from a JSON file."""
    global page_cache, url_to_page_id_map, config_cache, id_title_map_global
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f: data = json.load(f)
            page_cache = data.get("page_cache", {}); url_to_page_id_map = data.get("url_map", {}); config_cache = data.get("config_cache", {}); id_title_map_global = data.get("id_title_map", {})
            logger.info(f"Loaded caches ({len(page_cache)} pages, {len(url_to_page_id_map)} URLs, {len(config_cache)} configs, {len(id_title_map_global)} titles) from {filename}")
        else: logger.info(f"Cache file {filename} not found. Starting fresh."); page_cache, url_to_page_id_map, config_cache, id_title_map_global = {}, {}, {}, {}
    except (json.JSONDecodeError, Exception) as e: logger.error(f"Error loading cache from {filename}: {e}. Starting fresh."); page_cache, url_to_page_id_map, config_cache, id_title_map_global = {}, {}, {}, {}


# --- Main Execution Block (for direct testing) ---
if __name__ == "__main__":
    print("build_toc_structure.py executed directly (intended for import by import_all.py)")
    # Add specific tests here, e.g.:
    # load_cache_from_file()
    # test_md = "* [Link1](../figs-activepassive/01.md) and **bold**."
    # result = parse_rich_text(test_md)
    # print(json.dumps(result, indent=2))
    # update_page_links("YOUR_TEST_PAGE_ID") # Replace with a valid Notion page ID for testing