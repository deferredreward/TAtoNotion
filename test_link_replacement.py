#!/usr/bin/env python3
"""
Test the link replacement logic on a few pages first.
"""

import os
import sys
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

# Import our link replacer
from replace_internal_links import LinkReplacer

def test_path_resolution():
    """Test the path resolution logic."""
    replacer = LinkReplacer()
    
    # Test cases
    test_cases = [
        ("checking/vol2-steps", "../alignment-tool/01.md", "checking/alignment-tool"),
        ("checking/vol2-steps", "../vol2-things-to-check/01.md", "checking/vol2-things-to-check"),
        ("checking/vol2-steps", "../../translate/translate-key-terms/01.md", "translate/translate-key-terms"),
        ("checking/vol2-things-to-check", "../../translate/figs-explicit/01.md", "translate/figs-explicit"),
    ]
    
    print("Testing path resolution:")
    for current_path, relative_path, expected in test_cases:
        result = replacer.resolve_relative_path(current_path, relative_path)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status} {current_path} + {relative_path} = {result} (expected: {expected})")

def test_on_sample_pages():
    """Test link replacement on a few sample pages."""
    replacer = LinkReplacer()
    
    # Load page mapping
    if not replacer.load_page_mapping():
        print("Failed to load page mapping")
        return
    
    print(f"Loaded {len(replacer.page_map)} pages")
    
    # Test on a few specific pages that we know have links
    test_pages = [
        "checking/vol2-things-to-check",
        "checking/vol2-steps"
    ]
    
    for article_path in test_pages:
        if article_path in replacer.page_map:
            page_info = replacer.page_map[article_path]
            print(f"\nTesting: {article_path} -> {page_info['title']}")
            
            # Just analyze, don't update yet
            blocks = replacer.get_page_content(page_info["page_id"])
            print(f"Found {len(blocks)} blocks")
            
            # Count links that would be replaced
            link_count = 0
            for block in blocks:
                _, links = replacer.update_block_links(block, article_path)
                link_count += links
            
            print(f"Would replace {link_count} links")
        else:
            print(f"Page not found: {article_path}")

if __name__ == "__main__":
    print("=== Testing Path Resolution ===")
    test_path_resolution()
    
    print("\n=== Testing on Sample Pages ===")
    test_on_sample_pages()