# TAtoNotion

A tool to import Translation Academy articles from a Gitea repository into Notion pages.

## Overview

TAtoNotion is a Python utility that imports articles from the unfoldingWord Translation Academy repository hosted on Gitea into a Notion database. The tool preserves formatting including blockquotes, nested blockquotes, footnotes, lists, and text styles (bold, italic).

## Features

- Import articles from the Translation Academy repository to Notion
- Preserve markdown formatting (headings, lists, blockquotes, code blocks)
- Support for nested blockquotes with proper indentation
- Handle special formatting (bold, italic, links)
- Convert footnotes to superscript Unicode characters
- Present article subtitles in callout boxes
- Skip existing articles to avoid duplicates
- Configurable import delays to avoid rate limiting

## Setup

### Prerequisites

- Python 3.6+
- Gitea API key with access to the Translation Academy repository
- Notion API key with integration access to your workspace

### Installation

1. Clone the repository:
```
git clone https://github.com/yourusername/TAtoNotion.git
cd TAtoNotion
```

2. Create a virtual environment:
```
python -m venv venv
```

3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`

4. Install dependencies:
```
pip install -r requirements.txt
```

5. Create a `.env` file with your API keys:
```
GITEA_API_KEY=your_gitea_api_key
NOTION_API_KEY=your_notion_api_key
```

## Usage

1. Create a list of articles to import in `articles_to_import.txt`, with one article folder name per line:
```
figs-ellipsis
figs-idiom
translate-names
```

2. Run the script:
```
python ta_to_notion.py
```

### Command Line Options

- `--input` or `-i`: Specify an alternative input file (default: `articles_to_import.txt`)
- `--skip-existing` or `-s`: Skip articles that already exist in Notion
- `--delay` or `-d`: Set delay between imports in seconds (default: 1.0)

Example:
```
python ta_to_notion.py --input custom_list.txt --skip-existing --delay 2.0
```

## Implementation Details

The script handles several special formatting cases:

1. **Nested Blockquotes**: Double blockquotes (> >) are indented under their parent blocks
2. **Footnotes**: Rendered as Unicode superscript numbers
3. **Subtitles**: Displayed in callout boxes with a question mark icon
4. **Empty Blockquote Lines**: Preserved as empty blockquotes with a space character

## Future Directions

The project will be moving in a major new direction focusing on:

1. Enhanced content transformation capabilities
2. Integration with additional knowledge base platforms
3. Improved formatting preservation and conversion
4. Batch processing and scheduling capabilities

## Troubleshooting

If you encounter issues:

1. Check the log file `ta_to_notion.log` for detailed error messages
2. Verify your API keys are correct and have proper permissions
3. Ensure the article folders exist in the Translation Academy repository

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 