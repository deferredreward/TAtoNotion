#!/usr/bin/env python3
"""
Test script to verify database connection and migrate a few sample articles
"""

import os
from dotenv import load_dotenv
from notion_client import Client
from ta_to_notion_db_migration import TAMigrator

# Load environment variables
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
notion = Client(auth=NOTION_API_KEY)

# Test database connection first
DATABASE_ID = "340b5f5c-4f57-4a6a-bd21-5e5b30aac26c"

def test_database_connection():
    """Test if we can now access the database."""
    try:
        database = notion.databases.retrieve(database_id=DATABASE_ID)
        print("✅ Database connection successful!")
        
        print(f"Database title: {database.get('title', [{}])[0].get('plain_text', 'No title')}")
        
        properties = database.get('properties', {})
        print(f"\nDatabase properties ({len(properties)}):")
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get('type', 'unknown')
            print(f"  - {prop_name}: {prop_type}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_sample_migration():
    """Test migration with just a few articles."""
    print("\n" + "="*50)
    print("Testing sample migration...")
    
    migrator = TAMigrator()
    
    # Load all data first
    migrator.load_all_data()
    
    if not migrator.articles_data:
        print("❌ No articles loaded")
        return
    
    print(f"✅ Loaded {len(migrator.articles_data)} articles")
    
    # Test with first 3 articles
    sample_articles = list(migrator.articles_data.items())[:3]
    
    print(f"\nTesting with {len(sample_articles)} sample articles:")
    for key, info in sample_articles:
        article = info['content']
        print(f"  - {key}: {article['title']}")
    
    # Try to migrate these samples
    success_count = 0
    for article_key, article_info in sample_articles:
        article_data = article_info['content']
        relationships = article_info['relationships']
        
        print(f"\nMigrating: {article_key}")
        page_id = migrator.create_database_entry(article_data, relationships)
        
        if page_id:
            print(f"  ✅ Success: {page_id}")
            success_count += 1
        else:
            print(f"  ❌ Failed")
    
    print(f"\n📊 Sample migration results: {success_count}/{len(sample_articles)} successful")
    return success_count > 0

if __name__ == "__main__":
    print("🧪 Testing Translation Academy migration...")
    
    # Test database connection
    if test_database_connection():
        # Test sample migration
        test_sample_migration()
    else:
        print("Cannot proceed without database connection.")