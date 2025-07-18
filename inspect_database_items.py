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

def inspect_database_items():
    """Inspect the actual items in the database to understand their structure."""
    try:
        items = []
        start_cursor = None
        
        while True:
            query_params = {
                "database_id": DATABASE_ID,
                "page_size": 100
            }
            
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = notion.databases.query(**query_params)
            items.extend(response["results"])
            
            if not response["has_more"]:
                break
            
            start_cursor = response["next_cursor"]
        
        print(f"Found {len(items)} items in database")
        print("\n=== Database Items ===")
        
        for i, item in enumerate(items):
            print(f"\n--- Item {i+1} ---")
            
            # Get title
            title_prop = item.get("properties", {}).get("Title", {})
            if title_prop and title_prop.get("title"):
                title = title_prop["title"][0]["plain_text"]
                print(f"Title: {title}")
            
            # Get slug
            slug_prop = item.get("properties", {}).get("Slug", {})
            if slug_prop and slug_prop.get("rich_text"):
                slug = slug_prop["rich_text"][0]["plain_text"] if slug_prop["rich_text"] else ""
                print(f"Slug: {slug}")
            
            # Get other relevant properties
            for prop_name in ["Status", "Manual", "Content Type", "Repository Path"]:
                prop = item.get("properties", {}).get(prop_name, {})
                if prop:
                    if prop.get("select"):
                        print(f"{prop_name}: {prop['select']['name']}")
                    elif prop.get("rich_text"):
                        text = prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
                        print(f"{prop_name}: {text}")
        
    except Exception as e:
        print(f"Error inspecting database: {str(e)}")

if __name__ == "__main__":
    inspect_database_items()