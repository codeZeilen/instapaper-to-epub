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

class ExtendedBookmark(object):
    _book_file_name: str
    _original_title: str
    _bookmark_id: str
    sanitized_content: str

    def __init__(self, bookmark: Bookmark):
        self.bookmark = bookmark
        self._book_file_name = ""
        self._original_title = ""
        self._bookmark_id = ""
        self.sanitized_content = ""

    def __getattr__(self, name):
        return getattr(self.bookmark, name)

    #
    # Downloading content
    #
    def get_content(self) -> Optional["ExtendedBookmark"]:   
        print(f'Downloading {self.title if self.title else self.url}')
        self.get_and_sanitize_content()
        if not self.sanitized_content:
            print(f'Skipping {self.title} due to empty content.')
            return None

        return self
    
    def get_and_sanitize_content(self):
        self.sanitized_content = self.html if self.html else "no content"
        self.sanitized_content = self.sanitized_content.strip()
    
    #
    # Adapting Bookmark properties
    #
    @property
    def bookmark_id(self) -> str:
        if not self._bookmark_id:
            self._bookmark_id = str(self.bookmark.bookmark_id)
        return self._bookmark_id

    @property
    def title(self) -> str:        
        if not self._original_title:
            self._original_title = self.bookmark.title
            if not self.bookmark.title:
                self._title = self.url
            self._title = f'{BOOK_FILE_PREFIX}: {self.bookmark.title}'
        return self._title
    
    @property
    def original_title(self) -> str:
        if not self._original_title:
            self.title # to force initialization
        return self._original_title
            
    @property
    def book_file_name(self) -> str:
        if not self._book_file_name:
            self._book_file_name = self.make_safe_filename(self.title) + '_' + self.bookmark_id
        return self._book_file_name

    def make_safe_filename(self, file_name: str) -> str:
        # Define a whitelist of characters that are allowed in filenames
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)

        # Remove all characters from the string that are not in the whitelist
        safe_filename = ''.join(c for c in file_name if c in valid_chars)

        # Replace spaces with underscores
        safe_filename = safe_filename.replace(' ', '_')

        # Shorten filename
        safe_filename = safe_filename[:100]

        return safe_filename


class BookmarkDownloader(object):

    def __init__(self, instapaper: Optional[Instapaper] = None):
        self.instapaper = instapaper

        self.books_folder = Path('./books')
        self.books_folder.mkdir(exist_ok=True)
        self.tmp_images_folder = Path('./tmp_images')
        self.tmp_images_folder.mkdir(exist_ok=True)

    def login(self):
        # TODO: Refactor to get configuration as parameters    
        with open("oauth_config.json", "r") as f:
            oauth_config = json.load(f)
        with open("user_credentials.json", "r") as f:
            user_credentials = json.load(f)
        self.instapaper = Instapaper(oauth_config['id'], oauth_config['secret'])
        self.instapaper.login(user_credentials['username'], user_credentials['password'])

    def download(self, num_bookmarks_to_retrieve: int = 70):
        for bookmark in self.instapaper.bookmarks(limit=num_bookmarks_to_retrieve):
            self.download_bookmark_to_folder(bookmark, self.books_folder)

    def download_bookmark_to_folder(self, bookmark, folder_path : Path):
        bookmark = ExtendedBookmark(bookmark)
        if self.bookmark_already_downloaded(bookmark):
            print(f'Skipping {bookmark.original_title}, as corresponding book already exists.')
            return
      
        if not bookmark.get_content():
            return

        book = self.create_full_book(bookmark.bookmark_id, bookmark.original_title, bookmark.sanitized_content)
        self.write_book(book, bookmark.book_file_name, folder_path)

    def bookmark_already_downloaded(self, bookmark):
        return (self.books_folder / f'{bookmark.book_file_name}.epub').exists()

    #
    # EPub Creation
    #
    def create_full_book(self, bookmark_id, title, sanitized_content) -> epub.EpubBook:
        book = self.new_book(title, bookmark_id)

        cover = self.create_cover(title, bookmark_id)
        book.add_item(cover)

        full_content = self.sanitize_and_add_images(book, sanitized_content)
        chapter = self.create_chapter(title, bookmark_id, full_content)
        book.add_item(chapter)

        self.add_navigation_files(book, cover, chapter)

        return book

    def new_book(self, title, book_id: str = "") -> epub.EpubBook:
        book = epub.EpubBook()
        book.set_identifier(book_id)
        book.set_title(title)
        return book

    def create_cover(self, title: str, book_id: str):
        cover_content = f'<html><body><h1 style="width: 70%; margin: 0 auto;">{title}</h1></body></html>'
        cover = epub.EpubHtml(
            title=title, 
            file_name=f'{book_id}_cover.xhtml')
        cover.content = cover_content
        return cover

    def create_chapter(self, title: str, book_id: str, sanitized_content: str) -> epub.EpubHtml:
        chapter = epub.EpubHtml(
            title=title, 
            file_name=f'{book_id}.xhtml')
        chapter.content = sanitized_content
        return chapter

    def sanitize_and_add_images(self, book: epub.EpubBook, sanitized_content: str) -> str:
        return self.shrink_replace_and_add_images(book, sanitized_content)

    def add_navigation_files(self, book: epub.EpubBook, cover: epub.EpubCover, chapter) -> None:
        book.toc = (cover,chapter,)
        
        # Add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define the spine of the book
        book.spine = [cover, chapter,]

    def write_book(self, book: epub.EpubBook, book_file_name:str, folder_path: Path):
        book_file_path = folder_path / f'{book_file_name}.epub'
        try: 
            epub.write_epub(book_file_path, book, {})
        except Exception as e:
            print(f'Error writing book {book_file_name}: {e}')
            book_file_path.unlink()
            raise e

    #
    # Sanitizing content
    #
    def shrink_replace_and_add_images(self, book, html) -> str:
        soup = BeautifulSoup(html, 'html.parser')
        replaced_images = dict()

        images = soup.find_all('img')
        images = set(filter(lambda i: i.has_attr('src') and not i['src'].startswith('data:'), images))
        for img in images:  
            image_url = urlparse(img['src']) 
            url_file_name = hashlib.md5(img['src'].encode('utf-8')).hexdigest() + image_url.path.split('/')[-1]
            file_path = self.tmp_images_folder / url_file_name
            
            # Special Cases
            if (not file_path.suffix) or (file_path.suffix not in ('.jpg', '.jpeg', '.gif', '.png', '.bmp', '.tiff')):
                self.replace_img_with_alt_text(img, soup)
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
                image_data = self.convert_image(image_data)
                self.add_image_to_book(book, url_file_name, image_data)
                replaced_images[img['src']] = url_file_name
                img['src'] = url_file_name
            except:
                self.replace_img_with_alt_text(img, soup)   

        return str(soup)

    def replace_img_with_alt_text(self, img, soup) -> bool:
        alt_text = img.get('alt')
        if alt_text:
            # Preserve the image content by using the alt text
            alt_par = soup.new_tag('p')
            alt_par.string = alt_text
            img.replace_with(alt_par)
            return True
        else:
            return False
        
    def convert_image(self, image_data) -> bytes:
        image = Image.open(io.BytesIO(image_data))
        image = image.convert('L')
        return image.tobytes()

    def add_image_to_book(self, book, url_file_name, image_data) -> None:
        img_path = Path(url_file_name)
        book_image = epub.EpubItem(uid=img_path.name, 
            file_name=url_file_name, 
            media_type=mime.guess_type(url_file_name)[0], 
            content=image_data)
        book.add_item(book_image)
        return url_file_name

# Download ebooks when started as a script
if __name__ == '__main__':
    if len(sys.argv) > 1:
        num_bookmarks_to_retrieve = int(sys.argv[1])
    else:
        num_bookmarks_to_retrieve = 70
    
    downloader = BookmarkDownloader()
    downloader.login()
    downloader.download(num_bookmarks_to_retrieve)
