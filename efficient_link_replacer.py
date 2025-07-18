#!/usr/bin/env python3
"""
Efficient Link Replacer for Notion Database

This script replaces internal links more efficiently by:
1. Only updating blocks that actually contain links to be replaced
2. Using the block update API instead of deleting/recreating entire pages
3. Preserving block structure and only changing the link URLs
"""

import os
import sys
import re
import time
import logging
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from notion_client import Client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("efficient_link_replacement.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

class EfficientLinkReplacer:
    def __init__(self):
        self.page_map = {}  # Maps article paths to page IDs
        self.updated_blocks = 0
        self.total_links_replaced = 0
        self.total_images_embedded = 0
        
    def load_page_mapping(self):
        """Load all pages and create a mapping from article paths to page IDs."""
        logger.info("Loading page mapping from database...")
        
        try:
            all_pages = []
            start_cursor = None
            
            while True:
                if start_cursor:
                    response = notion.databases.query(
                        database_id=DATABASE_ID,
                        start_cursor=start_cursor
                    )
                else:
                    response = notion.databases.query(database_id=DATABASE_ID)
                
                all_pages.extend(response["results"])
                
                if not response["has_more"]:
                    break
                
                start_cursor = response["next_cursor"]
            
            logger.info(f"Found {len(all_pages)} pages in database")
            
            # Build mapping from repository path to page ID
            for page in all_pages:
                repo_path = None
                title = ""
                
                # Get repository path
                if "Repository Path" in page["properties"]:
                    repo_prop = page["properties"]["Repository Path"]
                    if repo_prop.get("rich_text"):
                        repo_path = repo_prop["rich_text"][0]["plain_text"]
                
                # Get title for logging
                if "Title" in page["properties"]:
                    title_prop = page["properties"]["Title"]
                    if title_prop.get("title"):
                        title = title_prop["title"][0]["plain_text"]
                
                if repo_path:
                    # Convert repo path to article key format
                    if repo_path.startswith("en_ta/"):
                        article_key = repo_path[6:]  # Remove "en_ta/" prefix
                        self.page_map[article_key] = {
                            "page_id": page["id"],
                            "title": title
                        }
                        logger.debug(f"Mapped {article_key} -> {title}")
            
            logger.info(f"Created mapping for {len(self.page_map)} articles")
            return True
            
        except Exception as e:
            logger.error(f"Error loading page mapping: {e}")
            return False
    
    def resolve_relative_path(self, current_path: str, relative_path: str) -> Optional[str]:
        """Resolve a relative path to an absolute article path."""
        try:
            # Remove /01.md suffix if present
            if relative_path.endswith("/01.md"):
                relative_path = relative_path[:-6]
            
            # Get current directory (section)
            current_parts = current_path.split("/")
            current_section = current_parts[0] if current_parts else ""
            
            # Resolve relative path
            if relative_path.startswith("../"):
                # Same section link - just replace with section/article
                article_name = relative_path[3:]  # Remove "../"
                resolved_path = f"{current_section}/{article_name}"
                
            elif relative_path.startswith("../../"):
                # Cross-section link - remove "../../" and use as-is
                resolved_path = relative_path[6:]  # Remove "../../"
                
            else:
                # Relative to current directory
                if current_parts:
                    resolved_path = f"{current_section}/{relative_path}"
                else:
                    resolved_path = relative_path
            
            # Clean up any double slashes and fix "../" patterns
            resolved_path = re.sub(r'/+', '/', resolved_path)
            resolved_path = re.sub(r'[^/]+/\.\./+', '', resolved_path)  # Remove "section/../" patterns
            
            # Remove leading slash if present
            if resolved_path.startswith("/"):
                resolved_path = resolved_path[1:]
            
            return resolved_path
            
        except Exception as e:
            logger.error(f"Error resolving path {relative_path} from {current_path}: {e}")
            return None
    
    def is_internal_link(self, url: str) -> bool:
        """Check if a URL is an internal link that should be replaced."""
        return (
            url.endswith("/01.md") or 
            (url.startswith("../") and "/01.md" not in url) or
            (url.startswith("../../") and "/01.md" not in url)
        )
    
    def is_image_url(self, url: str) -> bool:
        """Check if a URL is an image that should be embedded."""
        return url and re.search(r'\.(jpeg|jpg|gif|png|svg|webp)$', url.lower())
    
    def extract_markdown_images(self, text: str) -> List[Dict]:
        """Extract markdown image links from text."""
        # Pattern: ![caption](url)
        image_pattern = r'!\[(.*?)\]\((.*?)\)'
        images = []
        for match in re.finditer(image_pattern, text):
            caption = match.group(1)
            url = match.group(2)
            if self.is_image_url(url):
                images.append({
                    "caption": caption,
                    "url": url,
                    "match": match,
                    "full_match": match.group(0)
                })
        return images
    
    def get_page_content(self, page_id: str) -> List[Dict]:
        """Get all content blocks from a page."""
        try:
            blocks = []
            start_cursor = None
            
            while True:
                if start_cursor:
                    response = notion.blocks.children.list(
                        block_id=page_id,
                        start_cursor=start_cursor
                    )
                else:
                    response = notion.blocks.children.list(block_id=page_id)
                
                blocks.extend(response["results"])
                
                if not response["has_more"]:
                    break
                
                start_cursor = response["next_cursor"]
            
            return blocks
            
        except Exception as e:
            logger.error(f"Error getting page content for {page_id}: {e}")
            return []
    
    def update_rich_text_links(self, rich_text: List[Dict], current_path: str) -> Tuple[List[Dict], int, List[Dict]]:
        """Update links in rich text array and extract images for embedding."""
        updated_rich_text = []
        links_replaced = 0
        images_to_embed = []
        
        for item in rich_text:
            if item.get("type") == "text":
                text_obj = item.get("text", {})
                text_content = text_obj.get("content", "")
                link_obj = text_obj.get("link")
                
                # Check for markdown images in text content
                markdown_images = self.extract_markdown_images(text_content)
                if markdown_images:
                    # Remove markdown image syntax from text
                    updated_text = text_content
                    for img in markdown_images:
                        updated_text = updated_text.replace(img["full_match"], "")
                        images_to_embed.append(img)
                    
                    # Only keep the text item if there's remaining content
                    updated_text = updated_text.strip()
                    if updated_text:
                        updated_item = item.copy()
                        updated_item["text"]["content"] = updated_text
                        updated_rich_text.append(updated_item)
                elif link_obj and self.is_internal_link(link_obj["url"]):
                    # Resolve the relative path
                    resolved_path = self.resolve_relative_path(current_path, link_obj["url"])
                    
                    if resolved_path and resolved_path in self.page_map:
                        # Replace with Notion page link
                        target_page_id = self.page_map[resolved_path]["page_id"]
                        new_url = f"https://www.notion.so/{target_page_id.replace('-', '')}"
                        
                        # Update the link
                        updated_item = item.copy()
                        updated_item["text"]["link"]["url"] = new_url
                        updated_rich_text.append(updated_item)
                        
                        links_replaced += 1
                        logger.info(f"    Replaced: {link_obj['url']} -> {self.page_map[resolved_path]['title']}")
                    else:
                        # Keep original link if we can't resolve it
                        updated_rich_text.append(item)
                        if resolved_path:
                            logger.warning(f"    Could not find page for: {resolved_path}")
                else:
                    updated_rich_text.append(item)
            else:
                updated_rich_text.append(item)
        
        return updated_rich_text, links_replaced, images_to_embed
    
    def create_image_block(self, image_info: Dict) -> Dict:
        """Create a Notion image block from image information."""
        return {
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": image_info["url"]},
                "caption": [{"type": "text", "text": {"content": image_info["caption"]}}] if image_info["caption"] else []
            }
        }
    
    def check_and_update_block(self, block: Dict, current_path: str, page_id: str) -> Tuple[bool, List[Dict]]:
        """Check if a block needs updating and update it if necessary."""
        block_type = block.get("type")
        block_id = block.get("id")
        
        if not block_id:
            return False, []
        
        # Handle different block types with rich text
        rich_text = None
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
        elif block_type == "quote":
            rich_text = block.get("quote", {}).get("rich_text", [])
        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
        
        if not rich_text:
            return False, []
        
        # Check if this block has any internal links or images
        has_internal_links = False
        has_images = False
        
        for item in rich_text:
            if item.get("type") == "text":
                text_content = item.get("text", {}).get("content", "")
                link_obj = item.get("text", {}).get("link")
                
                # Check for markdown images
                if self.extract_markdown_images(text_content):
                    has_images = True
                    break
                
                # Check for internal links
                if link_obj and self.is_internal_link(link_obj["url"]):
                    has_internal_links = True
                    break
        
        if not has_internal_links and not has_images:
            return False, []
        
        # Update the links and extract images
        updated_rich_text, links_replaced, images_to_embed = self.update_rich_text_links(rich_text, current_path)
        image_blocks = []
        
        # Create image blocks for embedding
        if images_to_embed:
            for img in images_to_embed:
                image_blocks.append(self.create_image_block(img))
                logger.info(f"    Extracted image: {img['caption']} -> {img['url']}")
            self.total_images_embedded += len(images_to_embed)
        
        if links_replaced > 0 or images_to_embed:
            try:
                # Update the block with new rich text
                update_data = {
                    block_type: {
                        "rich_text": updated_rich_text
                    }
                }
                
                # Preserve other properties if they exist
                if block_type == "callout" and "icon" in block.get("callout", {}):
                    update_data["callout"]["icon"] = block["callout"]["icon"]
                if block_type == "callout" and "color" in block.get("callout", {}):
                    update_data["callout"]["color"] = block["callout"]["color"]
                
                notion.blocks.update(block_id=block_id, **update_data)
                
                if links_replaced > 0:
                    logger.info(f"    Updated block {block_id} with {links_replaced} link replacements")
                    self.total_links_replaced += links_replaced
                
                return True, image_blocks
                
            except Exception as e:
                logger.error(f"    Error updating block {block_id}: {e}")
                return False, []
        
        return False, []
    
    def update_page_links(self, page_id: str, current_path: str, title: str) -> bool:
        """Update links in a page - only touching blocks that need updates."""
        logger.info(f"Checking: {title}")
        
        try:
            # Get all blocks from the page
            blocks = self.get_page_content(page_id)
            
            if not blocks:
                logger.info(f"  No blocks found")
                return True
            
            # Check and update each block individually
            blocks_updated = 0
            all_image_blocks = []
            
            for i, block in enumerate(blocks):
                updated, image_blocks = self.check_and_update_block(block, current_path, page_id)
                if updated:
                    blocks_updated += 1
                    self.updated_blocks += 1
                    
                    # Collect image blocks to add after the current block
                    if image_blocks:
                        all_image_blocks.extend([(i + 1, image_blocks)])
                    
                    # Small delay to avoid rate limits
                    time.sleep(0.1)
            
            # Add image blocks to the page (in reverse order to maintain positions)
            for insert_position, image_blocks in reversed(all_image_blocks):
                try:
                    # Insert image blocks after the text block
                    if insert_position < len(blocks):
                        # Insert after specific block
                        after_block_id = blocks[insert_position - 1]["id"]
                        
                        # Add each image block individually to maintain order
                        for img_block in image_blocks:
                            notion.blocks.children.append(
                                block_id=page_id,
                                children=[img_block],
                                after=after_block_id
                            )
                            # Update after_block_id for the next image
                            time.sleep(0.1)
                    else:
                        # Append to end of page
                        notion.blocks.children.append(
                            block_id=page_id,
                            children=image_blocks
                        )
                    
                    time.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"  Error adding image blocks: {e}")
            
            if blocks_updated > 0:
                logger.info(f"  Updated {blocks_updated} blocks")
            else:
                logger.info(f"  No links to replace or images to embed")
            
            return True
                
        except Exception as e:
            logger.error(f"Error updating links in page {page_id}: {e}")
            return False
    
    def process_all_pages(self):
        """Process all pages in the database."""
        logger.info("Starting efficient link replacement process...")
        
        if not self.load_page_mapping():
            logger.error("Failed to load page mapping")
            return
        
        success_count = 0
        total_pages = len(self.page_map)
        
        for i, (article_path, page_info) in enumerate(self.page_map.items(), 1):
            logger.info(f"Processing ({i}/{total_pages}): {article_path}")
            
            try:
                if self.update_page_links(page_info["page_id"], article_path, page_info["title"]):
                    success_count += 1
                
                # Rate limiting between pages
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Error processing {article_path}: {e}")
                continue
        
        logger.info(f"Efficient link replacement complete:")
        logger.info(f"  Pages processed: {success_count}/{total_pages}")
        logger.info(f"  Blocks updated: {self.updated_blocks}")
        logger.info(f"  Total links replaced: {self.total_links_replaced}")
        logger.info(f"  Total images embedded: {self.total_images_embedded}")

def main():
    """Main function."""
    import sys
    
    # Simple test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        logger.info("Running in test mode...")
        replacer = EfficientLinkReplacer()
        
        # Test image extraction
        test_text = "Check out this image: ![Simple translation process flowchart](https://cdn.door43.org/ta/jpg/translation_process.png) and this link [translate](../translate-discover/01.md)."
        images = replacer.extract_markdown_images(test_text)
        print(f"Found {len(images)} images:")
        for img in images:
            print(f"  Caption: {img['caption']}")
            print(f"  URL: {img['url']}")
            
            # Test block creation
            block = replacer.create_image_block(img)
            print(f"  Block: {block['type']} with caption: {block['image']['caption']}")
        
        logger.info("Test mode completed!")
        return
    
    logger.info("Starting Translation Academy efficient link replacement...")
    
    replacer = EfficientLinkReplacer()
    replacer.process_all_pages()
    
    logger.info("Efficient link replacement process finished!")

if __name__ == "__main__":
    main()