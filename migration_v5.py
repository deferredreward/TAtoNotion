#!/usr/bin/env python3
"""
Enhanced Translation Academy Migration Script

This script combines the best practices from the existing codebase:
- Advanced markdown formatting from build_toc_structure.py
- Gitea API integration for source of truth
- Database population with rich metadata
- Update detection for monthly sync
- Link resolution and relationship handling
"""

import os
import yaml
import json
import re
import logging
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from notion_client import Client
import requests
import base64

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("enhanced_ta_migration.log"),
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

# Global caches and mappings
page_cache = {}
url_to_page_id_map = {}
article_to_page_id_map = {}

class EnhancedTAMigrator:
    def __init__(self):
        self.sections = {}
        self.articles_data = {}
        self.content_hashes = {}  # For update detection
        self.section_sequence = {'intro': 1, 'process': 2, 'translate': 3, 'checking': 4}
        
    def fetch_gitea_content(self, path: str) -> Optional[str]:
        """Fetch content from Gitea API with caching."""
        cache_key = f"gitea_content:{path}"
        if cache_key in page_cache:
            return page_cache[cache_key]
        
        url = f"{GITEA_API_BASE}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/contents/{path}"
        headers = {"Authorization": f"token {GITEA_API_KEY}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data and "content" in data and data["content"]:
                content_raw = base64.b64decode(data["content"])
                content = content_raw.decode("utf-8")
                page_cache[cache_key] = content
                return content
            else:
                logger.warning(f"No content found for Gitea path: {path}")
                page_cache[cache_key] = None
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {path}: {e}")
            page_cache[cache_key] = None
            return None
    
    def parse_rich_text(self, text: str) -> List[Dict]:
        """
        Advanced rich text parsing from build_toc_structure.py
        Handles bold, italic, links, footnotes with proper nesting
        """
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
        
        def parse_segment(segment):
            """Parse links (outermost level)"""
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
                article_id = self.extract_article_id_from_link(link_url)
                notion_page_id = self.find_page_id_from_article_id(article_id) if article_id else None
                
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
            """Parse bold and italic formatting"""
            # Bold replacement
            def bold_repl(m):
                return f"\0BOLD{m.group(1)}\0"
            segment = re.sub(bold_pattern, bold_repl, segment)
            
            # Italic replacement (asterisk)
            def italic_repl(m):
                return f"\0ITALIC{m.group(1)}\0"
            segment = re.sub(italic_pattern, italic_repl, segment)
            
            # Italic replacement (underscore)
            def underscore_italic_repl(m):
                return f"\0ITALIC{m.group(1)}\0"
            segment = re.sub(underscore_italic_pattern, underscore_italic_repl, segment)
            
            # Footnote replacement
            def footnote_repl(m):
                return f"\0FOOTNOTE{m.group(1)}\0"
            segment = re.sub(footnote_pattern, footnote_repl, segment)
            
            # Split by null markers and create rich text objects
            parts = []
            tokens = re.split(r'(\0(?:BOLD|ITALIC|FOOTNOTE)[^\0]*\0)', segment)
            
            for token in tokens:
                if not token:
                    continue
                    
                if token.startswith('\0BOLD') and token.endswith('\0'):
                    content = token[5:-1]  # Remove \0BOLD and \0
                    parts.append({
                        "type": "text",
                        "text": {"content": content},
                        "annotations": {"bold": True}
                    })
                elif token.startswith('\0ITALIC') and token.endswith('\0'):
                    content = token[7:-1]  # Remove \0ITALIC and \0
                    parts.append({
                        "type": "text", 
                        "text": {"content": content},
                        "annotations": {"italic": True}
                    })
                elif token.startswith('\0FOOTNOTE') and token.endswith('\0'):
                    footnote_num = token[9:-1]  # Remove \0FOOTNOTE and \0
                    # Convert to superscript Unicode
                    superscript = ''.join({
                        '0':'⁰','1':'¹','2':'²','3':'³','4':'⁴',
                        '5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'
                    }.get(c, c) for c in footnote_num)
                    parts.append({
                        "type": "text",
                        "text": {"content": superscript},
                        "annotations": {"color": "gray"}
                    })
                else:
                    # Regular text
                    parts.append({
                        "type": "text",
                        "text": {"content": token}
                    })
            
            return parts
        
        return parse_segment(text)
    
    def process_nested_blockquotes(self, lines: List[str], start_index: int) -> Tuple[List[Dict], int]:
        """
        Process nested blockquotes from build_toc_structure.py
        Handles complex quote structures with proper nesting
        """
        blocks = []
        level_groups = []  # List of (level, lines)
        current_level = 0
        current_lines = []
        i = start_index
        
        # First pass: group lines by markdown nesting level
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
            
            # Clean any <sup> HTML tags to unicode superscript
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
                "quote": {"rich_text": self.parse_rich_text(quote_content), "children": []}
            }
            
            if level > 1 and len(stack) >= level-1:
                parent = stack[level-2]
                parent['quote']['children'].append(block)
            else:
                blocks.append(block)
            
            # Update stack for this level
            stack = stack[:level-1] + [block]
        
        return blocks, i
    
    def convert_markdown_to_notion_blocks(self, content: str) -> List[Dict]:
        """
        Advanced markdown to Notion blocks conversion
        Handles headers, lists, blockquotes, paragraphs with rich formatting
        """
        if not content:
            return []
        
        lines = content.split('\\n')
        blocks = []
        i = 0
        current_paragraph = []
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                # Empty line - finish current paragraph
                if current_paragraph:
                    paragraph_content = ' '.join(current_paragraph)
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": self.parse_rich_text(paragraph_content)
                        }
                    })
                    current_paragraph = []
                i += 1
                continue
            
            # Check for headers
            if line.startswith('### '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": self.parse_rich_text(line[4:])
                    }
                })
            elif line.startswith('## '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": self.parse_rich_text(line[3:])
                    }
                })
            elif line.startswith('# '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": self.parse_rich_text(line[2:])
                    }
                })
            # Check for blockquotes
            elif line.startswith('>'):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                
                # Process nested blockquotes
                quote_blocks, new_i = self.process_nested_blockquotes(lines, i)
                blocks.extend(quote_blocks)
                i = new_i - 1  # Will be incremented at end of loop
            # Check for numbered lists
            elif re.match(r'^\d+\.\s', line):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                content = re.sub(r'^\d+\.\s', '', line)
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": self.parse_rich_text(content)
                    }
                })
            # Check for bullet lists
            elif line.startswith('* ') or line.startswith('- '):
                self._finish_paragraph(blocks, current_paragraph)
                current_paragraph = []
                content = line[2:]
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": self.parse_rich_text(content)
                    }
                })
            else:
                # Regular text line - add to current paragraph
                current_paragraph.append(line)
            
            i += 1
        
        # Finish any remaining paragraph
        self._finish_paragraph(blocks, current_paragraph)
        
        return blocks
    
    def _finish_paragraph(self, blocks: List[Dict], current_paragraph: List[str]):
        """Helper to finish current paragraph."""
        if current_paragraph:
            paragraph_content = ' '.join(current_paragraph)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": self.parse_rich_text(paragraph_content)
                }
            })
    
    def extract_article_id_from_link(self, link_url: str) -> Optional[str]:
        """Extract article ID from various internal link formats."""
        if not link_url or not isinstance(link_url, str):
            return None
        
        # Handle various formats: ../slug/, ../slug/01.md, /manual/slug/, etc.
        match = re.search(r'(?:\.\./|/)(?:intro|process|checking|translate)/([^/]+)(?:/01\.md|/)?$', link_url)
        if match:
            return match.group(1)
        
        # Fallback for just ../slug/ format
        relative_match = re.search(r'\.\./([^/]+)(?:/01\.md|/)?$', link_url)
        if relative_match:
            return relative_match.group(1)
        
        return None
    
    def find_page_id_from_article_id(self, article_id: str) -> Optional[str]:
        """Find the Notion page ID for an article ID."""
        if not article_id:
            return None
        
        # Check cache first
        for article_key, page_id in article_to_page_id_map.items():
            if article_key.endswith(f"/{article_id}"):
                return page_id
        
        return None
    
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
    
    def get_article_relationships(self, section_name: str, article_name: str) -> Dict:
        """Get relationships from config data."""
        config = self.sections.get(section_name, {}).get('config', {})
        article_config = config.get(article_name, {})
        
        return {
            'dependencies': article_config.get('dependencies', []),
            'recommended': article_config.get('recommended', []),
            'article_id': article_name,
            'section': section_name
        }
    
    def check_for_updates(self, article_key: str, new_hash: str) -> bool:
        """Check if article content has been updated since last migration."""
        old_hash = self.content_hashes.get(article_key)
        return old_hash != new_hash
    
    def load_existing_hashes(self):
        """Load existing content hashes from previous migration."""
        try:
            with open('content_hashes.json', 'r') as f:
                self.content_hashes = json.load(f)
        except FileNotFoundError:
            self.content_hashes = {}
    
    def save_content_hashes(self):
        """Save content hashes for future update detection."""
        with open('content_hashes.json', 'w') as f:
            json.dump(self.content_hashes, f, indent=2)
    
    def create_enhanced_database_entry(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Optional[str]:
        """Create database entry with enhanced formatting and metadata."""
        try:
            # Create comprehensive properties (reusing previous logic)
            properties = self.create_database_properties(article_data, relationships, sequence_order)
            
            # Create the database page
            response = notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=properties
            )
            
            page_id = response['id']
            logger.info(f"Created enhanced database entry for {article_data['article_id']}: {page_id}")
            
            # Add content using advanced markdown processing
            if article_data['content']:
                blocks = self.convert_markdown_to_notion_blocks(article_data['content'])
                if blocks:
                    self.add_blocks_in_batches(page_id, blocks)
            
            # Update mappings for link resolution
            article_key = f"{article_data['section']}/{article_data['article_id']}"
            article_to_page_id_map[article_key] = page_id
            
            return page_id
            
        except Exception as e:
            logger.error(f"Error creating enhanced database entry for {article_data['article_id']}: {e}")
            return None
    
    def create_database_properties(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Dict:
        """Create comprehensive database properties with enhanced metadata."""
        full_content = f"{article_data['content']}\n{article_data['subtitle']}"
        
        # Manual mapping
        manual_mapping = {
            'intro': 'Introduction',
            'process': 'Process Manual', 
            'translate': 'Translation Manual',
            'checking': 'Checking Manual'
        }
        
        # Content type detection
        def get_content_type(article_id, section):
            if article_id.startswith('figs-') or article_id.startswith('grammar-'):
                return 'Module'
            elif article_id in ['intro-checking', 'intro-share', 'intro-publishing', 'ta-intro']:
                return 'Section'
            else:
                return 'Topic'
        
        # Key concepts detection
        def get_key_concepts(article_id, content):
            concepts = []
            if 'figs-' in article_id or any(word in content.lower() for word in ['metaphor', 'simile']):
                concepts.append('Figures of Speech')
            if 'grammar-' in article_id or any(word in content.lower() for word in ['verb', 'sentence']):
                concepts.append('Grammar')
            if any(word in content.lower() for word in ['translation', 'translate', 'meaning']):
                concepts.append('Translation Principles')
            if any(word in content.lower() for word in ['check', 'review', 'accuracy']):
                concepts.append('Quality Assurance')
            if any(word in content.lower() for word in ['team', 'leader', 'collaborate']):
                concepts.append('Team Management')
            if any(word in content.lower() for word in ['culture', 'cultural', 'context']):
                concepts.append('Cultural Context')
            if any(word in content.lower() for word in ['church', 'pastor', 'leader']):
                concepts.append('Church Involvement')
            if any(word in content.lower() for word in ['source', 'original', 'hebrew', 'greek']):
                concepts.append('Source Texts')
            return concepts
        
        # Target audience detection
        def get_target_audience(section, content):
            audiences = []
            if section == 'translate':
                audiences.append('Translators')
            elif section == 'checking':
                audiences.append('Checkers')
            elif section == 'process':
                audiences.append('Team Leaders')
            if any(word in content.lower() for word in ['train', 'teaching']):
                audiences.append('Trainers')
            if any(word in content.lower() for word in ['church', 'pastor']):
                audiences.append('Church Leaders')
            return audiences or ['Translators']
        
        # Difficulty level
        def get_difficulty_level(dependencies):
            if len(dependencies) == 0:
                return 'Beginner'
            elif len(dependencies) <= 3:
                return 'Intermediate'
            else:
                return 'Advanced'
        
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
            
            "Content Type": {
                "select": {"name": get_content_type(article_data['article_id'], article_data['section'])}
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
            
            # YAML configuration
            "YAML Config": {
                "rich_text": [{"type": "text", "text": {"content": json.dumps({
                    'dependencies': relationships['dependencies'],
                    'recommended': relationships['recommended']
                }, indent=2)}}]
            },
            
            # Difficulty and concepts
            "Difficulty Level": {
                "select": {"name": get_difficulty_level(relationships['dependencies'])}
            },
            
            "Key Concepts": {
                "multi_select": [{"name": concept} for concept in get_key_concepts(article_data['article_id'], full_content)]
            },
            
            # Target audience
            "Target Audience": {
                "multi_select": [{"name": audience} for audience in get_target_audience(article_data['section'], full_content)]
            },
            
            # Status
            "Status": {
                "select": {"name": "Complete" if article_data['content'] else "Needs Review"}
            },
            
            # Translation status
            "Translation Status": {
                "multi_select": [{"name": "Available in GL"}]
            }
        }
        
        return properties
    
    def add_blocks_in_batches(self, page_id: str, blocks: List[Dict], batch_size: int = 100):
        """Add blocks to page in batches, handling nested children."""
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]
            
            # Handle nested children for blockquotes
            processed_batch = []
            for block in batch:
                block_copy = block.copy()
                children = None
                
                if block.get("type") == "quote" and "children" in block.get("quote", {}):
                    children = block_copy["quote"].pop("children", [])
                
                processed_batch.append(block_copy)
            
            try:
                response = notion.blocks.children.append(
                    block_id=page_id,
                    children=processed_batch
                )
                
                # Handle nested children
                if any("children" in block.get("quote", {}) for block in batch if block.get("type") == "quote"):
                    self._append_nested_children(response, batch)
                
                logger.info(f"Added {len(processed_batch)} blocks to {page_id}")
                
            except Exception as e:
                logger.error(f"Error adding blocks to page {page_id}: {e}")
    
    def _append_nested_children(self, response: Dict, original_blocks: List[Dict]):
        """Append nested children for blockquotes."""
        results = response.get("results", [])
        for i, result_block in enumerate(results):
            if i < len(original_blocks):
                original = original_blocks[i]
                if (original.get("type") == "quote" and 
                    "children" in original.get("quote", {}) and
                    original["quote"]["children"]):
                    
                    children = original["quote"]["children"]
                    block_id = result_block["id"]
                    
                    try:
                        notion.blocks.children.append(
                            block_id=block_id,
                            children=children
                        )
                    except Exception as e:
                        logger.error(f"Error adding nested children: {e}")

def main():
    """Main migration function with enhanced capabilities."""
    migrator = EnhancedTAMigrator()
    
    # Load existing hashes for update detection
    migrator.load_existing_hashes()
    
    logger.info("Starting enhanced Translation Academy migration...")
    
    # Process 10 articles including form and meaning + figures of speech from just-in-time modules
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
        
        # Load section configuration
        migrator.sections[section_name] = migrator.load_config_from_gitea(section_name)
        
        article_data = migrator.load_article_from_gitea(section_name, article_name)
        if article_data['content']:
            article_key = f"{section_name}/{article_name}"
            articles_to_process.append((article_key, article_data))
            logger.info(f"Test article loaded: {article_key}")
    
    if not articles_to_process:
        logger.info("No test articles found")
        return
    
    logger.info(f"Processing {len(articles_to_process)} test articles...")
    
    # Process articles
    success_count = 0
    for i, (article_key, article_data) in enumerate(articles_to_process, 1):
        section_name, article_name = article_key.split('/', 1)
        relationships = migrator.get_article_relationships(section_name, article_name)
        
        logger.info(f"Processing test ({i}/{len(articles_to_process)}): {article_key}")
        logger.info(f"  Title: {article_data['title']}")
        
        page_id = migrator.create_enhanced_database_entry(article_data, relationships, i)
        
        if page_id:
            # Update hash for future comparisons
            migrator.content_hashes[article_key] = article_data['content_hash']
            success_count += 1
            logger.info(f"  Created page: https://www.notion.so/{page_id.replace('-', '')}")
        
        # Rate limiting
        time.sleep(0.5)
    
    # Save updated hashes
    migrator.save_content_hashes()
    
    logger.info(f"Enhanced migration test complete: {success_count}/{len(articles_to_process)} successful")

if __name__ == "__main__":
    main()