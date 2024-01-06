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

with open("oauth_config.json", "r") as f:
    oauth_config = json.load(f)
with open("user_credentials.json", "r") as f:
    user_credentials = json.load(f)
instapaper = Instapaper(oauth_config['id'], oauth_config['secret'])
instapaper.login(user_credentials['username'], user_credentials['password'])

if len(sys.argv) > 1:
    num_bookmarks_to_retrieve = sys.argv[1]
else:
    num_bookmarks_to_retrieve = 70

books_folder = Path('books')
books_folder.mkdir(exist_ok=True)
tmp_images_folder = Path('./tmp_images')
tmp_images_folder.mkdir(exist_ok=True)

def download():
    for bookmark in instapaper.bookmarks(limit=num_bookmarks_to_retrieve):
        if not get_content(bookmark):
            continue

        book = create_book(bookmark)
        sanitize_and_add_images(bookmark, book)
        cover = create_and_add_cover(bookmark, book)
        chapter = create_and_add_chapter(bookmark, book)
        add_navigation_files(book, cover, chapter)
        write_book(bookmark, book)

#
# Downloading content
#
def get_content(bookmark):
    adapt_title_and_file_name(bookmark)        

    if bookmark_already_downloaded(bookmark):
        print(f'Skipping {bookmark.original_title}, as corresponding book already exists.')
        return None
    
    print(f'Downloading {bookmark.title}')
    get_and_sanitize_content(bookmark)
    if not bookmark.sanitized_content:
        print(f'Skipping {bookmark.title} due to empty content.')
        return None

    return bookmark

def adapt_title_and_file_name(bookmark):
    bookmark.original_title = bookmark.title
    bookmark.title = 'Instapaper: ' + bookmark.title
    bookmark.book_file_name = make_safe_filename(bookmark.title)

def bookmark_already_downloaded(bookmark):
    return (books_folder / f'{bookmark.book_file_name}.epub').exists()

def get_and_sanitize_content(bookmark):
    bookmark.sanitized_content = bookmark.html
    if bookmark.sanitized_content:
        bookmark.sanitized_content = bookmark.sanitized_content.strip()


#
# EPub Creation
#
def create_book(bookmark):
    book = epub.EpubBook()
    book.set_identifier(str(bookmark.bookmark_id))
    book.set_title(bookmark.title)
    return book

def create_and_add_cover(bookmark, book):
    cover_content = f'<html><body><h1 style="width: 70%; margin: 0 auto;">{bookmark.original_title}</h1></body></html>'
    cover = epub.EpubHtml(
        title=bookmark.title, 
        file_name=f'{bookmark.bookmark_id}_cover.xhtml')
    cover.content = cover_content
    book.add_item(cover)
    return cover

def create_and_add_chapter(bookmark, book):
    chapter = epub.EpubHtml(
        title=bookmark.title, 
        file_name=f'{bookmark.bookmark_id}.xhtml')
    chapter.content = bookmark.sanitized_content
    book.add_item(chapter)
    return chapter

def sanitize_and_add_images(bookmark, book):
    bookmark.sanitized_content = shrink_replace_and_add_images(bookmark.sanitized_content, book)

def add_navigation_files(book, cover, chapter):
    book.toc = (cover,chapter,)
    
    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Define the spine of the book
    book.spine = [cover, chapter,]

def write_book(bookmark, book):
    epub.write_epub(f'./books/{bookmark.book_file_name}.epub', book, {})


#
# Sanitizing content
#
def make_safe_filename(s):
    # Define a whitelist of characters that are allowed in filenames
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

    # Remove all characters from the string that are not in the whitelist
    safe_filename = ''.join(c for c in s if c in valid_chars)

    # Replace spaces with underscores
    safe_filename = safe_filename.replace(' ', '_')

    return safe_filename

def shrink_replace_and_add_images(html, book):
    soup = BeautifulSoup(html, 'html.parser')

    images = soup.find_all('img')
    images = filter(lambda i: i.has_attr('src') and not i['src'].startswith('data:'), images)
    for img in images:  
        url_file_name = urlparse(img['src']).path.split('/')[-1]
        file_path = tmp_images_folder / url_file_name
        
        if (not file_path.suffix) or (file_path.suffix in ('.html', '.svg', '.webp')):
            replace_img_with_alt_text(img, soup)
            continue
        
        image_data = None
        try:
            response = requests.get(img['src'])
            if response.status_code == 200:
                image_data = response.content
        except Exception:
            pass

        if image_data:
            try: 
                image_data = convert_image(image_data, file_path)
                add_image_to_book(book, url_file_name, image_data)
                img['src'] = url_file_name
            except:
                # Something went wrong while parsing/converting/storing the image
                replace_img_with_alt_text(img, soup)    
        else:
            replace_img_with_alt_text(img, soup)

    return str(soup)

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
    
def convert_image(image_data, filename):
    # Dither the image to save space
    image = Image.open(io.BytesIO(image_data))
    image = image.convert('1', dither=Image.FLOYDSTEINBERG)
    image.save(filename)

    with open(filename, 'rb') as f:
        return f.read()

def add_image_to_book(book, url_file_name, image_data):
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
