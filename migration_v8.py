#!/usr/bin/env python3
"""
Final Fixed Translation Academy Migration Script

Fixes:
1. Nested blockquotes (> >) as children of parent quote blocks
2. Proper list numbering that increments correctly
3. All rich metadata preserved
4. Clean markdown processing
"""

import os
import yaml
import json
import re
import logging
import time
import hashlib
import argparse
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
        logging.FileHandler("final_fixed_migration.log"),
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

class FinalFixedTAMigrator:
    def __init__(self):
        self.sections = {}
        self.content_hashes = {}
        
        # Unicode superscript mapping for HTML <sup> tag conversion
        self.superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
            'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ',
            'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 'i': 'ⁱ', 'j': 'ʲ',
            'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ',
            'p': 'ᵖ', 'q': 'ᵠ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ',
            'u': 'ᵘ', 'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ',
            'z': 'ᶻ', '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽',
            ')': '⁾', '[': '⁽', ']': '⁾', ' ': ' '
        }
        
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
    
    def convert_to_superscript(self, text: str) -> str:
        """Convert text to Unicode superscript characters."""
        return ''.join(self.superscript_map.get(c, c) for c in text)
    
    def clean_html_and_formatting(self, text: str) -> str:
        """Remove HTML tags and fix formatting issues."""
        if not text:
            return text
        
        # Handle <sup> tags with comprehensive patterns
        def sup_full_repl(match):
            content = match.group(1).strip()
            
            # Combined numeric and bracket footnote: e.g. '16 [1]' -> ¹⁶⁽¹⁾
            cm = re.match(r'^(?P<num>\d+)\s*\[\s*(?P<foot>\d+)\s*\]$', content)
            if cm:
                num_sup = self.convert_to_superscript(cm.group('num'))
                foot_sup = self.convert_to_superscript(cm.group('foot'))
                return f"{num_sup}⁽{foot_sup}⁾"
            
            # Bracket-only footnote: e.g. '[1]' -> ⁽¹⁾
            bm = re.match(r'^\[\s*(\d+)\s*\]$', content)
            if bm:
                foot_sup = self.convert_to_superscript(bm.group(1))
                return f"⁽{foot_sup}⁾"
            
            # Numeric superscript: e.g. '16' -> ¹⁶
            nm = re.match(r'^(\d+)$', content)
            if nm:
                return self.convert_to_superscript(nm.group(1))
            
            # Fallback: convert any content to superscript
            return self.convert_to_superscript(content)
        
        # Apply superscript conversion
        text = re.sub(r'<sup>\s*(.*?)\s*</sup>', sup_full_repl, text)
        
        # Handle <br> tags - convert to line breaks
        text = text.replace('<br>', '\n')
        text = text.replace('<br/>', '\n')
        text = text.replace('<br />', '\n')
        
        # Fix stray literal \n characters - convert to actual line breaks
        text = text.replace('\\n', '\n')
        
        # Remove other common HTML tags
        text = re.sub(r'</?p>', '', text)
        text = re.sub(r'</?div[^>]*>', '', text)
        text = re.sub(r'</?span[^>]*>', '', text)
        text = re.sub(r'</?strong>', '', text)  # Keep bold formatting in text
        text = re.sub(r'</?em>', '', text)     # Keep italic formatting in text
        text = re.sub(r'</?b>', '', text)      # Keep bold formatting in text
        text = re.sub(r'</?i>', '', text)      # Keep italic formatting in text
        
        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 consecutive newlines
        text = re.sub(r'\s+', ' ', text)  # Multiple whitespace to single space
        text = text.strip()
        
        return text
    
    def parse_rich_text(self, text: str) -> List[Dict]:
        """Parse text for bold, italic, and links - simple and reliable approach."""
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        # Clean HTML and formatting issues first
        text = self.clean_html_and_formatting(text)
        
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
        """Convert markdown content to Notion blocks with proper nested blockquotes and list numbering."""
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
            
            # Headers (handle #### first, then ###, ##, #)
            if line.startswith('#### '):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",  # Notion only has 3 levels, so #### becomes h3
                    "heading_3": {
                        "rich_text": self.parse_rich_text(line[5:])
                    }
                })
            elif line.startswith('### '):
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
            
            # Tables (markdown format: | header | header |)
            elif line.startswith('|') and '|' in line[1:]:
                table_block, new_i = self.process_table(lines, i)
                if table_block:
                    blocks.append(table_block)
                i = new_i - 1  # Will be incremented at end of loop
            
            # Blockquotes (handle nested > > properly as children)
            elif line.startswith('> '):
                # Check if this is a nested quote (> >) that should be a child
                if line.startswith('> >') and blocks:
                    # Collect all consecutive nested quotes
                    nested_quotes = []
                    j = i
                    while j < len(lines) and lines[j].startswith('> >'):
                        nested_content = lines[j][3:].strip()  # Remove "> > "
                        if nested_content:
                            nested_quotes.append(nested_content)
                        j += 1
                    
                    if nested_quotes:
                        # Create child quote blocks
                        for nested_content in nested_quotes:
                            child_quote = {
                                "object": "block",
                                "type": "quote",
                                "quote": {
                                    "rich_text": self.parse_rich_text(nested_content)
                                }
                            }
                            
                            # Add as child to the previous block
                            last_block = blocks[-1]
                            block_type = last_block.get("type")
                            
                            if block_type in ["numbered_list_item", "bulleted_list_item", "paragraph"]:
                                # Initialize children if not exists
                                if "children" not in last_block.get(block_type, {}):
                                    last_block[block_type]["children"] = []
                                last_block[block_type]["children"].append(child_quote)
                            else:
                                # Fallback: create a separate quote block
                                blocks.append(child_quote)
                    
                    i = j - 1  # Skip the processed nested quote lines
                else:
                    # Regular blockquote processing
                    quote_block, new_i = self.process_blockquotes(lines, i)
                    if quote_block:
                        blocks.append(quote_block)
                    i = new_i - 1  # Will be incremented at end of loop
            
            # Numbered lists ((1) format) - ensure proper incrementing
            elif re.match(r'^\(\d+\)\s', line):
                list_blocks, new_i = self.process_numbered_list(lines, i, 'paren')
                blocks.extend(list_blocks)
                i = new_i - 1
            
            # Numbered lists (1. format) - ensure proper incrementing  
            elif re.match(r'^\d+\.\s', line):
                list_blocks, new_i = self.process_numbered_list(lines, i, 'dot')
                blocks.extend(list_blocks)
                i = new_i - 1
            
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
    
    def process_table(self, lines: List[str], start_i: int) -> tuple:
        """Process markdown table and convert to Notion table block."""
        try:
            table_lines = []
            i = start_i
            
            # Collect all table lines (starting with |)
            while i < len(lines) and lines[i].strip().startswith('|'):
                line = lines[i].strip()
                if line.endswith('|'):
                    table_lines.append(line)
                i += 1
            
            if len(table_lines) < 2:
                # Not a valid table, return None
                return None, start_i + 1
            
            # Parse table structure
            header_line = table_lines[0]
            headers = [cell.strip() for cell in header_line.split('|')[1:-1]]  # Remove empty first/last
            
            # Skip separator line if it exists (like |----|----|)
            data_start = 1
            if len(table_lines) > 1 and all(c in '-|: ' for c in table_lines[1]):
                data_start = 2
            
            # Parse data rows
            rows = []
            for line in table_lines[data_start:]:
                cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last
                if len(cells) >= len(headers):
                    rows.append(cells[:len(headers)])  # Truncate to header count
                elif len(cells) > 0:
                    # Pad short rows with empty cells
                    while len(cells) < len(headers):
                        cells.append('')
                    rows.append(cells)
            
            if not rows:
                return None, start_i + 1
            
            # Create Notion table block (working approach from single_page_updater)
            table_block = {
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": len(headers),
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": []
                }
            }
            
            # Add header row
            header_row = {
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": []
                }
            }
            
            for header in headers:
                header_row["table_row"]["cells"].append(
                    self.parse_rich_text(header) if header else [{"type": "text", "text": {"content": ""}}]
                )
            
            table_block["table"]["children"].append(header_row)
            
            # Add data rows
            for row in rows:
                row_block = {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": []
                    }
                }
                
                for cell in row:
                    row_block["table_row"]["cells"].append(
                        self.parse_rich_text(cell) if cell else [{"type": "text", "text": {"content": ""}}]
                    )
                
                table_block["table"]["children"].append(row_block)
            
            return table_block, i
            
        except Exception as e:
            logger.error(f"Error processing table: {e}")
            return None, start_i + 1
    
    def process_blockquotes(self, lines: List[str], start_i: int) -> tuple:
        """Process blockquotes with proper nesting as children."""
        main_quote_lines = []
        children = []
        i = start_i
        
        while i < len(lines) and lines[i].startswith('> '):
            line_content = lines[i][2:]  # Remove "> "
            
            # Check for nested blockquote > > text
            if line_content.startswith('> '):
                nested_content = line_content[2:]  # Remove another "> "
                if nested_content.strip():
                    # Create child quote block
                    child_quote = {
                        "object": "block",
                        "type": "quote",
                        "quote": {
                            "rich_text": self.parse_rich_text(nested_content)
                        }
                    }
                    children.append(child_quote)
            else:
                # Regular quote content
                if line_content.strip():  # Skip empty quote lines
                    main_quote_lines.append(line_content)
            
            i += 1
        
        # Create main quote block
        if main_quote_lines or children:
            quote_text = '\n'.join(main_quote_lines) if main_quote_lines else ""
            
            # Ensure empty quotes have proper space placeholder
            if not quote_text.strip():
                quote_block = {
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": " "}}]
                    }
                }
            else:
                quote_block = {
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": self.parse_rich_text(quote_text)
                    }
                }
            
            # Add children if any
            if children:
                quote_block["quote"]["children"] = children
            
            return quote_block, i
        
        return None, i
    
    def process_numbered_list(self, lines: List[str], start_i: int, list_type: str) -> tuple:
        """Process numbered lists with proper incremental numbering."""
        list_items = []
        i = start_i
        
        if list_type == 'paren':
            pattern = r'^\(\d+\)\s'
        else:  # dot
            pattern = r'^\d+\.\s'
        
        # Collect all consecutive numbered items, ignoring empty lines
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Check if this is a numbered list item
            if re.match(pattern, line):
                # Extract item text
                item_text = re.sub(pattern, '', line)
                list_items.append(item_text)
                i += 1
            else:
                # Not a numbered list item, stop processing
                break
        
        # Create numbered list items
        blocks = []
        for item in list_items:
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": self.parse_rich_text(item)
                }
            })
        
        return blocks, i
    
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
    
    def extract_learning_objective(self, content: str) -> str:
        """Extract or generate a learning objective from content."""
        lines = content.split('\\n')
        for line in lines[:10]:
            if any(keyword in line.lower() for keyword in ['learn', 'understand', 'objective', 'goal']):
                return line.strip()[:200]
        
        paragraphs = [p.strip() for p in content.split('\\n\\n') if p.strip() and not p.startswith('#')]
        if paragraphs:
            return paragraphs[0][:200] + "..." if len(paragraphs[0]) > 200 else paragraphs[0]
        
        return "Learn about translation concepts and techniques."
    
    def get_content_type(self, article_id: str, section: str) -> str:
        """Determine content type based on article ID and section."""
        if article_id.startswith('figs-') or article_id.startswith('grammar-'):
            return 'Module'
        elif article_id in ['intro-checking', 'intro-share', 'intro-publishing', 'ta-intro']:
            return 'Section'
        else:
            return 'Topic'
    
    def get_key_concepts(self, article_id: str, content: str) -> List[str]:
        """Extract key concepts from article."""
        concepts = []
        content_lower = content.lower()
        
        if 'figs-' in article_id or any(word in content_lower for word in ['metaphor', 'simile']):
            concepts.append('Figures of Speech')
        if 'grammar-' in article_id or any(word in content_lower for word in ['verb', 'sentence']):
            concepts.append('Grammar')
        if any(word in content_lower for word in ['translation', 'translate', 'meaning']):
            concepts.append('Translation Principles')
        if any(word in content_lower for word in ['check', 'review', 'accuracy']):
            concepts.append('Quality Assurance')
        if any(word in content_lower for word in ['team', 'leader', 'collaborate']):
            concepts.append('Team Management')
        if any(word in content_lower for word in ['culture', 'cultural', 'context']):
            concepts.append('Cultural Context')
        if any(word in content_lower for word in ['church', 'pastor', 'leader']):
            concepts.append('Church Involvement')
        if any(word in content_lower for word in ['source', 'original', 'hebrew', 'greek']):
            concepts.append('Source Texts')
        
        return concepts
    
    def get_target_audience(self, section: str, article_id: str, content: str) -> List[str]:
        """Determine target audience."""
        audiences = []
        content_lower = content.lower()
        
        if section == 'translate':
            audiences.append('Translators')
        elif section == 'checking':
            audiences.append('Checkers')
        elif section == 'process':
            audiences.append('Team Leaders')
        
        if any(word in content_lower for word in ['train', 'teaching']):
            audiences.append('Trainers')
        if any(word in content_lower for word in ['church', 'pastor']):
            audiences.append('Church Leaders')
        
        return audiences or ['Translators']
    
    def get_difficulty_level(self, dependencies: List[str]) -> str:
        """Determine difficulty level based on dependencies."""
        if len(dependencies) == 0:
            return 'Beginner'
        elif len(dependencies) <= 3:
            return 'Intermediate'
        else:
            return 'Advanced'
    
    def create_database_properties(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Dict:
        """Create comprehensive database properties with all metadata."""
        full_content = f"{article_data['content']}\\n{article_data['subtitle']}"
        
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
            
            "Content Type": {
                "select": {"name": self.get_content_type(article_data['article_id'], article_data['section'])}
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
            
            "Learning Objective": {
                "rich_text": [{"type": "text", "text": {"content": self.extract_learning_objective(full_content)}}]
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
                "select": {"name": self.get_difficulty_level(relationships['dependencies'])}
            },
            
            "Key Concepts": {
                "multi_select": [{"name": concept} for concept in self.get_key_concepts(article_data['article_id'], full_content)]
            },
            
            # Target audience
            "Target Audience": {
                "multi_select": [{"name": audience} for audience in self.get_target_audience(article_data['section'], article_data['article_id'], full_content)]
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
    
    def find_existing_page(self, article_id: str) -> Optional[str]:
        """Find existing page by slug/article_id."""
        try:
            # Query database for existing page with matching slug
            response = notion.databases.query(
                database_id=DATABASE_ID,
                filter={
                    "property": "Slug",
                    "rich_text": {
                        "equals": article_id
                    }
                }
            )
            
            if response.get("results"):
                page_id = response["results"][0]["id"]
                logger.info(f"Found existing page for {article_id}: {page_id}")
                return page_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error searching for existing page {article_id}: {e}")
            return None
    
    def clear_page_content(self, page_id: str):
        """Clear existing content blocks from a page."""
        try:
            # Get existing blocks
            response = notion.blocks.children.list(block_id=page_id)
            
            # Delete all existing blocks
            for block in response.get("results", []):
                notion.blocks.delete(block_id=block["id"])
            
            logger.info(f"Cleared existing content from page {page_id}")
            
        except Exception as e:
            logger.error(f"Error clearing page content {page_id}: {e}")
    
    def create_or_update_database_entry(self, article_data: Dict, relationships: Dict, sequence_order: int) -> Optional[str]:
        """Create new database entry or update existing one."""
        try:
            # Check if page already exists
            existing_page_id = self.find_existing_page(article_data['article_id'])
            
            if existing_page_id:
                # Update existing page
                logger.info(f"Updating existing page for {article_data['article_id']}")
                
                # Update properties
                properties = self.create_database_properties(article_data, relationships, sequence_order)
                notion.pages.update(
                    page_id=existing_page_id,
                    properties=properties
                )
                
                # Clear existing content and add new content
                self.clear_page_content(existing_page_id)
                
                if article_data['content']:
                    blocks = self.convert_markdown_to_blocks(article_data['content'])
                    if blocks:
                        self.add_blocks_to_page(existing_page_id, blocks)
                        logger.info(f"Updated {len(blocks)} blocks in {existing_page_id}")
                
                return existing_page_id
            else:
                # Create new page
                logger.info(f"Creating new page for {article_data['article_id']}")
                
                properties = self.create_database_properties(article_data, relationships, sequence_order)
                
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
            logger.error(f"Error creating/updating database entry for {article_data['article_id']}: {e}")
            return None
    
    def add_blocks_to_page(self, page_id: str, blocks: List[Dict]):
        """Add blocks to page in batches, handling nested children."""
        batch_size = 100
        
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]
            
            # Separate children from parent blocks for API call
            children_to_process = {}
            table_children_to_process = {}
            clean_batch = []
            
            for idx, block in enumerate(batch):
                block_copy = block.copy()
                block_type = block_copy.get("type")
                
                # Handle table children separately
                if block_type == "table" and "_table_children" in block_copy:
                    table_children = block_copy.pop("_table_children", [])
                    table_children_to_process[idx] = table_children
                
                # Check for children in various block types (exclude tables as they handle children differently)
                if block_type and block_type in block_copy and block_type != "table":
                    if "children" in block_copy[block_type]:
                        children = block_copy[block_type].pop("children", [])
                        children_to_process[idx] = children
                
                clean_batch.append(block_copy)
            
            try:
                # Add parent blocks first
                response = notion.blocks.children.append(
                    block_id=page_id,
                    children=clean_batch
                )
                
                # Add children to their parent blocks
                if "results" in response:
                    # Handle regular children
                    if children_to_process:
                        for batch_idx, children in children_to_process.items():
                            if batch_idx < len(response["results"]):
                                parent_block_id = response["results"][batch_idx]["id"]
                                notion.blocks.children.append(
                                    block_id=parent_block_id,
                                    children=children
                                )
                    
                    # Handle table children
                    if table_children_to_process:
                        for batch_idx, table_children in table_children_to_process.items():
                            if batch_idx < len(response["results"]):
                                table_block_id = response["results"][batch_idx]["id"]
                                notion.blocks.children.append(
                                    block_id=table_block_id,
                                    children=table_children
                                )
                
            except Exception as e:
                logger.error(f"Error adding blocks to page {page_id}: {e}")

def load_test_articles():
    """Load test articles from file."""
    test_file = Path("test_articles.txt")
    if test_file.exists():
        with open(test_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    else:
        logger.warning("test_articles.txt not found, using empty list")
        return []

def discover_all_articles(migrator):
    """Discover all articles from all sections by scanning the filesystem."""
    all_articles = []
    
    # Known sections - scan the local en_ta directory
    sections_to_check = ['intro', 'translate', 'process', 'checking']
    base_path = Path('en_ta')
    
    for section_name in sections_to_check:
        try:
            logger.info(f"Discovering articles in {section_name} section...")
            section_path = base_path / section_name
            
            if not section_path.exists():
                logger.warning(f"Section path {section_path} does not exist")
                continue
            
            articles_found = []
            
            # Scan all subdirectories in the section
            for item in section_path.iterdir():
                if item.is_dir() and item.name not in ['config.yaml', 'toc.yaml']:
                    # Check if this directory contains an 01.md file
                    article_file = item / '01.md'
                    if article_file.exists():
                        article_name = item.name
                        articles_found.append(article_name)
                        article_path = f"{section_name}/{article_name}"
                        all_articles.append(article_path)
                        logger.info(f"Found article: {article_path}")
            
            logger.info(f"Found {len(articles_found)} articles in {section_name} section")
            
        except Exception as e:
            logger.error(f"Error discovering articles in {section_name}: {str(e)}")
    
    logger.info(f"Discovered {len(all_articles)} total articles")
    return all_articles

def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Translation Academy Migration Script')
    parser.add_argument('--test', action='store_true', 
                       help='Run with test articles from test_articles.txt')
    parser.add_argument('--all', action='store_true', 
                       help='Run with all discovered articles (default)')
    
    args = parser.parse_args()
    
    # Default to --all if no option specified
    if not args.test and not args.all:
        args.all = True
    
    migrator = FinalFixedTAMigrator()
    
    logger.info("Starting final fixed Translation Academy migration...")
    
    # Determine which articles to process
    if args.test:
        logger.info("Running in TEST mode with articles from test_articles.txt")
        articles_list = load_test_articles()
    else:
        logger.info("Running in ALL mode - discovering all articles")
        articles_list = discover_all_articles(migrator)
    
    logger.info(f"Processing {len(articles_list)} articles in batches...")
    
    # Process articles in batches
    batch_size = 5  # Process 5 articles at a time
    success_count = 0
    total_articles = len(articles_list)
    
    # Load section configurations once
    sections_loaded = set()
    
    for i in range(0, total_articles, batch_size):
        batch = articles_list[i:i + batch_size]
        batch_start = i + 1
        batch_end = min(i + batch_size, total_articles)
        
        logger.info(f"Processing batch {batch_start}-{batch_end} of {total_articles} articles...")
        
        for j, article_key in enumerate(batch):
            article_num = i + j + 1
            logger.info(f"Processing ({article_num}/{total_articles}): {article_key}")
            
            try:
                section_name, article_name = article_key.split('/', 1)
                
                # Load section configuration if not already loaded
                if section_name not in sections_loaded:
                    logger.info(f"Loading {section_name} section configuration...")
                    if section_name not in migrator.sections:
                        migrator.sections[section_name] = migrator.load_config_from_gitea(section_name)
                    sections_loaded.add(section_name)
                
                # Load article data
                article_data = migrator.load_article_from_gitea(section_name, article_name)
                if not article_data['content']:
                    logger.warning(f"  No content found for {article_key}")
                    continue
                
                logger.info(f"  Title: {article_data['title']}")
                
                # Get relationships for this article
                relationships = migrator.get_article_relationships(section_name, article_name)
                
                # Create or update the database entry
                page_id = migrator.create_or_update_database_entry(article_data, relationships, article_num)
                
                if page_id:
                    success_count += 1
                    logger.info(f"  Created page: https://www.notion.so/{page_id.replace('-', '')}")
                else:
                    logger.error(f"  Failed to create page for {article_key}")
                
                # Rate limiting between articles
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"  Error processing {article_key}: {str(e)}")
                continue
        
        # Longer pause between batches to be respectful to APIs
        if batch_end < total_articles:
            logger.info(f"Batch {batch_start}-{batch_end} complete. Pausing before next batch...")
            time.sleep(2)
    
    logger.info(f"Final fixed migration complete: {success_count}/{total_articles} successful")

if __name__ == "__main__":
    main()