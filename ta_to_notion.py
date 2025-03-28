import os
import requests
import json
import re
import logging
import argparse
from dotenv import load_dotenv
from notion_client import Client
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ta_to_notion.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
GITEA_API_KEY = os.getenv("GITEA_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

if not GITEA_API_KEY:
    logger.error("GITEA_API_KEY not found in .env file")
    exit(1)

if not NOTION_API_KEY:
    logger.error("NOTION_API_KEY not found in .env file")
    exit(1)

# Constants
GITEA_BASE_URL = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_BRANCH = "master"

# Notion parent page ID - Format properly for API
def format_notion_id(id_str):
    """Format a Notion ID to the correct UUID format."""
    # Check if ID already contains dashes in the right format
    if len(id_str) == 36 and id_str.count('-') == 4:
        return id_str
    
    # Remove any existing dashes
    id_str = id_str.replace('-', '')
    
    # Insert dashes in the standard UUID format
    if len(id_str) == 32:
        return f"{id_str[0:8]}-{id_str[8:12]}-{id_str[12:16]}-{id_str[16:20]}-{id_str[20:32]}"
    else:
        return id_str  # Return as is if we can't format it

# The page ID from the URL: Translation-Academy-WIP-1c372d5af2de80e08b11cd7748a1467d
# We need to extract and format the UUID part
RAW_NOTION_ID = "1c372d5af2de80e08b11cd7748a1467d"
NOTION_PARENT_PAGE_ID = format_notion_id(RAW_NOTION_ID)
logger.info(f"Using Notion page ID: {NOTION_PARENT_PAGE_ID}")

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def read_article_list(file_path):
    """Read the list of articles to import from a file."""
    try:
        with open(file_path, 'r') as f:
            articles = [line.strip() for line in f.readlines() if line.strip()]
        return articles
    except FileNotFoundError:
        logger.error(f"Article list file not found: {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error reading article list: {str(e)}")
        return []

def get_gitea_file_content(path):
    """Get the content of a file from Gitea."""
    url = f"{GITEA_BASE_URL}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/raw/{path}?ref={GITEA_BRANCH}"
    headers = {"Authorization": f"token {GITEA_API_KEY}"}
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.text
        else:
            logger.error(f"Error fetching {path}: HTTP {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"Request failed for {path}: {str(e)}")
        return None

def check_article_exists(title):
    """Check if an article with the given title already exists in Notion."""
    try:
        search_params = {
            "query": title,
            "filter": {
                "property": "object",
                "value": "page"
            }
        }
        
        results = notion.search(**search_params)
        
        for page in results.get("results", []):
            if "properties" in page and "title" in page["properties"]:
                page_title = page["properties"]["title"]["title"]
                if page_title and page_title[0]["plain_text"] == title:
                    return page["id"]
        
        return None
    except Exception as e:
        logger.error(f"Error checking if article exists: {str(e)}")
        return None

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
        
        # For level 2 blockquotes (> >), track them for later addition as children
        if level == 2 and blocks:
            # Remember to add this as a child of the previous block
            parent_index = len(blocks) - 1
            parent_child_relations.append((parent_index, block))
        else:
            blocks.append(block)
    
    return blocks, parent_child_relations, i

def create_notion_page(parent_id, title, subtitle, content, skip_existing=False):
    """Create a new page in Notion with the provided content."""
    # Check if page already exists
    if skip_existing:
        existing_id = check_article_exists(title)
        if existing_id:
            logger.info(f"Article '{title}' already exists with ID: {existing_id}")
            return existing_id
    
    # Convert markdown content to Notion blocks
    blocks, parent_child_relations = convert_markdown_to_notion_blocks(content)
    
    # Create the page
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
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": subtitle
                            }
                        }
                    ]
                }
            },
            *blocks
        ]
    }
    
    try:
        response = notion.pages.create(**page_data)
        logger.info(f"Successfully created page: {title}")
        
        # The response is a dictionary with the page details, including the ID
        if isinstance(response, dict) and 'id' in response:
            # Process any parent-child relationships for nested blockquotes
            if parent_child_relations:
                page_id = response['id']
                block_ids = []
                
                # First, get all block IDs from the page
                try:
                    page_blocks = notion.blocks.children.list(block_id=page_id)
                    # Skip the title block which is at index 0
                    block_ids = [block['id'] for block in page_blocks['results'][1:]]
                    logger.debug(f"Retrieved {len(block_ids)} block IDs from the page")
                    
                    # Now add child blocks to their parents
                    for parent_idx, child_block in parent_child_relations:
                        if parent_idx < len(block_ids):
                            parent_block_id = block_ids[parent_idx]
                            try:
                                notion.blocks.children.append(
                                    block_id=parent_block_id,
                                    children=[child_block]
                                )
                                logger.debug(f"Added child block to parent {parent_block_id}")
                            except Exception as e:
                                logger.error(f"Error adding child block: {str(e)}")
                except Exception as e:
                    logger.error(f"Error getting block IDs: {str(e)}")
            
            return response['id']
        else:
            logger.error(f"Unexpected response format: {type(response)}")
            logger.debug(f"Response: {response}")
            return None
    except Exception as e:
        logger.error(f"Error creating Notion page: {str(e)}")
        return None

def parse_rich_text(text):
    """Parse markdown text to create Notion's rich text objects with formatting."""
    rich_text = []
    
    # First, handle basic formatting (bold and italic)
    # Process bold formatting (**text**)
    bold_pattern = r'\*\*([^*]+)\*\*'
    # Process italic formatting (*text*)
    italic_pattern = r'\*([^*]+)\*'
    # Process footnote references ([^n])
    footnote_ref_pattern = r'\\\[\^(\d+)\\\]'
    
    # Handle links - find all [text](url) patterns
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

def convert_markdown_to_notion_blocks(markdown_content):
    """Convert markdown content to Notion blocks."""
    blocks = []
    parent_child_relations = []  # To track parent-child relationships
    
    # Split the content into lines
    lines = markdown_content.splitlines()
    
    # Process footnotes first to extract them
    footnotes = {}
    footnote_pattern = r'\[\^(\d+)\]:\s*(.*?)(?=\n\n|\n\[\^|$)'
    footnote_matches = re.finditer(footnote_pattern, markdown_content, re.DOTALL)
    for match in footnote_matches:
        footnote_num = match.group(1)
        footnote_text = match.group(2).strip()
        footnotes[footnote_num] = footnote_text
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check for headings
        if line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": parse_rich_text(line[2:])
                }
            })
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": parse_rich_text(line[3:])
                }
            })
        elif line.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": parse_rich_text(line[4:])
                }
            })
        elif line.startswith("#### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",  # Notion only has h1, h2, h3, so we use h3 for h4
                "heading_3": {
                    "rich_text": parse_rich_text(line[5:])
                }
            })
        
        # Check for blockquotes - handle nested quotes
        elif line.startswith("> "):
            # Check if this is a double blockquote (> >) that should be a child of the previous block
            is_double_blockquote = line.strip().startswith("> >")
            
            # If it's a double blockquote and we have a previous block, make it a child
            if is_double_blockquote and blocks:
                # Process just this blockquote line and any following at the same level
                quote_lines = []
                current_i = i
                
                while current_i < len(lines) and lines[current_i].strip().startswith("> >"):
                    # Remove both > characters and get content
                    content_line = lines[current_i].strip()
                    # Remove the first >
                    content_line = content_line[1:].lstrip()
                    # Remove the second >
                    content_line = content_line[1:].lstrip()
                    
                    quote_lines.append(content_line)
                    current_i += 1
                
                # Create a blockquote block
                quote_content = "\n".join(quote_lines)
                child_block = {
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": parse_rich_text(quote_content)
                    }
                }
                
                # Add this as a child of the previous block
                parent_index = len(blocks) - 1
                parent_child_relations.append((parent_index, child_block))
                
                # Advance i to after the last blockquote line
                i = current_i
                continue
            else:
                # Process blockquotes and collect parent-child relations
                quote_blocks, quote_relations, new_i = process_nested_blockquotes(lines, i)
                blocks.extend(quote_blocks)
                
                # Calculate parent indices relative to all blocks
                base_index = len(blocks) - len(quote_blocks)
                for parent_idx, child_block in quote_relations:
                    parent_child_relations.append((base_index + parent_idx, child_block))
                
                # Advance i to after the last blockquote line
                i = new_i
                
                continue  # Skip the increment at the end as we've already advanced i
        
        # Handle lines with just a ">" (isolated blockquote separator)
        elif line == ">":
            # Create a blockquote with just a space to avoid placeholder text
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": " "}}]
                }
            })
            i += 1
            continue
        
        # Check for unordered lists
        elif line.startswith("* ") or line.startswith("- "):
            list_items = []
            prefix_length = 2  # Length of "* " or "- "
            
            # Collect all consecutive list items
            while i < len(lines) and (lines[i].strip().startswith("* ") or lines[i].strip().startswith("- ")):
                list_content = lines[i].strip()[prefix_length:]
                list_items.append({
                    "rich_text": parse_rich_text(list_content)
                })
                i += 1
            
            # Create the bullet list block
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": list_items[0]
            })
            
            # Add remaining list items
            for item in list_items[1:]:
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": item
                })
            
            continue  # Skip the increment at the end as we've already advanced i
        
        # Check for ordered lists
        elif re.match(r'^\d+\.\s', line):
            list_items = []
            
            # Collect all consecutive list items
            while i < len(lines) and re.match(r'^\d+\.\s', lines[i].strip()):
                # Extract content after the number and period
                list_content = re.sub(r'^\d+\.\s', '', lines[i].strip())
                list_items.append({
                    "rich_text": parse_rich_text(list_content)
                })
                i += 1
            
            # Create the numbered list block
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": list_items[0]
            })
            
            # Add remaining list items
            for item in list_items[1:]:
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": item
                })
            
            continue  # Skip the increment at the end as we've already advanced i
        
        # Check for code blocks
        elif line.startswith("```"):
            code_language = line[3:].strip()
            code_lines = []
            i += 1
            
            # Collect all lines until the closing ```
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            
            # Create the code block
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                    "language": code_language if code_language else "plain text"
                }
            })
            
            # Skip the closing ```
            if i < len(lines):
                i += 1
            
            continue  # Skip the increment at the end as we've already advanced i
        
        # Check for footnote definitions
        elif re.match(r'\[\^(\d+)\]:', line):
            # Skip footnote definitions as we've already processed them
            i += 1
            continue
        
        # Default to paragraph
        else:
            # Check if this line starts a paragraph that spans multiple lines
            paragraph_lines = [line]
            next_i = i + 1
            
            # Collect lines until we hit an empty line or a special format
            while (next_i < len(lines) and 
                  lines[next_i].strip() and 
                  not lines[next_i].strip().startswith(("# ", "## ", "### ", "#### ", "> ", "* ", "- ", "```", "[^")) and
                  not re.match(r'^\d+\.\s', lines[next_i].strip())):
                paragraph_lines.append(lines[next_i].strip())
                next_i += 1
            
            # Join the paragraph lines
            paragraph_content = " ".join(paragraph_lines)
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(paragraph_content)
                }
            })
            
            # Update i to skip the lines we've processed
            i = next_i - 1
        
        i += 1
    
    # Add footnotes at the end if any exist
    if footnotes:
        # Add a divider before footnotes
        blocks.append({
            "object": "block",
            "type": "divider",
            "divider": {}
        })
        
        # Add heading for footnotes
        blocks.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "Footnotes"}}]
            }
        })
        
        # Add each footnote as a paragraph
        for num, text in footnotes.items():
            footnote_content = f"[{num}] {text}"
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(footnote_content)
                }
            })
    
    return blocks, parent_child_relations

def process_article(article_folder, skip_existing=False):
    """Process a single article by folder name."""
    base_path = f"translate/{article_folder}"
    
    # Get article components
    title_content = get_gitea_file_content(f"{base_path}/title.md")
    subtitle_content = get_gitea_file_content(f"{base_path}/sub-title.md")
    main_content = get_gitea_file_content(f"{base_path}/01.md")
    
    if not all([title_content, subtitle_content, main_content]):
        logger.error(f"Failed to fetch all components for {article_folder}")
        return None
    
    # Create Notion page
    page_id = create_notion_page(
        NOTION_PARENT_PAGE_ID,
        title_content.strip(),
        subtitle_content.strip(),
        main_content,
        skip_existing
    )
    
    return page_id

def main():
    """Main function to process all articles."""
    parser = argparse.ArgumentParser(description='Import Translation Academy articles to Notion')
    parser.add_argument('--input', '-i', default="articles_to_import.txt", help='Input file with article folders to import')
    parser.add_argument('--skip-existing', '-s', action='store_true', help='Skip articles that already exist')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between imports in seconds (to avoid rate limiting)')
    args = parser.parse_args()
    
    articles = read_article_list(args.input)
    
    logger.info(f"Found {len(articles)} articles to import")
    successful = 0
    failed = 0
    
    for i, article in enumerate(articles):
        logger.info(f"Processing article {i+1}/{len(articles)}: {article}")
        page_id = process_article(article, args.skip_existing)
        
        if page_id:
            logger.info(f"Created Notion page with ID: {page_id}")
            successful += 1
        else:
            logger.error(f"Failed to create Notion page for {article}")
            failed += 1
        
        # Avoid rate limiting
        if i < len(articles) - 1 and args.delay > 0:
            time.sleep(args.delay)
    
    logger.info(f"Import completed. Success: {successful}, Failed: {failed}")

if __name__ == "__main__":
    main() 