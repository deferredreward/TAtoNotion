import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GITEA_API_KEY = os.getenv("GITEA_API_KEY")

# Constants
GITEA_BASE_URL = "https://git.door43.org/api/v1"
GITEA_REPO_OWNER = "unfoldingWord"
GITEA_REPO_NAME = "en_ta"
GITEA_BRANCH = "master"

def get_gitea_file_content(path):
    """Get the content of a file from Gitea."""
    url = f"{GITEA_BASE_URL}/repos/{GITEA_REPO_OWNER}/{GITEA_REPO_NAME}/raw/{path}?ref={GITEA_BRANCH}"
    headers = {"Authorization": f"token {GITEA_API_KEY}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.text
    else:
        print(f"Error fetching {path}: {response.status_code}")
        return None

def test_fetch_article_components():
    """Test fetching the components of an article."""
    article_folder = "figs-ellipsis"
    base_path = f"translate/{article_folder}"
    
    # Get article components
    title_path = f"{base_path}/title.md"
    subtitle_path = f"{base_path}/sub-title.md"
    content_path = f"{base_path}/01.md"
    
    print(f"Fetching title from: {title_path}")
    title_content = get_gitea_file_content(title_path)
    if title_content:
        print(f"Title content: {title_content.strip()}")
    else:
        print("Failed to fetch title content")
    
    print(f"\nFetching subtitle from: {subtitle_path}")
    subtitle_content = get_gitea_file_content(subtitle_path)
    if subtitle_content:
        print(f"Subtitle content: {subtitle_content.strip()}")
    else:
        print("Failed to fetch subtitle content")
    
    print(f"\nFetching main content from: {content_path}")
    main_content = get_gitea_file_content(content_path)
    if main_content:
        # Print only the first 100 characters of the main content
        print(f"Main content (first 100 chars): {main_content[:100].strip()}...")
    else:
        print("Failed to fetch main content")

if __name__ == "__main__":
    test_fetch_article_components() 