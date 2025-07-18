import os
import sys
import csv
import json
import logging
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tsv_to_notion_db.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("Error: NOTION_API_KEY not found in .env file")
    sys.exit(1)

# Database ID from the URL: https://www.notion.so/unfoldingword/340b5f5c4f574a6abd215e5b30aac26c
DATABASE_ID = "340b5f5c4f574a6abd215e5b30aac26c"

# Initialize Notion client
notion = Client(auth=NOTION_API_KEY)

def format_notion_id(id_str):
    """Format the page ID properly (Notion expects dashes in specific places)."""
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

def get_database_structure():
    """Get the current structure of the database."""
    try:
        database = notion.databases.retrieve(database_id=DATABASE_ID)
        print("Current database properties:")
        for prop_name, prop_info in database["properties"].items():
            print(f"  {prop_name}: {prop_info['type']}")
        return database
    except Exception as e:
        print(f"Error retrieving database: {str(e)}")
        return None

def read_tsv_file(file_path):
    """Read the TSV file and return headers and data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            # Use csv.reader with tab delimiter
            reader = csv.reader(file, delimiter='\t')
            headers = next(reader)  # First row is headers
            data = list(reader)
            
            print(f"TSV file has {len(headers)} columns:")
            for i, header in enumerate(headers):
                print(f"  {i+1}. {header}")
            
            print(f"TSV file has {len(data)} rows of data")
            return headers, data
    except Exception as e:
        print(f"Error reading TSV file: {str(e)}")
        return None, None

def determine_property_type(column_name, sample_values):
    """Determine the best Notion property type for a column based on its content."""
    # Remove empty values for analysis
    non_empty_values = [v for v in sample_values if v and v.strip()]
    
    if not non_empty_values:
        return "rich_text"  # Default for empty columns
    
    # Check for URL patterns
    if any(v.startswith(('http://', 'https://')) for v in non_empty_values):
        return "url"
    
    # Check for numbers
    if all(v.replace('.', '').replace('-', '').isdigit() for v in non_empty_values):
        return "number"
    
    # Check for long text (more than 200 characters typically)
    if any(len(v) > 200 for v in non_empty_values):
        return "rich_text"
    
    # Default to rich_text for most text content
    return "rich_text"

def add_properties_to_database(headers, data):
    """Add new properties to the database based on TSV columns."""
    try:
        # Get current database structure
        database = get_database_structure()
        if not database:
            return False
        
        current_properties = database["properties"]
        
        # Analyze each column to determine property type
        new_properties = {}
        
        for i, header in enumerate(headers):
            if header in current_properties:
                print(f"Property '{header}' already exists, skipping...")
                continue
            
            # Get sample values from this column
            sample_values = [row[i] if i < len(row) else "" for row in data[:10]]  # First 10 rows
            
            # Determine property type
            prop_type = determine_property_type(header, sample_values)
            
            if prop_type == "rich_text":
                new_properties[header] = {
                    "rich_text": {}
                }
            elif prop_type == "url":
                new_properties[header] = {
                    "url": {}
                }
            elif prop_type == "number":
                new_properties[header] = {
                    "number": {}
                }
            else:
                new_properties[header] = {
                    "rich_text": {}
                }
            
            print(f"Will add property '{header}' as type '{prop_type}'")
        
        if not new_properties:
            print("No new properties to add")
            return True
        
        # Add new properties to database
        for prop_name, prop_config in new_properties.items():
            try:
                # Update database with new property
                update_data = {
                    "properties": {
                        prop_name: prop_config
                    }
                }
                
                notion.databases.update(database_id=DATABASE_ID, **update_data)
                # Get the actual type from the config
                actual_type = list(prop_config.keys())[0]
                print(f"Added property '{prop_name}' ({actual_type})")
                
            except Exception as e:
                print(f"Failed to add property '{prop_name}': {str(e)}")
                return False
        
        return True
        
    except Exception as e:
        print(f"Error adding properties: {str(e)}")
        return False

def get_database_items():
    """Get all items from the database."""
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
        return items
        
    except Exception as e:
        print(f"Error getting database items: {str(e)}")
        return []

def find_matching_item(item, tsv_row, headers):
    """Find if a database item matches a TSV row based on title or topic."""
    try:
        # Get the title from the item
        title_prop = item.get("properties", {}).get("Title", {})
        
        if title_prop and title_prop.get("title"):
            item_title = title_prop["title"][0]["plain_text"]
        else:
            return False, "No title found in database item"
        
        # Get Topic translationAcademy from TSV (second column)
        if len(headers) > 1 and headers[1] == "Topic translationAcademy" and len(tsv_row) > 1:
            topic = tsv_row[1].strip()
            if not topic:
                return False, "Empty topic in TSV"
            
            # Try exact match first
            if topic.lower() == item_title.lower():
                return True, "Exact match"
            
            # Also check for partial matches (some topics might have slight variations)
            if topic and item_title:
                # Remove common prefixes/suffixes for comparison
                topic_clean = topic.replace("https://git.door43.org/tim/en_ta/src/branch/master/translate/", "").replace("/01.md", "")
                topic_clean = topic_clean.replace("https://git.door43.org/unfoldingWord/en_ta/src/branch/master/translate/", "").replace("/01.md", "")
                
                # Check if cleaned topic matches title
                if topic_clean.lower() == item_title.lower():
                    return True, "Cleaned match"
                
                # Check for common variations
                if "rhetorical question" in item_title.lower() and "rhetorical question" in topic.lower():
                    return True, "Rhetorical question special case"
                
                if "hyperbole" in item_title.lower() and ("hyperbole" in topic.lower() or "generalization" in topic.lower()):
                    return True, "Hyperbole special case"
                
                # No match found - return details for logging
                return False, f"No match: TSV topic '{topic}' (cleaned: '{topic_clean}') vs DB title '{item_title}'"
        
        return False, "Invalid TSV format or missing topic column"
        
    except Exception as e:
        logger.error(f"Error matching item: {str(e)}")
        return False, f"Error: {str(e)}"

def update_item_with_tsv_data(item_id, tsv_row, headers):
    """Update a database item with data from TSV row."""
    try:
        # Build properties update
        properties_update = {}
        
        for i, header in enumerate(headers):
            if i < len(tsv_row) and tsv_row[i].strip():
                value = tsv_row[i].strip()
                
                # Skip empty values
                if not value or value == "XXXXX":
                    continue
                
                # Determine how to format the property based on its type
                if header.startswith("http") or "docs.google.com" in value:
                    # URL property
                    properties_update[header] = {
                        "url": value
                    }
                else:
                    # Rich text property
                    properties_update[header] = {
                        "rich_text": [
                            {
                                "text": {
                                    "content": value
                                }
                            }
                        ]
                    }
        
        if properties_update:
            notion.pages.update(page_id=item_id, properties=properties_update)
            print(f"Updated item {item_id} with {len(properties_update)} properties")
            return True
        else:
            print(f"No valid data to update for item {item_id}")
            return False
            
    except Exception as e:
        print(f"Error updating item {item_id}: {str(e)}")
        return False

def process_tsv_to_database():
    """Main function to process TSV file and update database."""
    tsv_file_path = "Translation Aid GLT_GST_GTN_OL Learner Outcome rubric COMPLETE.xlsx - tA Index.tsv"
    
    logger.info("=== TSV to Notion Database Processor ===")
    
    # Read TSV file
    headers, data = read_tsv_file(tsv_file_path)
    if not headers or not data:
        return
    
    # Get current database structure
    logger.info("\n--- Current Database Structure ---")
    database = get_database_structure()
    if not database:
        return
    
    # Add new properties to database
    logger.info("\n--- Adding New Properties ---")
    if not add_properties_to_database(headers, data):
        logger.error("Failed to add properties to database")
        return
    
    # Get all database items
    logger.info("\n--- Getting Database Items ---")
    items = get_database_items()
    if not items:
        logger.error("No items found in database")
        return
    
    # Create a lookup of database items by title for easier analysis
    db_titles = {}
    for item in items:
        title_prop = item.get("properties", {}).get("Title", {})
        if title_prop and title_prop.get("title"):
            title = title_prop["title"][0]["plain_text"]
            db_titles[title.lower()] = title
    
    # Update items with TSV data
    logger.info("\n--- Updating Items with TSV Data ---")
    updated_count = 0
    no_match_count = 0
    no_match_details = []
    
    for row_idx, row in enumerate(data, 1):
        # Skip empty rows
        if not any(cell.strip() for cell in row):
            continue
        
        # Get TSV topic for logging
        tsv_topic = row[1].strip() if len(row) > 1 else "Unknown"
        
        # Find matching item in database
        matching_item = None
        match_reason = None
        
        for item in items:
            is_match, reason = find_matching_item(item, row, headers)
            if is_match:
                matching_item = item
                match_reason = reason
                break
        
        if matching_item:
            item_id = matching_item["id"]
            # Get item title for logging
            title_prop = matching_item.get("properties", {}).get("Title", {})
            item_title = title_prop["title"][0]["plain_text"] if title_prop and title_prop.get("title") else "Unknown"
            
            if update_item_with_tsv_data(item_id, row, headers):
                updated_count += 1
                logger.info(f"Updated '{item_title}' (matched: {match_reason})")
        else:
            no_match_count += 1
            # Get detailed mismatch info
            mismatch_info = {
                "row": row_idx,
                "tsv_topic": tsv_topic,
                "tsv_first_col": row[0] if len(row) > 0 else "",
                "available_titles": list(db_titles.values())[:5]  # Show first 5 for context
            }
            no_match_details.append(mismatch_info)
            logger.warning(f"No match for row {row_idx}: TSV topic '{tsv_topic}'")
    
    # Generate comprehensive mismatch report
    logger.info("\n=== MISMATCH REPORT ===")
    logger.info(f"Total TSV rows processed: {len(data)}")
    logger.info(f"Successfully matched: {updated_count}")
    logger.info(f"No matches found: {no_match_count}")
    
    if no_match_details:
        logger.info("\n--- DETAILED MISMATCH ANALYSIS ---")
        logger.info("Current matching logic:")
        logger.info("  1. Exact match: TSV 'Topic translationAcademy' == DB 'Title'")
        logger.info("  2. Cleaned match: Remove URL prefixes/suffixes")
        logger.info("  3. Special cases: 'rhetorical question', 'hyperbole'")
        logger.info("")
        
        logger.info("UNMATCHED TSV ENTRIES:")
        for detail in no_match_details:
            logger.info(f"  Row {detail['row']}: '{detail['tsv_topic']}'")
            if detail['tsv_first_col']:
                logger.info(f"    First column: '{detail['tsv_first_col']}'")
        
        logger.info("\nAVAILABLE DATABASE TITLES (sample):")
        for title in sorted(db_titles.values())[:10]:
            logger.info(f"  '{title}'")
        
        logger.info(f"\nTotal database titles: {len(db_titles)}")
        
        # Save detailed report to file
        with open("tsv_mismatch_report.json", "w") as f:
            json.dump({
                "summary": {
                    "total_tsv_rows": len(data),
                    "matched": updated_count,
                    "unmatched": no_match_count
                },
                "unmatched_details": no_match_details,
                "database_titles": list(db_titles.values())
            }, f, indent=2)
        
        logger.info("\nDetailed mismatch report saved to: tsv_mismatch_report.json")
    
    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"Updated {updated_count} items with TSV data")
    logger.info(f"Could not match {no_match_count} TSV entries")

if __name__ == "__main__":
    process_tsv_to_database()