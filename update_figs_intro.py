import os
import re
import logging
import time
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

# Page IDs
NOTION_PARENT_ID = os.environ.get("NOTION_PARENT_ID", "1c372d5a-f2de-80e0-8b11-cd7748a1467d")
FIGURES_OF_SPEECH_SECTION_ID = "1c472d5a-f2de-8169-88f3-facba60a0b94"  # Section page ID
FIGS_INTRO_PAGE_ID = None  # We'll find this

# Create a mapping of article IDs to their Notion page IDs
article_mapping = {
    "figs-apostrophe": "1c472d5a-f2de-818b-ac19-e4429bf84339",
    "figs-aside": "1c472d5a-f2de-8113-991f-e445b13ddec1",
    "figs-doublet": "1c472d5a-f2de-814c-9a9b-ca7cb12381af",
    "figs-euphemism": "1c472d5a-f2de-81fa-84ec-e66795396583",
    "figs-hendiadys": "1c472d5a-f2de-814c-9862-fe3f3b390be8",
    "figs-hyperbole": "1c472d5a-f2de-81a6-a829-f8ee60162d23",
    "figs-idiom": "1c472d5a-f2de-8160-9524-f91e617c85d1",
    "figs-irony": "1c472d5a-f2de-81e1-86b5-d45735f3be57",
    "figs-litany": "1c472d5a-f2de-81f1-8764-c8ebda37023c",
    "figs-litotes": "1c472d5a-f2de-81b9-a8f9-df92f9e32275",
    "figs-merism": "1c472d5a-f2de-81cf-8f51-d0d6a2cca8a7",
    "figs-metaphor": "1c472d5a-f2de-812c-928b-c1bbf12ef0ff",
    "figs-metonymy": "1c472d5a-f2de-8175-86b5-c6868edada96",
    "figs-parallelism": "1c472d5a-f2de-81f2-a2b9-e73bf22fb509",
    "figs-personification": "1c472d5a-f2de-8129-8011-d750e46ff928",
    "figs-pastforfuture": "1c472d5a-f2de-8192-b60b-d6a17bcf692b",
    "figs-rquestion": "1c472d5a-f2de-8160-88c9-fbcbc58c00bb",
    "figs-simile": "1c472d5a-f2de-81c4-849d-e22f79507df0",
    "figs-synecdoche": "1c472d5a-f2de-81ec-a368-eaeaf0c587db"
}

# Map article IDs to their titles
article_titles = {
    "figs-apostrophe": "Apostrophe",
    "figs-aside": "Aside",
    "figs-doublet": "Doublet",
    "figs-euphemism": "Euphemism",
    "figs-hendiadys": "Hendiadys",
    "figs-hyperbole": "Hyperbole",
    "figs-idiom": "Idiom",
    "figs-irony": "Irony",
    "figs-litany": "Litany",
    "figs-litotes": "Litotes",
    "figs-merism": "Merism",
    "figs-metaphor": "Metaphor",
    "figs-metonymy": "Metonymy",
    "figs-parallelism": "Parallelism",
    "figs-personification": "Personification",
    "figs-pastforfuture": "Predictive Past",
    "figs-rquestion": "Rhetorical Question",
    "figs-simile": "Simile",
    "figs-synecdoche": "Synecdoche"
}

def list_pages(parent_id, max_pages=100):
    """List all pages under a parent with their titles."""
    try:
        response = notion.blocks.children.list(block_id=parent_id, page_size=max_pages)
        pages = []
        
        for block in response.get("results", []):
            if block.get("type") == "child_page":
                page_title = block.get("child_page", {}).get("title", "")
                page_id = block.get("id")
                pages.append((page_title, page_id))
                logger.info(f"Found page: '{page_title}' with ID: {page_id}")
        
        # Check if there are more results
        if response.get("has_more"):
            next_cursor = response.get("next_cursor")
            while next_cursor:
                response = notion.blocks.children.list(
                    block_id=parent_id,
                    start_cursor=next_cursor,
                    page_size=max_pages
                )
                
                for block in response.get("results", []):
                    if block.get("type") == "child_page":
                        page_title = block.get("child_page", {}).get("title", "")
                        page_id = block.get("id")
                        pages.append((page_title, page_id))
                        logger.info(f"Found page: '{page_title}' with ID: {page_id}")
                
                next_cursor = response.get("next_cursor") if response.get("has_more") else None
        
        return pages
    except Exception as e:
        logger.error(f"Error listing pages: {e}")
        return []

def find_page_by_title(parent_id, title):
    """Find a Notion page by title within a parent page."""
    try:
        response = notion.blocks.children.list(block_id=parent_id)
        
        for block in response.get("results", []):
            if block.get("type") == "child_page":
                page_title = block.get("child_page", {}).get("title", "")
                if page_title.lower() == title.lower():
                    return block.get("id")
        
        # Check if there are more results
        if response.get("has_more"):
            next_cursor = response.get("next_cursor")
            while next_cursor:
                response = notion.blocks.children.list(
                    block_id=parent_id,
                    start_cursor=next_cursor
                )
                
                for block in response.get("results", []):
                    if block.get("type") == "child_page":
                        page_title = block.get("child_page", {}).get("title", "")
                        if page_title.lower() == title.lower():
                            return block.get("id")
                
                next_cursor = response.get("next_cursor") if response.get("has_more") else None
        
        return None
    except Exception as e:
        logger.error(f"Error finding page by title: {e}")
        return None

def create_figs_intro_content():
    """Create the content for the Figures of Speech intro page with proper links."""
    # Create a heading and introduction
    blocks = [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Figures of Speech"
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
                            "content": "Figures of speech have special meanings that are not the same as the meanings of their individual words. There are different kinds of figures of speech. This page lists and defines some of those that are used in the Bible. In-depth study will follow."
                        }
                    }
                ]
            }
        },
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Description"
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
                            "content": "Figures of speech are ways of saying things that use words in non-literal ways. That is, the meaning of a figure of speech is not the same as the more direct meaning of its words. In order to translate the meaning, you need to be able to recognize figures of speech and know what the figure of speech means in the source language. Then you can choose either a figure of speech or a direct way to communicate that same meaning in the target language."
                        }
                    }
                ]
            }
        },
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Types"
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
                            "content": "Listed below are different types of Figures of Speech. If you would like additional information simply click the colored word to be directed to a page containing definitions, examples, and videos for each figure of speech."
                        }
                    }
                ]
            }
        }
    ]
    
    # Add a bulleted list item for each figure of speech with Notion links
    for article_id, title in article_titles.items():
        if article_id in article_mapping:
            notion_url = f"https://www.notion.so/{article_mapping[article_id].replace('-', '')}"
            
            # Create a description based on the figure of speech type
            description = get_description_for_figure(article_id, title)
            
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": ""
                            }
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": title,
                                "link": {
                                    "url": notion_url
                                }
                            },
                            "annotations": {
                                "bold": True
                            }
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": " — " + description
                            }
                        }
                    ]
                }
            })
    
    return blocks

def get_description_for_figure(article_id, title):
    """Get a description for each figure of speech type."""
    descriptions = {
        "figs-apostrophe": "An apostrophe is a figure of speech in which a speaker directly addresses someone who is not there, or addresses a thing that is not a person.",
        "figs-aside": "An aside is a figure of speech in which someone who is speaking to a person or group pauses to speak confidentially to himself or someone else about those to whom he had been speaking.",
        "figs-doublet": "A doublet is a pair of words or very short phrases that mean the same thing and that are used in the same phrase. In the Bible, doublets are often used in poetry, prophecy, and sermons to emphasize an idea.",
        "figs-euphemism": "A euphemism is a mild or polite way of referring to something that is unpleasant or embarrassing. Its purpose is to avoid offending the people who hear or read it.",
        "figs-hendiadys": "In hendiadys a single idea is expressed with two words connected with \"and,\" when one word could be used to modify the other.",
        "figs-hyperbole": "A hyperbole is a deliberate exaggeration used to indicate the speaker's feeling or opinion about something.",
        "figs-idiom": "An idiom is a group of words that has a meaning that is different from what one would understand from the meanings of the individual words.",
        "figs-irony": "Irony is a figure of speech in which the sense that the speaker intends to communicate is actually the opposite of the literal meaning of the words.",
        "figs-litany": "Litany is a figure of speech in which the various components of a thing are listed in a series of very similar statements.",
        "figs-litotes": "Litotes is an emphatic statement about something made by negating an opposite expression.",
        "figs-merism": "Merism is a figure of speech in which a person refers to something by listing some of its parts or by speaking of two extreme parts of it.",
        "figs-metaphor": "A metaphor is a figure of speech in which one concept is used in place of another, unrelated concept. This invites the hearer to think of what the unrelated concepts have in common.",
        "figs-metonymy": "Metonymy is a figure of speech in which a thing or idea is called not by its own name, but by the name of something closely associated with it.",
        "figs-parallelism": "In parallelism two phrases or clauses that are similar in structure or idea are used together. It is found throughout the whole of the Hebrew Bible, most commonly in the poetry of the books of Psalms and Proverbs.",
        "figs-personification": "Personification is a figure of speech in which an idea or something that is not human is referred to as if it were a person and could do the things that people do or have the qualities that people have.",
        "figs-pastforfuture": "The predictive past is a form that some languages use to refer to things that will happen in the future. This is sometimes done in prophecy to show that the event will certainly happen.",
        "figs-rquestion": "A rhetorical question is a question that is used for something other than getting information. Often it indicates the speaker's attitude toward the topic or the listener.",
        "figs-simile": "A simile is a comparison of two things that are not normally thought to be similar. It focuses on a particular trait that the two items have in common, and it includes words such as \"like,\" \"as,\" or \"than\" to make the comparison explicit.",
        "figs-synecdoche": "Synecdoche is a figure of speech in which (1) the name of a part of something is used to refer to the whole thing, or (2) the name of a whole thing is used to refer to just one part of it."
    }
    
    return descriptions.get(article_id, f"A figure of speech related to {title}.")

def find_figs_intro_page():
    """Try to find the Figures of Speech intro page by searching in multiple places."""
    global FIGS_INTRO_PAGE_ID
    
    # Option 1: Check if it's directly in the parent page
    logger.info("Checking if Figures of Speech intro page is in the main parent page")
    FIGS_INTRO_PAGE_ID = find_page_by_title(NOTION_PARENT_ID, "Figures of Speech")
    if FIGS_INTRO_PAGE_ID:
        logger.info(f"Found Figures of Speech intro page in parent: {FIGS_INTRO_PAGE_ID}")
        return FIGS_INTRO_PAGE_ID
    
    # Option 2: Check in the Just-in-Time Learning Modules section
    logger.info("Checking if Figures of Speech intro page is in Just-in-Time Learning Modules")
    jit_modules_id = find_page_by_title(NOTION_PARENT_ID, "Just-in-Time Learning Modules")
    if jit_modules_id:
        FIGS_INTRO_PAGE_ID = find_page_by_title(jit_modules_id, "Figures of Speech")
        if FIGS_INTRO_PAGE_ID:
            logger.info(f"Found Figures of Speech intro page in JIT modules: {FIGS_INTRO_PAGE_ID}")
            return FIGS_INTRO_PAGE_ID
    
    # Option 3: Check in the Figures of Speech section
    logger.info("Checking if Figures of Speech intro page is in the Figures of Speech section")
    pages = list_pages(FIGURES_OF_SPEECH_SECTION_ID)
    for title, page_id in pages:
        if title.lower() == "figures of speech":
            FIGS_INTRO_PAGE_ID = page_id
            logger.info(f"Found Figures of Speech intro page in section: {FIGS_INTRO_PAGE_ID}")
            return FIGS_INTRO_PAGE_ID
    
    # Option 4: Look for "figs-intro" or similar variations
    logger.info("Checking for variations of the intro page title")
    # Check if there's a page with figs-intro in the title
    for title, page_id in pages:
        if "intro" in title.lower() or "introduction" in title.lower():
            FIGS_INTRO_PAGE_ID = page_id
            logger.info(f"Found potential intro page: {title} with ID {FIGS_INTRO_PAGE_ID}")
            return FIGS_INTRO_PAGE_ID
    
    logger.error("Could not find the Figures of Speech intro page")
    return None

def update_figs_intro_page():
    """Update the Figures of Speech intro page with proper links."""
    # Find the Figures of Speech intro page
    find_figs_intro_page()
    
    # Get the globally defined page ID
    global FIGS_INTRO_PAGE_ID
    
    if not FIGS_INTRO_PAGE_ID:
        logger.error("Could not find the Figures of Speech intro page, attempting to create it")
        
        # Create a new page if we couldn't find it
        try:
            # Create a new page in the Figures of Speech section
            page_data = {
                "parent": {"page_id": FIGURES_OF_SPEECH_SECTION_ID},
                "properties": {
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": "Figures of Speech"
                                }
                            }
                        ]
                    }
                }
            }
            
            response = notion.pages.create(**page_data)
            FIGS_INTRO_PAGE_ID = response["id"]
            logger.info(f"Created new Figures of Speech intro page: {FIGS_INTRO_PAGE_ID}")
        except Exception as e:
            logger.error(f"Failed to create a new page: {e}")
            return False
    
    try:
        # First, delete all existing content
        existing_blocks = notion.blocks.children.list(block_id=FIGS_INTRO_PAGE_ID)
        
        for block in existing_blocks.get("results", []):
            logger.info(f"Deleting block: {block['id']}")
            notion.blocks.delete(block_id=block["id"])
        
        # Wait a bit to ensure deletion is completed
        time.sleep(1)
        
        # Create new content with proper links
        new_blocks = create_figs_intro_content()
        
        # Add the new content to the page
        notion.blocks.children.append(block_id=FIGS_INTRO_PAGE_ID, children=new_blocks)
        
        logger.info(f"Successfully updated Figures of Speech intro page with {len(new_blocks)} blocks")
        return True
    except Exception as e:
        logger.error(f"Error updating Figures of Speech intro page: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting update of Figures of Speech intro page")
    success = update_figs_intro_page()
    if success:
        logger.info("Successfully updated Figures of Speech intro page")
    else:
        logger.error("Failed to update Figures of Speech intro page") 