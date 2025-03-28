import os
import sys
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("Error: NOTION_API_KEY not found in .env file")
    sys.exit(1)

# Format the page ID properly (Notion expects dashes in specific places)
def format_notion_id(id_str):
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
print(f"Original Page ID: {RAW_NOTION_ID}")
print(f"Formatted Page ID: {NOTION_PARENT_PAGE_ID}")

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def list_user_pages():
    """List all pages the integration has access to."""
    try:
        # First try to list any search results to see what we can access
        search_results = notion.search()
        
        print("\nPages and databases accessible to this integration:")
        if search_results["results"]:
            for i, item in enumerate(search_results["results"]):
                item_type = item["object"]
                item_id = item["id"]
                title = "Untitled"
                
                # Try to extract title based on object type
                if item_type == "page" and "title" in item.get("properties", {}):
                    title_obj = item["properties"]["title"]
                    if "title" in title_obj and title_obj["title"]:
                        title = title_obj["title"][0]["plain_text"]
                elif item_type == "database":
                    title = item.get("title", [{"plain_text": "Untitled"}])[0]["plain_text"]
                    
                print(f"{i+1}. {item_type.capitalize()}: {title} (ID: {item_id})")
                
                # If it's a page, try to get a URL
                if "url" in item:
                    print(f"   URL: {item['url']}")
        else:
            print("No pages found. Make sure your integration has access to the pages.")
        
        return search_results["results"]
    except Exception as e:
        print(f"Error listing pages: {str(e)}")
        return []

def test_notion_connection():
    """Test connection to Notion API."""
    try:
        # Try to fetch the parent page to test connection
        print(f"\nTesting connection to Notion and trying to retrieve page: {NOTION_PARENT_PAGE_ID}")
        parent_page = notion.pages.retrieve(page_id=NOTION_PARENT_PAGE_ID)
        print("✓ Successfully connected to Notion API!")
        
        # Try to extract the page title
        if "properties" in parent_page and "title" in parent_page["properties"]:
            title_obj = parent_page["properties"]["title"]
            if "title" in title_obj and title_obj["title"]:
                title = title_obj["title"][0]["plain_text"]
                print(f"Page title: {title}")
            else:
                print("Page has no title")
        else:
            print("Could not extract title information")
        
        return True
    except APIResponseError as e:
        print(f"\n✗ Error connecting to Notion API: {str(e)}")
        print("\nThis could be due to:")
        print("1. Incorrect page ID format")
        print("2. The page doesn't exist")
        print("3. Your Notion integration doesn't have access to this page")
        print("\nMake sure that:")
        print("- Your integration is added to the page (Share button > Add connections > [your integration])")
        print("- The page ID is correct")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {str(e)}")
        return False

def test_create_simple_page_in_workspace():
    """Create a simple page in the workspace root (no parent)."""
    print("\nTrying to create a page in the workspace root...")
    try:
        # Create a page without specifying a parent (will go to workspace root)
        page_data = {
            "parent": {"workspace": True},
            "properties": {
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": "Test Page in Workspace Root"
                            }
                        }
                    ]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "This is a test page created in the workspace root."
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        response = notion.pages.create(**page_data)
        print(f"✓ Successfully created test page in workspace root with ID: {response['id']}")
        print(f"Page URL: {response['url']}")
        return response['id']
    except Exception as e:
        print(f"✗ Failed to create page in workspace root: {str(e)}")
        return None

def test_create_simple_page(parent_id=None):
    """Test creating a simple page in Notion under the specified parent."""
    if parent_id is None:
        parent_id = NOTION_PARENT_PAGE_ID
    
    print(f"\nTrying to create a page under parent: {parent_id}")
    try:
        # Create a simple test page
        page_data = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": "Test Page from Python Script"
                            }
                        }
                    ]
                }
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "This is a test page created by the Python script to verify Notion API functionality."
                                }
                            }
                        ]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Test Heading"
                                }
                            }
                        ]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "This test was successful if you can see this page in your Notion workspace."
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        response = notion.pages.create(**page_data)
        print(f"✓ Successfully created test page with ID: {response['id']}")
        print(f"Page URL: {response['url']}")
        return response['id']
    except Exception as e:
        print(f"✗ Error creating Notion page: {str(e)}")
        return None

if __name__ == "__main__":
    print("=== Notion API Connection Test ===")
    print(f"API Key (first 5 chars): {NOTION_API_KEY[:5]}...")
    
    # First, check what pages we have access to
    available_pages = list_user_pages()
    
    # Start by trying to create a page in the workspace root
    print("\nFirst, let's try creating a page in the workspace root")
    workspace_page_id = test_create_simple_page_in_workspace()
    
    if workspace_page_id:
        print("\nSuccess! Now trying to create a child page under the new workspace page...")
        child_page_id = test_create_simple_page(workspace_page_id)
        
        if child_page_id:
            print("\nSuccess creating child page! Your Notion integration is working correctly.")
            print("\nNow trying to use the specified Translation Academy page ID...")
    
    # Test connection to the specified page
    connection_success = test_notion_connection()
    
    if connection_success:
        print("\nTrying to create a test page under the Translation Academy page...")
        ta_page_id = test_create_simple_page()
        if ta_page_id:
            print("\nSuccess! Your setup is complete and ready to import articles.")
        else:
            print("\nFailed to create page under Translation Academy. Check the permissions.")
    else:
        print("\nFailed to connect to Translation Academy page. Please make sure:")
        print("1. The page ID is correct")
        print("2. You've shared the page with your integration")
        print("   (In Notion: open the page → Share → Add connections → select your integration)")
        print("3. You've given your integration the appropriate permissions") 