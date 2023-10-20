from instapaper import Instapaper
from ebooklib import epub
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image
import requests
import json
import string
import sys
import io
import mimetypes as mime
from urllib.parse import urlparse

# Replace with your Instapaper credentials
with open("oauth_config.json", "r") as f:
    oauth_config = json.load(f)

with open("user_credentials.json", "r") as f:
    user_credentials = json.load(f)

if len(sys.argv) > 1:
    num_bookmarks_to_retrieve = sys.argv[1]
else:
    num_bookmarks_to_retrieve = 70
 
instapaper = Instapaper(oauth_config['id'], oauth_config['secret'])
instapaper.login(user_credentials['username'], user_credentials['password'])

books_folder = Path('books')

def make_safe_filename(s):
    # Define a whitelist of characters that are allowed in filenames
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

    # Remove all characters from the string that are not in the whitelist
    safe_filename = ''.join(c for c in s if c in valid_chars)

    # Replace spaces with underscores
    safe_filename = safe_filename.replace(' ', '_')

    return safe_filename

def replace_imgs_with_alt_text(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for img in soup.find_all('img'):
        if not replace_img_with_alt_text(img, soup): 
            # Just remove the image right away
            img.decompose()
    return str(soup)

def replace_img_with_alt_text(img, soup):
    alt_text = img.get('alt')
    if alt_text:
        # Preserve the image content by using the alt text
        alt_par = soup.new_tag('p')
        alt_par.wrap(alt_text)
        img.replace_with(alt_par)
        return True
    else:
        return False

def shrink_and_replace_images(html, book):
    # Parse the HTML
    soup = BeautifulSoup(html, 'html.parser')

    for img in soup.find_all('img'):
        img_url = img['src']
        if img_url.startswith('data:'):
            # Nothing to do here
            continue
        
        parsed_url = urlparse(img_url)
        url_file_name = parsed_url.path.split('/')[-1]
        filename = f'./tmp_images/{url_file_name}'
        filepath = Path(filename)
        if (not filepath.suffix) or (filepath.suffix in ('.html', '.svg', '.webp')):
            replace_img_with_alt_text(img, soup)
            continue
        
        try:
            response = requests.get(img_url)
            if not response.status_code == 200:
                replace_img_with_alt_text(img, soup)
            else: 
                img_data = response.content
                            
                # Dither the image to save space
                image = Image.open(io.BytesIO(img_data))
                image = image.convert('1', dither=Image.FLOYDSTEINBERG)
                image.save(filename)
            
                with open(filename, 'rb') as f:
                    image_data = f.read()

                img_path = Path(url_file_name)
                book_image = epub.EpubItem(uid=img_path.name, 
                    file_name=url_file_name, 
                    media_type=mime.guess_type(url_file_name)[0], 
                    content=image_data)
                book.add_item(book_image)

                # Update the img tag in the HTML
                img['src'] = url_file_name
        except Exception:
            replace_img_with_alt_text(img, soup)

    return str(soup)

# Get all bookmarks
for bookmark in instapaper.bookmarks(limit=num_bookmarks_to_retrieve):
    bookmark.original_title = bookmark.title
    bookmark.title = 'Instapaper: ' + bookmark.title
    book_file_name = make_safe_filename(bookmark.title)
    if not book_file_name:
        continue 
    if not (books_folder / f'{book_file_name}.epub').exists():
        print(f'Downloading {bookmark.title}')

        # Check whether content is available
        content = bookmark.html
        if not (content and content.strip()):
            print(f'Skipping {bookmark.title} due to empty content')
            continue

        # Create an epub book
        book = epub.EpubBook()
        book.set_identifier(str(bookmark.bookmark_id))
        book.set_title(bookmark.title)
        book.set_language('en')

        # Create an epub chapter with the cover
        
        ## Create the Cover
        cover_content = f'<html><body><h1 style="width: 70%; margin: 0 auto;">{bookmark.original_title}</h1></body></html>'
        
        ## Add Cover
        cover = epub.EpubHtml(title=bookmark.title, file_name=f'{bookmark.bookmark_id}_cover.xhtml', lang='en')
        cover.content = cover_content
        book.add_item(cover)
        
        # Create an epub chapter from the article content

        ## Prepare Content
        content = shrink_and_replace_images(content, book)

        ## Add Chapter
        chapter = epub.EpubHtml(title=bookmark.title, file_name=f'{bookmark.bookmark_id}.xhtml', lang='en')
        chapter.content = content
        book.add_item(chapter)
        
        # Add the chapter to the book's table of contents
        book.toc = (cover,chapter,)
        
        # Add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define the spine of the book
        book.spine = [cover, chapter,]
        
        # Write the epub file to disk
        epub.write_epub(f'./books/{book_file_name}.epub', book, {})
    else:
        print(f'Skipping {bookmark.title}')

