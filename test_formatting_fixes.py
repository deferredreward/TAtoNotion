#!/usr/bin/env python3
"""
Test the formatting fixes on a few sample pages first.
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

# Import our formatter
from fix_formatting_issues import FormattingFixer

def test_html_tag_cleaning():
    """Test HTML tag cleaning logic."""
    fixer = FormattingFixer()
    
    test_cases = [
        ("the day I choose in early autumn<sup>1</sup> you must humble", "the day I choose in early autumn[1] you must humble"),
        ("<sup> [1]</sup> The Hebrew says", "[1] The Hebrew says"),
        ("Some text <sup>2</sup> more text", "Some text [2] more text"),
        ("Normal text without tags", "Normal text without tags"),
        ("<sup>  3  </sup>", "[3]"),
    ]
    
    print("Testing HTML tag cleaning:")
    for input_text, expected in test_cases:
        result = fixer.clean_html_tags(input_text)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status}: '{input_text}' -> '{result}' (expected: '{expected}')")

def test_on_sample_pages():
    """Test formatting fixes on a few sample pages."""
    fixer = FormattingFixer()
    
    # Get a few sample pages
    try:
        response = notion.databases.query(
            database_id=DATABASE_ID,
            page_size=5
        )
        
        pages = response["results"]
        print(f"\nTesting formatting fixes on {len(pages)} sample pages:")
        
        for page in pages:
            title = ""
            if "Title" in page["properties"]:
                title_prop = page["properties"]["Title"]
                if title_prop.get("title"):
                    title = title_prop["title"][0]["plain_text"]
            
            print(f"\n--- {title} ---")
            
            # Get page content
            blocks = fixer.get_page_content(page["id"])
            print(f"Found {len(blocks)} blocks")
            
            # Analyze what would be fixed (without actually fixing)
            issues_found = []
            
            for block in blocks:
                block_type = block.get("type")
                
                if block_type == "quote":
                    rich_text = block.get("quote", {}).get("rich_text", [])
                    
                    # Check for empty quotes
                    if not rich_text or all(not item.get("text", {}).get("content", "").strip() for item in rich_text):
                        issues_found.append("Empty quote block")
                    else:
                        # Check for HTML tags
                        for item in rich_text:
                            if item.get("type") == "text":
                                content = item.get("text", {}).get("content", "")
                                if "<sup>" in content or "</sup>" in content:
                                    issues_found.append("HTML tags in quote")
                
                elif block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                    rich_text = block.get(block_type, {}).get("rich_text", [])
                    for item in rich_text:
                        if item.get("type") == "text":
                            content = item.get("text", {}).get("content", "")
                            if "<sup>" in content or "</sup>" in content:
                                issues_found.append(f"HTML tags in {block_type}")
            
            if issues_found:
                print(f"Would fix: {', '.join(set(issues_found))}")
            else:
                print("No formatting issues found")
    
    except Exception as e:
        print(f"Error testing pages: {e}")

def test_rich_text_fixing():
    """Test rich text fixing logic."""
    fixer = FormattingFixer()
    
    # Test rich text with HTML tags
    test_rich_text = [
        {
            "type": "text",
            "text": {
                "content": "the day I choose in early autumn<sup>1</sup> you must humble"
            }
        }
    ]
    
    print("\nTesting rich text fixing:")
    fixed_rich_text, issues_fixed = fixer.fix_rich_text_formatting(test_rich_text)
    
    print(f"Original: {test_rich_text[0]['text']['content']}")
    print(f"Fixed: {fixed_rich_text[0]['text']['content']}")
    print(f"Issues fixed: {issues_fixed}")

if __name__ == "__main__":
    print("=== Testing HTML Tag Cleaning ===")
    test_html_tag_cleaning()
    
    print("\n=== Testing Rich Text Fixing ===")
    test_rich_text_fixing()
    
    print("\n=== Testing on Sample Pages ===")
    test_on_sample_pages()