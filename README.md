# Instapaper to EPUB Export

A simple script to download articles bookmarked in Instapaper to a set of EPUB files.

## Installation

 1. Get Python 3.10 or newer (older might work, but I did not test it).
 2. Install requirements via pip3:
```
pip3 install -r requirements.txt
```
 3. Create config files: 
```
cp user_credentials.json.tmpl user_credentials.json;
cp oauth_config.json.tmpl oauth_config.json
``` 
 4. Fill in config files: 
  - oauth_config.json: token id and secret
  - user_credentials.json: username and password

## Usage

Currently, only downloading bookmarks chronologically is supported:

```
python3 download.py [limit_of_number_of_bookmarks]
```

You can set the number of bookmarks that should be downloaded with `limit_of_number_of_bookmarks`. If none is provided, the limit is currently 70 bookmarks.

You can find the downloaded books in `./books`. The folder `./tmp_images` contains converted images from the downloaded bookmarks and can be deleted after completing the download.

## Known Limitations

Some articles result in EPUB files that can not be opened in some ebook readers (e.g. Tolino).