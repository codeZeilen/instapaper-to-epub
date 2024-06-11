from instapaper import Instapaper, Bookmark
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
import hashlib
from urllib.parse import urlparse
from typing import Optional

BOOK_FILE_PREFIX = "InPa"

with open("oauth_config.json", "r") as f:
    oauth_config = json.load(f)
with open("user_credentials.json", "r") as f:
    user_credentials = json.load(f)
instapaper = Instapaper(oauth_config['id'], oauth_config['secret'])
instapaper.login(user_credentials['username'], user_credentials['password'])

if len(sys.argv) > 1:
    num_bookmarks_to_retrieve = int(sys.argv[1])
else:
    num_bookmarks_to_retrieve = 70

books_folder = Path('./books')
books_folder.mkdir(exist_ok=True)
tmp_images_folder = Path('./tmp_images')
tmp_images_folder.mkdir(exist_ok=True)

def download():
    for bookmark in instapaper.bookmarks(limit=num_bookmarks_to_retrieve):
        download_bookmark_to_folder(bookmark)

def download_bookmark_to_folder(bookmark, folder_path : Path = books_folder):
    if not get_content(bookmark):
        return

    book = create_full_book(bookmark.bookmark_id, bookmark.original_title, bookmark.sanitized_content)
    write_book(book, bookmark.book_file_name, folder_path)

#
# Downloading content
#
def get_content(bookmark) -> Optional[Bookmark]:
    adapt_title(bookmark) 
    bookmark.bookmark_id = str(bookmark.bookmark_id)    
    bookmark.book_file_name = generate_file_name(bookmark)

    if bookmark_already_downloaded(bookmark):
        print(f'Skipping {bookmark.original_title}, as corresponding book already exists.')
        return None
    
    print(f'Downloading {bookmark.title if bookmark.title else bookmark.url}')
    get_and_sanitize_content(bookmark)
    if not bookmark.sanitized_content:
        print(f'Skipping {bookmark.title} due to empty content.')
        return None

    return bookmark

def adapt_title(bookmark):
    bookmark.original_title = bookmark.title
    if not bookmark.title:
        bookmark.title = bookmark.url
    bookmark.title = f'{BOOK_FILE_PREFIX}: {bookmark.title}'

def bookmark_already_downloaded(bookmark):
    return (books_folder / f'{bookmark.book_file_name}.epub').exists()

def get_and_sanitize_content(bookmark):
    if bookmark.original_title:
        bookmark.sanitized_content = bookmark.html
        bookmark.sanitized_content = bookmark.sanitized_content.strip()
    else:
        # This is a bookmark without content
        bookmark.sanitized_content = "no content"
        

def generate_file_name(bookmark: Bookmark) -> str:
    return make_safe_filename(bookmark.title) + '_' + bookmark.bookmark_id

#
# EPub Creation
#
def create_full_book(bookmark_id, title, sanitized_content) -> epub.EpubBook:
    book = new_book(title, bookmark_id)

    cover = create_cover(title, bookmark_id)
    book.add_item(cover)

    full_content = sanitize_and_add_images(book, sanitized_content)
    chapter = create_chapter(title, bookmark_id, full_content)
    book.add_item(chapter)

    add_navigation_files(book, cover, chapter)

    return book

def new_book(title, book_id: str = "") -> epub.EpubBook:
    book = epub.EpubBook()
    book.set_identifier(book_id)
    book.set_title(title)
    return book

def create_cover(title: str, book_id: str):
    cover_content = f'<html><body><h1 style="width: 70%; margin: 0 auto;">{title}</h1></body></html>'
    cover = epub.EpubHtml(
        title=title, 
        file_name=f'{book_id}_cover.xhtml')
    cover.content = cover_content
    return cover

def create_chapter(title: str, book_id: str, sanitized_content: str) -> epub.EpubHtml:
    chapter = epub.EpubHtml(
        title=title, 
        file_name=f'{book_id}.xhtml')
    chapter.content = sanitized_content
    return chapter

def sanitize_and_add_images(book: epub.EpubBook, sanitized_content: str) -> str:
    return shrink_replace_and_add_images(book, sanitized_content)

def add_navigation_files(book: epub.EpubBook, cover: epub.EpubCover, chapter) -> None:
    book.toc = (cover,chapter,)
    
    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Define the spine of the book
    book.spine = [cover, chapter,]

def write_book(book: epub.EpubBook, book_file_name:str, folder_path: Path = books_folder):
    epub.write_epub(folder_path / f'{book_file_name}.epub', book, {})


#
# Sanitizing content
#
def make_safe_filename(file_name: str) -> str:
    # Define a whitelist of characters that are allowed in filenames
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

    # Remove all characters from the string that are not in the whitelist
    safe_filename = ''.join(c for c in file_name if c in valid_chars)

    # Replace spaces with underscores
    safe_filename = safe_filename.replace(' ', '_')

    # Shorten filename
    safe_filename = safe_filename[:100]

    return safe_filename

def shrink_replace_and_add_images(book, html) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    replaced_images = dict()

    images = soup.find_all('img')
    images = filter(lambda i: i.has_attr('src') and not i['src'].startswith('data:'), images)
    for img in images:  
        image_url = urlparse(img['src']) 
        url_file_name = hashlib.md5(img['src'].encode('utf-8')).hexdigest() + image_url.path.split('/')[-1]
        file_path = tmp_images_folder / url_file_name
        
        # Special Cases
        if (not file_path.suffix) or (file_path.suffix in ('.html', '.svg', '.webp')):
            replace_img_with_alt_text(img, soup)
            continue

        if img['src'] in replaced_images:
            img['src'] = replaced_images[img['src']]
            continue

        # Common Case        
        image_data = None
        try:
            response = requests.get(img['src'])
            response.raise_for_status()
            
            image_data = response.content
            image_data = convert_image(image_data)
            add_image_to_book(book, url_file_name, image_data)
            replaced_images[img['src']] = url_file_name
            img['src'] = url_file_name
        except:
            replace_img_with_alt_text(img, soup)   

    return str(soup)

def replace_imgs_with_alt_text(html_content) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    for img in soup.find_all('img'):
        if not replace_img_with_alt_text(img, soup): 
            # Just remove the image right away
            img.decompose()
    return str(soup)

def replace_img_with_alt_text(img, soup) -> bool:
    alt_text = img.get('alt')
    if alt_text:
        # Preserve the image content by using the alt text
        alt_par = soup.new_tag('p')
        alt_par.wrap(alt_text)
        img.replace_with(alt_par)
        return True
    else:
        return False
    
def convert_image(image_data) -> bytes:
    image = Image.open(io.BytesIO(image_data))
    image = image.convert('L')
    return image.tobytes()

def add_image_to_book(book, url_file_name, image_data) -> None:
    img_path = Path(url_file_name)
    book_image = epub.EpubItem(uid=img_path.name, 
        file_name=url_file_name, 
        media_type=mime.guess_type(url_file_name)[0], 
        content=image_data)
    book.add_item(book_image)
    return url_file_name

# Download ebooks when started as a script
if __name__ == '__main__':
    download()
