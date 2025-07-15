import os
import requests
import logging
import argparse
from dotenv import load_dotenv
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("extract_jit_modules.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API Keys
GITEA_API_KEY = os.getenv("GITEA_API_KEY")

if not GITEA_API_KEY:
    logger.error("GITEA_API_KEY not found in .env file")
    exit(1)

# Constants
GITEA_BASE_URL = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_BRANCH = "master"
OUTPUT_FILE = "just_in_time_modules.md"

# List of known folder names
KNOWN_FOLDERS = [
    "figs-123person", "figs-abstractnouns", "figs-activepassive", "figs-apostrophe", 
    "figs-aside", "figs-declarative", "figs-distinguish", "figs-doublenegatives", 
    "figs-doublet", "figs-ellipsis", "figs-euphemism", "figs-events", "figs-exclamations", 
    "figs-exclusive", "figs-explicit", "figs-explicitinfo", "figs-extrainfo", 
    "figs-gendernotations", "figs-genericnoun", "figs-go", "figs-hendiadys", 
    "figs-hyperbole", "figs-hypo", "figs-idiom", "figs-imperative", "figs-infostructure", 
    "figs-irony", "figs-litany", "figs-litotes", "figs-merism", "figs-metaphor", 
    "figs-metonymy", "figs-nominaladj", "figs-parables", "figs-parallelism", 
    "figs-pastforfuture", "figs-personification", "figs-possession", "figs-quotations", 
    "figs-quotemarks", "figs-quotesinquotes", "figs-rpronouns", "figs-rquestion", 
    "figs-simile", "figs-synecdoche", "figs-you", "figs-youcrowd", "figs-youdual", 
    "figs-youformal", "figs-yousingular", "grammar-collectivenouns", 
    "grammar-connect-condition-contrary", "grammar-connect-condition-fact", 
    "grammar-connect-condition-hypothetical", "grammar-connect-exceptions", 
    "grammar-connect-logic-contrast", "grammar-connect-logic-goal", 
    "grammar-connect-logic-result", "grammar-connect-time-background", 
    "grammar-connect-time-sequential", "grammar-connect-time-simultaneous", 
    "grammar-connect-words-phrases", "translate-bdistance", "translate-blessing", 
    "translate-bmoney", "translate-bvolume", "translate-bweight", "translate-fraction", 
    "translate-hebrewmonths", "translate-kinship", "translate-names", "translate-numbers", 
    "translate-ordinal", "translate-symaction", "translate-textvariants", 
    "translate-transliterate", "translate-unknown", "translate-versebridge", 
    "writing-background", "writing-endofstory", "writing-newevent", "writing-oathformula", 
    "writing-participants", "writing-poetry", "writing-politeness", "writing-pronouns", "writing-proverbs", 
    "writing-quotations", "writing-symlanguage"
]

def get_gitea_file_content(path):
    """Get the content of a file from Gitea."""
    url = f"{GITEA_BASE_URL}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/raw/{path}?ref={GITEA_BRANCH}"
    headers = {"Authorization": f"token {GITEA_API_KEY}"}
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.text
        else:
            logger.error(f"Error fetching {path}: HTTP {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"Request failed for {path}: {str(e)}")
        return None

def process_article(folder):
    """Process a single article by folder name."""
    base_path = f"translate/{folder}"
    
    # Get article components
    title_content = get_gitea_file_content(f"{base_path}/title.md")
    main_content = get_gitea_file_content(f"{base_path}/01.md")
    
    if not all([title_content, main_content]):
        logger.error(f"Failed to fetch all components for {folder}")
        return None
    
    return {
        'title': title_content.strip(),
        'content': main_content,
        'folder': folder
    }

def create_markdown_file(output_file):
    """Create a markdown file with all JIT modules."""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Just-in-Time Learning Modules\n\n")
            
            # Process each folder in the list
            for folder in KNOWN_FOLDERS:
                logger.info(f"Processing folder: {folder}")
                article_data = process_article(folder)
                
                if article_data:
                    f.write(f"# {article_data['title']}\n\n")
                    f.write(f"*Issue Link: {article_data['folder']}*\n\n")
                    f.write(f"{article_data['content']}\n\n")
                    f.write("---\n\n")
                else:
                    f.write(f"# {folder}\n\n")
                    f.write(f"*Issue Link: {folder}*\n\n")
                    f.write("*(Content not available)*\n\n")
                    f.write("---\n\n")
                
                # Add a small delay to avoid rate limiting
                time.sleep(0.5)
        
        logger.info(f"Successfully created markdown file: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error creating markdown file: {str(e)}")
        return False

def main():
    """Main function to extract JIT modules and create a markdown file."""
    parser = argparse.ArgumentParser(description='Extract Just-in-Time Learning Modules and create a markdown file')
    parser.add_argument('--output', '-o', default=OUTPUT_FILE, help='Output markdown file path')
    parser.add_argument('--delay', '-d', type=float, default=0.5, help='Delay between API requests in seconds (to avoid rate limiting)')
    args = parser.parse_args()
    
    logger.info(f"Starting extraction of {len(KNOWN_FOLDERS)} JIT modules")
    
    # Create markdown file
    logger.info(f"Creating markdown file: {args.output}")
    success = create_markdown_file(args.output)
    
    if success:
        logger.info(f"Successfully created markdown file with {len(KNOWN_FOLDERS)} modules")
    else:
        logger.error("Failed to create markdown file")

if __name__ == "__main__":
    main() 