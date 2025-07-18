# Translation Academy to Notion Migration Scripts

This repository contains scripts for migrating Translation Academy content from Gitea to a Notion database, with comprehensive processing and enhancement tools.

## Overview

The migration process transforms Translation Academy markdown files from the Gitea repository into a fully structured Notion database with:
- **Complete content coverage** (intro, translate, process, checking sections)
- Rich content formatting
- Cross-references and relationships
- TSV data enrichment
- Internal link connections
- Image embedding
- Formatting cleanup

## Migration Process

### Step 1: Content Migration
**Script:** `migration_v8.py`

Migrates all Translation Academy articles from Gitea to Notion database.

**Options:**
- `--test`: Process only test articles from `test_articles.txt`
- `--all`: Process all articles (default)

**Usage:**
```bash
./venv/Scripts/python.exe migration_v8.py --all
```

**What it does:**
- Discovers all articles in intro, translate, process, and checking sections
- **NEW:** Includes intro section with 8 foundational articles (ta-intro, translate-why, uw-intro, etc.)
- Processes articles in batches of 5 for API efficiency
- Converts markdown to Notion blocks with proper formatting
- Handles quotes, lists, headings, and rich text
- Creates database entries with metadata
- Fixes empty quote blocks with space placeholders
- Rate limits to respect API constraints

### Step 2: TSV Data Enrichment
**Script:** `tsv_to_notion_db.py`

Adds learner outcomes, lesson plans, and examples from TSV file to database.

**Usage:**
```bash
./venv/Scripts/python.exe tsv_to_notion_db.py
```

**What it does:**
- Reads `Translation Aid GLT_GST_GTN_OL Learner Outcome rubric COMPLETE.xlsx - tA Index.tsv`
- Adds new properties to database based on TSV columns
- Matches existing articles by title/topic
- Updates matched articles with TSV data
- Adds Module Tracking #, GLT/GST/GLTN/OL Learner Outcomes, Lesson Plans, Examples

### Step 3: Relationship Building
**Script:** `update_relationships.py`

Establishes connections between articles based on YAML configuration.

**Usage:**
```bash
./venv/Scripts/python.exe update_relationships.py        # All articles (default)
./venv/Scripts/python.exe update_relationships.py --test # Test articles only
```

**Options:**
- `--test`: Process only test articles from `test_articles.txt`
- `--all`: Process all articles (default behavior)
- `--articles`: Process specific articles

**What it does:**
- Loads YAML configuration from all sections
- Creates prerequisite relationships
- Establishes parent-child relationships
- Links related topics
- Builds comprehensive knowledge graph

### Step 4: Internal Link Replacement & Image Embedding
**Script:** `efficient_link_replacer.py`

Converts relative file links to proper Notion page links and embeds images from markdown.

**Usage:**
```bash
./venv/Scripts/python.exe efficient_link_replacer.py
```

**What it does:**
- Maps all articles to their Notion page IDs
- Resolves relative paths (../article, ../../section/article)
- Replaces markdown links with Notion page links
- **NEW:** Detects markdown images `![caption](url)` and converts to Notion image embeds
- **NEW:** Supports image formats: jpeg, jpg, gif, png, svg, webp
- Only updates blocks that contain internal links or images
- Preserves all formatting and structure
- Adds image blocks with captions directly to pages

### Step 5: Formatting Cleanup (Optional)
**Script:** `comprehensive_formatting_fixer.py`

Cleans up HTML tags and formatting issues.

**Usage:**
```bash
./venv/Scripts/python.exe comprehensive_formatting_fixer.py
```

**What it does:**
- Converts HTML `<sup>` tags to Unicode superscript
- Removes `<br>` tags and converts to line breaks
- Fixes empty quote blocks
- Removes other HTML remnants
- Normalizes whitespace

## Complete Migration Sequence

Run these scripts in order:

```bash
# 1. Migrate all content
./venv/Scripts/python.exe migration_v8.py --all

# 2. Add TSV data enrichment
./venv/Scripts/python.exe tsv_to_notion_db.py

# 3. Build relationships
./venv/Scripts/python.exe update_relationships.py

# 4. Replace internal links
./venv/Scripts/python.exe efficient_link_replacer.py

# 5. Clean up formatting (optional)
./venv/Scripts/python.exe comprehensive_formatting_fixer.py
```

## Configuration

### Environment Variables
Create a `.env` file with:
```
NOTION_API_KEY=your_notion_api_key_here
GITEA_API_KEY=your_gitea_api_key_here
```

### Database ID
The Notion database ID is hardcoded in scripts: `340b5f5c4f574a6abd215e5b30aac26c`

### Test Articles
Edit `test_articles.txt` to modify which articles are processed in test mode.

## Key Features

### Batch Processing
- Articles processed in batches of 5 to avoid API rate limits
- Configurable delays between requests
- Comprehensive error handling and retry logic

### Rich Content Support
- Markdown to Notion block conversion
- Bold, italic, and link formatting preserved
- Quote blocks with proper nesting
- Numbered and bulleted lists
- Multiple heading levels

### Link Resolution & Image Embedding
- Relative path resolution (../article, ../../section/article)
- Cross-section link support
- Automatic Notion page URL generation
- **NEW:** Markdown image detection and embedding `![caption](url)`
- **NEW:** Automatic image block creation with captions
- Efficient block-level updates

### Relationship Management
- YAML-based configuration
- Prerequisite chains
- Parent-child hierarchies
- Related topic networks

### Data Enrichment
- TSV file integration
- Learner outcome mapping
- Lesson plan associations
- Example connections

## Monitoring and Logging

All scripts generate comprehensive logs:
- `migration_v8.log` - Content migration details
- `tsv_to_notion_db.log` - TSV processing results
- `update_relationships.log` - Relationship building progress
- `efficient_link_replacement.log` - Link replacement activity
- `comprehensive_formatting_fix.log` - Formatting cleanup results

## Database Structure

The Notion database includes these key properties:
- **Title**: Article title
- **Slug**: URL-friendly identifier
- **Repository Path**: Original file location
- **Status**: Processing status
- **Manual**: Source manual (Translation/Process/Checking)
- **Content Type**: Module/Topic/etc.
- **Prerequisites**: Relation to prerequisite articles
- **Related Topics**: Relation to related articles
- **Parent Section**: Hierarchical relationships
- **Module Tracking #**: From TSV data
- **GLT/GST/GLTN/OL Learner Outcomes**: From TSV data
- **Lesson Plan**: URL to lesson plan
- **Examples**: Example references

## Performance Considerations

- **Migration**: ~5 minutes per 100 articles
- **TSV Processing**: ~30 seconds for 241 articles
- **Relationship Building**: ~2 minutes for 241 articles
- **Link Replacement & Image Embedding**: ~2 minutes for 241 articles
- **Formatting Cleanup**: ~3 minutes for 241 articles

Total time for complete migration: ~15-20 minutes for 241 articles

## Troubleshooting

### Common Issues

1. **Rate Limiting**: Scripts include delays - increase if needed
2. **Missing Articles**: Check YAML configuration and file paths
3. **Link Resolution**: Verify Repository Path property is populated
4. **Empty Quotes**: Fixed automatically by migration scripts
5. **HTML Tags**: Cleaned up by formatting fixer

### Recovery

If migration fails partway through:
- Scripts are generally safe to re-run
- Existing content will be updated, not duplicated
- Check logs for specific error details
- Individual scripts can be run independently

## File Structure

```
├── migration_v8.py              # Main content migration
├── tsv_to_notion_db.py          # TSV data enrichment
├── update_relationships.py      # Relationship building
├── efficient_link_replacer.py   # Internal link replacement
├── comprehensive_formatting_fixer.py  # Formatting cleanup
├── test_articles.txt            # Test article list
├── en_ta/                       # Local Translation Academy repo
└── *.log                        # Generated log files
```

## Dependencies

- Python 3.7+
- notion-client
- python-dotenv
- requests
- pyyaml
- pathlib

Install with:
```bash
pip install notion-client python-dotenv requests pyyaml
```

---

*This migration system processes the complete Translation Academy content into a structured, interconnected Notion database with rich formatting and cross-references.*