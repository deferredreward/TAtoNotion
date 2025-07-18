#!/usr/bin/env python3
"""
Check what relationships exist and what's missing for migrated articles
"""

from ta_to_notion_complete import CompleteTAMigrator
import json

def main():
    migrator = CompleteTAMigrator()
    migrator.load_all_data()
    
    # Load the existing database mappings
    with open('relationship_update_results.json', 'r') as f:
        results = json.load(f)
    
    existing_articles = set(results['article_to_page_mapping'].keys())
    
    print("🔍 RELATIONSHIP ANALYSIS")
    print("=" * 50)
    
    for article_key in existing_articles:
        if article_key in migrator.articles_data:
            info = migrator.articles_data[article_key]
            relationships = info['relationships']
            
            print(f"\n📄 {article_key}")
            print(f"   Title: {info['content']['title']}")
            
            # Check dependencies
            deps = relationships['dependencies']
            if deps:
                print(f"   📋 Dependencies ({len(deps)}):")
                for dep in deps:
                    dep_key = f"translate/{dep}"  # Try translate section first
                    if dep_key not in existing_articles:
                        # Try other sections
                        found = False
                        for section in ['intro', 'process', 'checking']:
                            dep_key = f"{section}/{dep}"
                            if dep_key in existing_articles:
                                found = True
                                break
                        if found:
                            print(f"      ✅ {dep} (linked)")
                        else:
                            print(f"      ❌ {dep} (missing)")
                    else:
                        print(f"      ✅ {dep} (linked)")
            
            # Check recommendations
            recs = relationships['recommended']
            if recs:
                print(f"   🔗 Recommended ({len(recs)}):")
                for rec in recs:
                    rec_key = f"translate/{rec}"  # Try translate section first
                    if rec_key not in existing_articles:
                        # Try other sections
                        found = False
                        for section in ['intro', 'process', 'checking']:
                            rec_key = f"{section}/{rec}"
                            if rec_key in existing_articles:
                                found = True
                                break
                        if found:
                            print(f"      ✅ {rec} (linked)")
                        else:
                            print(f"      ❌ {rec} (missing)")
                    else:
                        print(f"      ✅ {rec} (linked)")
    
    print(f"\n📊 SUMMARY")
    print(f"   Total articles in database: {len(existing_articles)}")
    print(f"   Articles analyzed: {len([k for k in existing_articles if k in migrator.articles_data])}")

if __name__ == "__main__":
    main()