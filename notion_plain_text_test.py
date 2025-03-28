import os
import re
import logging
import argparse
from dotenv import load_dotenv
import requests
import base64
from notion_client import Client

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
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

def fetch_gitea_content(article_folder, file_path):
    """Fetch content from Gitea API."""
    endpoint = f"{GITEA_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/translate/{article_folder}/{file_path}"
    headers = {"Authorization": f"token {gitea_api_key}"}
    
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        content_data = response.json()
        if 'content' in content_data:
            content = base64.b64decode(content_data['content']).decode('utf-8')
            return content
        else:
            logger.error(f"No content found for {article_folder}/{file_path}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error fetching {article_folder}/{file_path}: {str(e)}")
        return None

def preprocess_markdown(markdown_content):
    """Preprocess markdown content to handle formatting cases Notion doesn't support."""
    # Function to convert to unicode superscript characters
    def convert_to_unicode_superscript(match):
        text = match.group(1)
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

    # 1. Handle escaped brackets like \[text\]
    markdown_content = re.sub(r'\\\[(.*?)\\\]', r'[\1]', markdown_content)
    
    # 2. Handle specific footnote pattern like: > 53 \[Then everyone... [2]\]
    # This converts the footnote marker [2] to superscript ²
    markdown_content = re.sub(r'\[([\d]+)\]', lambda m: convert_to_unicode_superscript(m), markdown_content)
    
    # 3. Handle superscript tags <sup>text</sup> and convert to proper unicode superscript
    markdown_content = re.sub(r'<sup>(.*?)</sup>', convert_to_unicode_superscript, markdown_content)
    
    # 4. Apply superscript conversion for ^{} notation
    markdown_content = re.sub(r'\^\{(.*?)\}', convert_to_unicode_superscript, markdown_content)
    
    return markdown_content

def create_page_with_plain_text(title, content):
    """Create a page in Notion using plain text content."""
    # Preprocess the content
    processed_content = preprocess_markdown(content)
    
    # Create a new page with plain text content
    page_data = {
        "parent": {"page_id": NOTION_PARENT_ID},
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
            }
        ]
    }
    
    # Split content into paragraphs (by double newlines)
    paragraphs = processed_content.split("\n\n")
    
    # Create a paragraph block for each paragraph, splitting long paragraphs if needed
    for para in paragraphs:
        # Skip empty paragraphs
        if not para.strip():
            continue
            
        # Handle markdown headers - convert to appropriate heading blocks
        if para.strip().startswith("# "):
            page_data["children"].append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": para.strip()[2:]  # Remove the "# "
                            }
                        }
                    ]
                }
            })
        elif para.strip().startswith("## "):
            page_data["children"].append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": para.strip()[3:]  # Remove the "## "
                            }
                        }
                    ]
                }
            })
        elif para.strip().startswith("### "):
            page_data["children"].append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": para.strip()[4:]  # Remove the "### "
                            }
                        }
                    ]
                }
            })
        # Handle bullet lists
        elif para.strip().startswith("* ") or para.strip().startswith("- "):
            lines = para.strip().split("\n")
            for line in lines:
                if line.strip().startswith("* ") or line.strip().startswith("- "):
                    page_data["children"].append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": line.strip()[2:]  # Remove the "* " or "- "
                                    }
                                }
                            ]
                        }
                    })
        # Handle block quotes
        elif para.strip().startswith("> "):
            page_data["children"].append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": para.strip()[2:]  # Remove the "> "
                            }
                        }
                    ]
                }
            })
        # Regular paragraph
        else:
            # If paragraph is too long, split it into chunks of 2000 chars
            MAX_CHARS = 1900  # Slightly less than 2000 to be safe
            
            if len(para) <= MAX_CHARS:
                page_data["children"].append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": para
                                }
                            }
                        ]
                    }
                })
            else:
                # Split paragraph into chunks
                chunks = [para[i:i+MAX_CHARS] for i in range(0, len(para), MAX_CHARS)]
                for chunk in chunks:
                    page_data["children"].append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": chunk
                                    }
                                }
                            ]
                        }
                    })
    
    try:
        response = notion.pages.create(**page_data)
        logger.info(f"Created page '{title}' with plain text content")
        return response["id"]
    except Exception as e:
        logger.error(f"Error creating page with plain text: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Create Notion page with plain text markdown content")
    parser.add_argument("--article", required=True, help="Article ID to fetch and create")
    args = parser.parse_args()
    
    # Fetch article content
    article_id = args.article
    title_content = fetch_gitea_content(article_id, "title.md")
    article_content = fetch_gitea_content(article_id, "01.md")
    
    if not title_content or not article_content:
        logger.error(f"Failed to fetch content for {article_id}")
        return
    
    # Clean up title
    title = title_content.strip()
    
    # Create the page with plain text content
    page_id = create_page_with_plain_text(title, article_content)
    
    if page_id:
        logger.info(f"Successfully created page for '{title}' with ID: {page_id}")
    else:
        logger.error(f"Failed to create page for '{title}'")

if __name__ == "__main__":
    main() 