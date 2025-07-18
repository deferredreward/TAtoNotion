#!/usr/bin/env python3
"""
Clean Translation Academy Migration Script

Handles all markdown patterns found in the analysis:
- Headers (### ## #)
- Bold (**text**)
- Italic (*text*)
- Blockquotes (>) 
- Links [text](url)
- Lists (numbered and bulleted)
- Proper paragraph splitting
- Scripture references
"""

import os
import yaml
import json
import re
import logging
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from notion_client import Client
import requests
import base64

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("clean_ta_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GITEA_API_KEY = os.getenv("GITEA_API_KEY")

if not NOTION_API_KEY:
    logger.error("NOTION_API_KEY not found in .env file")
    exit(1)

if not GITEA_API_KEY:
    logger.error("GITEA_API_KEY not found in .env file")
    exit(1)

# Initialize clients
notion = Client(auth=NOTION_API_KEY)

# Constants
DATABASE_ID = "340b5f5c-4f57-4a6a-bd21-5e5b30aac26c"
GITEA_API_BASE = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_BRANCH = "master"

class CleanTAMigrator:
    def __init__(self):
        self.sections = {}
        self.content_hashes = {}
        
    def fetch_gitea_content(self, path: str) -> Optional[str]:
        """Fetch content from Gitea API."""
        url = f"{GITEA_API_BASE}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITEA_API_KEY}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data and "content" in data and data["content"]:
                content_raw = base64.b64decode(data["content"])
                content = content_raw.decode("utf-8")
                return content
            else:
                logger.warning(f"No content found for Gitea path: {path}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {path}: {e}")
            return None
    
    def parse_rich_text(self, text: str) -> List[Dict]:
        """Parse text for bold, italic, and links - simple and reliable approach."""
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        # Clean up any weird whitespace
        text = text.strip()
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        result = []
        i = 0
        
        while i < len(text):
            # Check for bold **text**
            if i < len(text) - 3 and text[i:i+2] == "**":
                # Find closing **
                end = text.find("**", i + 2)
                if end != -1:
                    bold_text = text[i+2:end]
                    result.append({
                        "type": "text",
                        "text": {"content": bold_text},
                        "annotations": {"bold": True}
                    })
                    i = end + 2
                    continue
            
            # Check for italic *text* (but not part of **)
            if (i < len(text) - 2 and text[i] == "*" and 
                (i == 0 or text[i-1] != "*") and 
                (i >= len(text) - 1 or text[i+1] != "*")):
                # Find closing *
                end = text.find("*", i + 1)
                if end != -1 and (end >= len(text) - 1 or text[end+1] != "*"):
                    italic_text = text[i+1:end]
                    result.append({
                        "type": "text",
                        "text": {"content": italic_text},
                        "annotations": {"italic": True}
                    })
                    i = end + 1
                    continue
            
            # Check for links [text](url)
            if text[i] == "[":
                # Find closing ]
                bracket_end = text.find("]", i + 1)
                if bracket_end != -1 and bracket_end < len(text) - 1 and text[bracket_end + 1] == "(":
                    # Find closing )
                    paren_end = text.find(")", bracket_end + 2)
                    if paren_end != -1:
                        link_text = text[i+1:bracket_end]
                        link_url = text[bracket_end+2:paren_end]
                        
                        result.append({
                            "type": "text",
                            "text": {
                                "content": link_text,
                                "link": {"url": link_url}
                            }
                        })
                        i = paren_end + 1
                        continue
            
            # Regular character
            result.append({
                "type": "text",
                "text": {"content": text[i]}
            })
            i += 1
        
        # Merge consecutive regular text
        merged = []
        current_text = ""
        
        for item in result:
            if (item["type"] == "text" and 
                "annotations" not in item and 
                "link" not in item["text"]):
                current_text += item["text"]["content"]
            else:
                if current_text:
                    merged.append({
                        "type": "text",
                        "text": {"content": current_text}
                    })
                    current_text = ""
                merged.append(item)
        
        if current_text:
            merged.append({
                "type": "text",
                "text": {"content": current_text}
            })
        
        return merged if merged else [{"type": "text", "text": {"content": ""}}]
    
    def convert_markdown_to_blocks(self, content: str) -> List[Dict]:
        """Convert markdown content to Notion blocks."""
        if not content:
            return []
        
        blocks = []
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Headers
            if line.startswith('#### '):\n                blocks.append({\n                    \"object\": \"block\",\n                    \"type\": \"heading_3\",  # Notion only has 3 levels, so #### becomes h3\n                    \"heading_3\": {\n                        \"rich_text\": self.parse_rich_text(line[5:])\n                    }\n                })\n            elif line.startswith('### '):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": self.parse_rich_text(line[4:])
                    }
                })
            elif line.startswith('## '):
                blocks.append({
                    "object": "block", 
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": self.parse_rich_text(line[3:])
                    }
                })
            elif line.startswith('# '):
                blocks.append({
                    "object": "block",
                    "type": "heading_1", 
                    "heading_1": {
                        "rich_text": self.parse_rich_text(line[2:])
                    }
                })
            
            # Blockquotes
            elif line.startswith('> '):
                quote_lines = []
                while i < len(lines) and lines[i].startswith('> '):
                    quote_lines.append(lines[i][2:])  # Remove "> "
                    i += 1
                i -= 1  # Back up one since we'll increment at end
                
                quote_text = ' '.join(quote_lines)
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": self.parse_rich_text(quote_text)
                    }
                })
            
            # Numbered lists (1. format)
            elif re.match(r'^\d+\.\s', line):
                list_items = []
                while i < len(lines) and re.match(r'^\d+\.\s', lines[i]):
                    item_text = re.sub(r'^\d+\.\s', '', lines[i])
                    list_items.append(item_text)
                    i += 1
                i -= 1  # Back up one
                
                for item in list_items:
                    blocks.append({
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": self.parse_rich_text(item)
                        }
                    })
            
            # Numbered lists ((1) format)
            elif re.match(r'^\(\d+\)\s', line):
                list_items = []
                while i < len(lines) and re.match(r'^\(\d+\)\s', lines[i]):
                    item_text = re.sub(r'^\(\d+\)\s', '', lines[i])
                    list_items.append(item_text)
                    i += 1
                i -= 1  # Back up one
                
                for item in list_items:
                    blocks.append({
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": self.parse_rich_text(item)
                        }
                    })
            
            # Bulleted lists
            elif line.startswith('* ') or line.startswith('- '):
                list_items = []
                while i < len(lines) and (lines[i].startswith('* ') or lines[i].startswith('- ')):
                    item_text = lines[i][2:]  # Remove "* " or "- "
                    list_items.append(item_text)
                    i += 1
                i -= 1  # Back up one
                
                for item in list_items:
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": self.parse_rich_text(item)
                        }
                    })
            
            # Regular paragraph
            else:
                # Collect consecutive non-special lines into a paragraph
                paragraph_lines = [line]
                j = i + 1
                while (j < len(lines) and 
                       lines[j].strip() and 
                       not lines[j].startswith('#') and
                       not lines[j].startswith('>') and 
                       not lines[j].startswith('*') and
                       not lines[j].startswith('-') and
                       not re.match(r'^\d+\.', lines[j]) and
                       not re.match(r'^\(\d+\)', lines[j])):
                    paragraph_lines.append(lines[j].rstrip())
                    j += 1
                
                paragraph_text = ' '.join(paragraph_lines)
                if paragraph_text.strip():
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": self.parse_rich_text(paragraph_text)
                        }
                    })
                
                i = j - 1  # Set i to last line we processed
            
            i += 1
        
        return blocks
    
    def load_article_from_gitea(self, section_name: str, article_name: str) -> Dict:
        """Load article content from Gitea API."""
        base_path = f"{section_name}/{article_name}"
        
        title_content = self.fetch_gitea_content(f"{base_path}/title.md") or ""
        subtitle_content = self.fetch_gitea_content(f"{base_path}/sub-title.md") or ""
        main_content = self.fetch_gitea_content(f"{base_path}/01.md") or ""
        
        # Calculate content hash for update detection
        combined_content = f"{title_content}|{subtitle_content}|{main_content}"
        content_hash = hashlib.md5(combined_content.encode()).hexdigest()
        
        return {
            'title': title_content.strip(),
            'subtitle': subtitle_content.strip(),
            'content': main_content.strip(),
            'section': section_name,
            'article_id': article_name,
            'content_hash': content_hash,
            'repository_path': f"en_ta/{base_path}",
            'gitea_url': f"https://git.door43.org/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/src/branch/{GITEA_BRANCH}/{base_path}/01.md"
        }
    
    def load_config_from_gitea(self, section_name: str) -> Dict:
        """Load section configuration from Gitea."""
        config_content = self.fetch_gitea_content(f"{section_name}/config.yaml")
        toc_content = self.fetch_gitea_content(f"{section_name}/toc.yaml")
        
        config_data = yaml.safe_load(config_content) if config_content else {}
        toc_data = yaml.safe_load(toc_content) if toc_content else {}
        
        return {
            'config': config_data,
            'toc': toc_data,
            'name': section_name
        }
    
    def create_database_properties(self, article_data: Dict, sequence_order: int) -> Dict:
        """Create database properties."""
        # Manual mapping
        manual_mapping = {
            'intro': 'Introduction',
            'process': 'Process Manual', 
            'translate': 'Translation Manual',
            'checking': 'Checking Manual'
        }
        
        properties = {
            # Core identification
            "Title": {
                "title": [{"type": "text", "text": {"content": article_data['title'] or article_data['article_id']}}]
            },
            
            "Slug": {
                "rich_text": [{"type": "text", "text": {"content": article_data['article_id']}}]
            },
            
            # Manual and organization
            "Manual": {
                "select": {"name": manual_mapping[article_data['section']]}
            },
            
            # Sequence and organization
            "Sequence Order": {
                "number": sequence_order
            },
            
            # Paths and references
            "Repository Path": {
                "rich_text": [{"type": "text", "text": {"content": article_data['repository_path']}}]
            },
            
            "Original URL": {
                "url": article_data['gitea_url']
            },
            
            # Content details
            "Summary": {
                "rich_text": [{"type": "text", "text": {"content": article_data['subtitle']}}]
            },
            
            # Status
            "Status": {
                "select": {"name": "Complete" if article_data['content'] else "Needs Review"}
            }
        }
        
        return properties
    
    def create_database_entry(self, article_data: Dict, sequence_order: int) -> Optional[str]:
        """Create database entry with clean formatting."""
        try:
            # Create database properties
            properties = self.create_database_properties(article_data, sequence_order)
            
            # Create the database page
            response = notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=properties
            )
            
            page_id = response['id']
            logger.info(f"Created database entry for {article_data['article_id']}: {page_id}")
            
            # Add content using clean markdown processing
            if article_data['content']:
                blocks = self.convert_markdown_to_blocks(article_data['content'])
                if blocks:
                    self.add_blocks_to_page(page_id, blocks)
                    logger.info(f"Added {len(blocks)} blocks to {page_id}")
            
            return page_id
            
        except Exception as e:
            logger.error(f"Error creating database entry for {article_data['article_id']}: {e}")
            return None
    
    def add_blocks_to_page(self, page_id: str, blocks: List[Dict]):
        """Add blocks to page in batches."""
        batch_size = 100
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]
            
            try:
                notion.blocks.children.append(
                    block_id=page_id,
                    children=batch
                )
                
            except Exception as e:
                logger.error(f"Error adding blocks to page {page_id}: {e}")

def main():
    """Main migration function."""
    migrator = CleanTAMigrator()
    
    logger.info("Starting clean Translation Academy migration...")
    
    # Process 10 test articles
    test_articles = [
        'translate/translate-fandm',      # Form and Meaning
        'translate/figs-metaphor',        # Figures of speech
        'translate/figs-simile', 
        'translate/figs-metonymy',
        'translate/figs-hyperbole',
        'translate/figs-irony',
        'translate/figs-rquestion',
        'translate/figs-synecdoche',
        'translate/figs-personification',
        'translate/figs-apostrophe'
    ]
    
    articles_to_process = []
    
    for test_article in test_articles:
        section_name, article_name = test_article.split('/', 1)
        logger.info(f"Loading {section_name} section from Gitea...")
        
        # Load section configuration if not already loaded
        if section_name not in migrator.sections:
            migrator.sections[section_name] = migrator.load_config_from_gitea(section_name)
        
        article_data = migrator.load_article_from_gitea(section_name, article_name)
        if article_data['content']:
            articles_to_process.append((test_article, article_data))
            logger.info(f"Loaded article: {test_article} - {article_data['title']}")
    
    if not articles_to_process:
        logger.info("No articles found")
        return
    
    logger.info(f"Processing {len(articles_to_process)} articles...")
    
    # Process articles
    success_count = 0
    for i, (article_key, article_data) in enumerate(articles_to_process, 1):
        logger.info(f"Processing ({i}/{len(articles_to_process)}): {article_key}")
        logger.info(f"  Title: {article_data['title']}")
        
        page_id = migrator.create_database_entry(article_data, i)
        
        if page_id:
            success_count += 1
            logger.info(f"  Created page: https://www.notion.so/{page_id.replace('-', '')}")
        
        # Rate limiting
        time.sleep(0.5)
    
    logger.info(f"Clean migration complete: {success_count}/{len(articles_to_process)} successful")

if __name__ == "__main__":
    main()