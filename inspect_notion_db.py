#!/usr/bin/env python3
"""
Script to inspect the Translation Academy Notion database structure
to understand the schema and properties available for migration.
"""

import os
import json
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("ERROR: NOTION_API_KEY not found in .env file")
    exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

# Database and page IDs from the URLs provided
TA_DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"
TA_WIP_PAGE_ID = "1c372d5af2de80e08b11cd7748a1467d"

def format_notion_id(id_str):
    """Format a Notion ID to the correct UUID format."""
    if len(id_str) == 36 and id_str.count('-') == 4:
        return id_str
    
    # Remove any existing dashes
    clean_id = id_str.replace('-', '')
    
    # Add dashes in the correct positions for UUID format
    if len(clean_id) == 32:
        formatted_id = f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
        return formatted_id
    
    return id_str

def inspect_database_schema():
    """Inspect the database schema to understand available properties."""
    try:
        database_id = format_notion_id(TA_DATABASE_ID)
        print(f"Inspecting database: {database_id}")
        
        # Get database schema
        database = notion.databases.retrieve(database_id=database_id)
        
        print("\n=== DATABASE SCHEMA ===")
        print(f"Title: {database.get('title', [{}])[0].get('plain_text', 'No title')}")
        print(f"ID: {database['id']}")
        
        print("\n=== PROPERTIES ===")
        properties = database.get('properties', {})
        
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get('type', 'unknown')
            print(f"\n{prop_name}:")
            print(f"  Type: {prop_type}")
            
            # Show additional details based on property type
            if prop_type == 'select':
                options = prop_info.get('select', {}).get('options', [])
                if options:
                    print(f"  Options: {[opt['name'] for opt in options]}")
            elif prop_type == 'multi_select':
                options = prop_info.get('multi_select', {}).get('options', [])
                if options:
                    print(f"  Options: {[opt['name'] for opt in options]}")
            elif prop_type == 'relation':
                database_id = prop_info.get('relation', {}).get('database_id')
                if database_id:
                    print(f"  Related database: {database_id}")
            elif prop_type == 'formula':
                expression = prop_info.get('formula', {}).get('expression')
                if expression:
                    print(f"  Formula: {expression}")
        
        return database
        
    except Exception as e:
        print(f"Error inspecting database: {e}")
        return None

def inspect_database_entries():
    """Get a few sample entries from the database to understand the data structure."""
    try:
        database_id = format_notion_id(TA_DATABASE_ID)
        
        # Query database for sample entries
        response = notion.databases.query(
            database_id=database_id,
            page_size=5  # Just get first 5 entries
        )
        
        print("\n=== SAMPLE DATABASE ENTRIES ===")
        
        for i, page in enumerate(response.get('results', []), 1):
            print(f"\n--- Entry {i} ---")
            print(f"ID: {page['id']}")
            
            properties = page.get('properties', {})
            for prop_name, prop_value in properties.items():
                prop_type = prop_value.get('type')
                
                # Extract value based on property type
                value = "N/A"
                if prop_type == 'title':
                    title_content = prop_value.get('title', [])
                    if title_content:
                        value = title_content[0].get('plain_text', '')
                elif prop_type == 'rich_text':
                    rich_text = prop_value.get('rich_text', [])
                    if rich_text:
                        value = rich_text[0].get('plain_text', '')
                elif prop_type == 'select':
                    select_value = prop_value.get('select')
                    if select_value:
                        value = select_value.get('name', '')
                elif prop_type == 'multi_select':
                    multi_select = prop_value.get('multi_select', [])
                    value = [item.get('name', '') for item in multi_select]
                elif prop_type == 'number':
                    value = prop_value.get('number', 0)
                elif prop_type == 'checkbox':
                    value = prop_value.get('checkbox', False)
                elif prop_type == 'relation':
                    relations = prop_value.get('relation', [])
                    value = [rel.get('id', '') for rel in relations]
                elif prop_type == 'url':
                    value = prop_value.get('url', '')
                elif prop_type == 'date':
                    date_info = prop_value.get('date')
                    if date_info:
                        value = date_info.get('start', '')
                
                print(f"  {prop_name} ({prop_type}): {value}")
        
        return response
        
    except Exception as e:
        print(f"Error querying database: {e}")
        return None

def inspect_wip_page():
    """Inspect the WIP page to understand its structure."""
    try:
        page_id = format_notion_id(TA_WIP_PAGE_ID)
        print(f"\n=== INSPECTING WIP PAGE: {page_id} ===")
        
        # Get page details
        page = notion.pages.retrieve(page_id=page_id)
        
        print(f"Page ID: {page['id']}")
        print(f"Created: {page.get('created_time', 'unknown')}")
        print(f"Last edited: {page.get('last_edited_time', 'unknown')}")
        
        # Get page content (blocks)
        blocks_response = notion.blocks.children.list(block_id=page_id, page_size=20)
        
        print("\n=== PAGE CONTENT STRUCTURE ===")
        for i, block in enumerate(blocks_response.get('results', []), 1):
            block_type = block.get('type', 'unknown')
            print(f"\nBlock {i}: {block_type}")
            print(f"  ID: {block['id']}")
            
            # Show content based on block type
            if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3']:
                rich_text = block.get(block_type, {}).get('rich_text', [])
                if rich_text:
                    text = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                    print(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")
            elif block_type == 'child_page':
                title = block.get('child_page', {}).get('title', '')
                print(f"  Child page: {title}")
            elif block_type == 'child_database':
                title = block.get('child_database', {}).get('title', '')
                print(f"  Child database: {title}")
        
        return page
        
    except Exception as e:
        print(f"Error inspecting WIP page: {e}")
        return None

def main():
    """Main function to run all inspections."""
    print("=== NOTION DATABASE INSPECTION ===")
    
    # Inspect database schema
    database = inspect_database_schema()
    
    # Inspect sample database entries
    entries = inspect_database_entries()
    
    # Inspect WIP page
    wip_page = inspect_wip_page()
    
    # Save results to JSON for further analysis
    results = {
        'database_schema': database,
        'sample_entries': entries,
        'wip_page': wip_page
    }
    
    with open('notion_inspection_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n=== INSPECTION COMPLETE ===")
    print("Results saved to: notion_inspection_results.json")

if __name__ == "__main__":
    main()