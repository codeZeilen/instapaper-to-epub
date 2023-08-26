from instapaper import Instapaper
from ebooklib import epub
from pathlib import Path
import json
import string

# Replace with your Instapaper credentials
with open("instapaper_oauth_config.json", "r") as f:
    oauth_config = json.load(f)

with open("instapaper_user_credentials.json", "r") as f:
    user_credentials = json.load(f)

instapaper = Instapaper(oauth_config.id, oauth_config.secret)
instapaper.login(user_credentials.username, user_credentials.password)

books_folder = Path('books')

def make_safe_filename(s):
    # Define a whitelist of characters that are allowed in filenames
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

    # Remove all characters from the string that are not in the whitelist
    safe_filename = ''.join(c for c in s if c in valid_chars)

    # Replace spaces with underscores
    safe_filename = safe_filename.replace(' ', '_')

    return safe_filename

# Get all bookmarks
for bookmark in instapaper.bookmarks(limit=1):
    bookmark.title = 'instapaper:' + bookmark.title
    book_file_name = make_safe_filename(bookmark.title)
    if not book_file_name:
        continue 
    if not (books_folder / f'{book_file_name}.epub').exists():
        print(f'Downloading {bookmark.title}')
        print(bookmark.text)

        # Get the article content
        content = bookmark.html
        if not content.strip():
            print(f'Skipping {bookmark.title} due to empty content')
            continue
        
        # Create an epub book
        book = epub.EpubBook()
        book.set_identifier(str(bookmark.bookmark_id))
        book.set_title(bookmark.title)
        book.set_language('en')
        
        # Create an epub chapter from the article content
        chapter = epub.EpubHtml(title=bookmark.title, file_name=f'{bookmark.bookmark_id}.xhtml', lang='en')
        chapter.content = content
        book.add_item(chapter)
        
        # Add the chapter to the book's table of contents
        book.toc = (chapter,)
        
        # Add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define the spine of the book
        book.spine = [chapter,]
        
        # Write the epub file to disk
        epub.write_epub(f'./books/{book_file_name}.epub', book, {})
    else:
        print(f'Skipping {bookmark.title}')

