# Instapaper to EPUB Folders Synchronization

A simple program to synchronize Instapaper articles to EPUB files in folders. Includes a script to simply download unread bookmarks.

Current features:
 - Synchronizing folders
 - Synchronizing unread and archive

Current limitations:
 - Only synchronizes up to the API limit of 500 articles 
 - Does not delete articles (Due to the API limit, actual deletions are indistinguishable from articles disappearing behind the API limit)
 - Some articles result in EPUB files that can not be opened in some ebook readers (e.g. Tolino).

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

## Usage of Synchronization

To start the synchronization, execute:

```
python3 synchronize.py
```

The program synchronizes your bookmarks to `./books`. Moving the books in the folders will move the bookmarks online on the next synchronization.


## Usage of Export

Currently, only downloading bookmarks chronologically is supported:

```
python3 download.py [limit_of_number_of_bookmarks]
```

You can set the number of bookmarks that should be downloaded with `limit_of_number_of_bookmarks`. If none is provided, the limit is currently 70 bookmarks.

You can find the downloaded books in `./books`. 


## Auxiliary Files
The folder `./tmp_images` contains converted images from the downloaded bookmarks and can be deleted after completing the download.

The file `index.json` contains the state resulting from the previous synchronization. If it is missing (or deleted), the synchronization will treat the online state as the primary state.
