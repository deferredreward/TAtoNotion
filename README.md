# TAtoNotion

A Python script to import Translation Academy articles from the [unfoldingWord/en_ta](https://git.door43.org/unfoldingWord/en_ta) Gitea repository to Notion pages.

## Setup

1. Clone this repository
2. Create a virtual environment and activate it:
```
python -m venv venv
.\venv\Scripts\Activate.ps1  # On Windows
source venv/bin/activate     # On macOS/Linux
```
3. Install dependencies:
```
pip install -r requirements.txt
```
4. Create a `.env` file with your API keys:
```
GITEA_API_KEY=your_gitea_api_key
NOTION_API_KEY=your_notion_api_key
```

## Usage

### 1. Add articles to import

Edit the `articles_to_import.txt` file to include the folder names of the articles you want to import, one per line. For example:
```
figs-ellipsis
figs-metaphor
translate-names
```

### 2. Run the script

```
python ta_to_notion.py
```

This will:
1. Read the list of articles from `articles_to_import.txt`
2. For each article, retrieve the title, subtitle, and content from the Gitea repository
3. Create a Notion page with those components under the specified parent page

### Command-line Options

The script supports several command-line options:

- `--input` or `-i`: Specify a custom input file (default: articles_to_import.txt)
  ```
  python ta_to_notion.py --input custom_list.txt
  ```

- `--skip-existing` or `-s`: Skip articles that already exist in Notion
  ```
  python ta_to_notion.py --skip-existing
  ```

- `--delay` or `-d`: Set the delay between imports in seconds (default: 1.0)
  ```
  python ta_to_notion.py --delay 0.5
  ```

You can combine options:
```
python ta_to_notion.py --input custom_list.txt --skip-existing --delay 2.0
```

## Testing

The project includes two test scripts to verify API connectivity:

- `test_gitea_api.py` - Test connectivity to the Gitea API
- `test_notion_api.py` - Test connectivity to the Notion API and page creation

Run these before using the main script to ensure everything is properly configured:

```
python test_gitea_api.py
python test_notion_api.py
```

## Structure

Each Translation Academy article consists of three files:
- `title.md` - Contains the title of the article
- `sub-title.md` - Contains the subtitle/question the article addresses
- `01.md` - Contains the main content of the article

The script fetches these three components and creates a Notion page with the title as the page title, the subtitle as a heading, and the content properly formatted.

## Logging

The script logs information to both the console and a file named `ta_to_notion.log` in the project directory. This log file contains detailed information about the import process, including any errors encountered. 