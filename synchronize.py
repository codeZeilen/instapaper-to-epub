from instapaper import Instapaper
from instapaper import Bookmark
import shutil
from typing import Dict, Tuple, AnyStr, Iterable
from pathlib import Path
from download import download_bookmark_to_folder
import json
import os
import sys
import time

NUM_BOOKMARKS_TO_SYNCHRONIZE = 500 # The maximum value the API allows

# TODO: Fix empty title and wrong markup cases

def synchronize():
    online_folders: Iterable[Dict[AnyStr, AnyStr]] = [{'title': folder['title'], 'folder_id': str(folder['folder_id'])}  for folder in instapaper.folders()] + [{'title': "unread", 'folder_id': "unread"}, {'title': "archive", 'folder_id': "archive"}]
    local_folders = [{'title' : f.name.split("_")[:-1], 
                  'folder_id': f.name.split("_")[-1], 
                  'folder_path' : f} for f in Path('books').iterdir() if f.is_dir()]

    synchronize_folders(online_folders, local_folders)
    synchronize_bookmarks(online_folders, local_folders)

def synchronize_folders(online_folders, local_folders):
    online_folder_ids = [folder['folder_id'] for folder in online_folders]
    local_folder_ids = [folder['folder_id'] for folder in local_folders]
    folders_to_create = select_folders(
        set(online_folder_ids) - set(local_folder_ids), 
        online_folders)
    folders_to_delete = select_folders(
        set(local_folder_ids) - set(online_folder_ids), 
        local_folders)

    for folder in folders_to_create:
        (Path('books') / folder_to_directory_name(folder)).mkdir()

    for folder in folders_to_delete:
        # Move to not delete in case of error
        shutil.move(Path('books') / folder_to_directory_name(folder), 
                    Path('books') / 'deleted' / folder_to_directory_name(folder))

def select_folders(folder_ids, folders):
    return [folder for folder in folders if folder['folder_id'] in folder_ids]

def folder_to_directory_name(folder):
    return "_".join(folder['title'].split(" ")) + "_" + str(folder['folder_id'])

def synchronize_bookmarks(online_folders: Iterable[Dict], local_folders: Iterable[Dict]):
    """Actual synchronize: Three way merge between the online version, the local version, and a stored index"""
    # Step 1: Create a tree for online and local version
    print("-- Get Trees --")
    online_tree, bookmarks = create_tree_from_online_version(online_folders)
    local_tree, paths = create_tree_from_local_version(local_folders)
    if os.path.exists("index.json"):
        with open("index.json", "r") as f:
            index_tree = json.load(f)
            index_tree = {int(k): v for k, v in index_tree.items()}
    else:
        # In case there is no stored index, we use an empty dictionary. That way the diffing will interpret any inconsitencies as conflicts and resolve them by favoring the online version.
        index_tree = dict()

    print("Discovered online bookmarks: ", len(online_tree))
    print("Discovered local bookmarks: ", len(local_tree))

    # Step 2: Three-way-diff with tree stored in index (if there is no index then use the online tree) resulting in diff
    print("-- Start Diffing --")
    local_diff, online_diff = three_way_diff(online_tree, local_tree, index_tree)

    print("Online changes: ", len(online_diff))
    print("Local changes: ", len(local_diff))

    # Step 3: Apply diff to local and online version, conflicts are resolved by favoring online version
    print("-- Apply Diffs --")
    apply_diff_to_local_version(local_tree, paths, bookmarks, local_diff, local_folders)
    apply_diff_to_online_version(online_tree, bookmarks, online_diff)

    # Step 4: Store resulting tree for next iteration
    print("-- Storing Index --")
    resulting_tree, _ = create_tree_from_local_version(local_folders)
    with open("index.json", "w") as f:
        json.dump(resulting_tree, f)
   

# Create tree by traversing folders and bookmarks, tree nodes contain bookmark id and bookmark object
def create_tree_from_online_version(online_folders) -> Tuple[Dict[int, AnyStr], Dict[int, Bookmark]]:
    tree : Dict[int, AnyStr] = {}
    bookmarks : Dict[int, Bookmark]  = {}
    folder_ids = [folder['folder_id'] for folder in online_folders]
    for folder_id in folder_ids:
        for bookmark in instapaper.bookmarks(folder=folder_id, limit=NUM_BOOKMARKS_TO_SYNCHRONIZE):
            tree[bookmark.bookmark_id] = str(folder_id)
            bookmarks[bookmark.bookmark_id] = bookmark

    return tree, bookmarks

def create_tree_from_local_version(local_folders) -> Tuple[Dict[int, AnyStr], Dict[int, Bookmark]]:
    tree = {}
    paths = {}
    for folder in map(lambda x: x['folder_path'], local_folders):
        folder_id = folder.name.split('_')[-1]
        for book in folder.iterdir():
            book_id = int(book.stem.split('_')[-1]) # Extract bookmark id from filename
            tree[book_id] = folder_id
            paths[book_id] = book.absolute()

    return tree, paths

def three_way_diff(online_tree: Dict[int, AnyStr], local_tree: Dict[int, AnyStr], index_tree: Dict[int, AnyStr]):
    bookmark_ids = online_tree.keys()
    local_diff = {}
    online_diff = {}

    for bookmark_id in bookmark_ids:
        # NOTE: The following default keys ignore the case in which a bookmark is deleted
        online_folder = online_tree.get(bookmark_id, None)
        local_folder = local_tree.get(bookmark_id, None)
        index_folder = index_tree.get(bookmark_id, None)

        if online_folder == local_folder == index_folder:
            continue
        elif online_folder != index_folder and local_folder == index_folder:
            # Only online changed
            local_diff[bookmark_id] = online_folder
        elif local_folder != index_folder and online_folder == index_folder:
            # Only local changed
            online_diff[bookmark_id] = local_folder
        elif local_folder != index_folder and online_folder != index_folder and local_folder != online_folder:
            # Both changed and they disagree on the change
            # -> we take the online version
            local_diff[bookmark_id] = online_folder
        elif local_folder == online_folder and local_folder != index_folder:
            # Both changed but they agree on the change
            # -> nothing to do 
            pass
        else:
            print(f"Invalid situation on bookmark {bookmark_id} (online folder: {online_folder}, local folder: {local_folder}, index folder: {index_folder})",file=sys.stderr)
            sys.exit(1)
    
    return local_diff, online_diff

def apply_diff_to_local_version(tree, paths, bookmarks, local_diff : Dict, local_folders : Iterable[Dict]):
    for bookmark_id, folder_id in local_diff.items():
        folders = [f for f in local_folders if f["folder_id"] == folder_id]
        if not folders:
            sys.exit(f"Folder with id {folder_id} not found.")
        folder = folders[0]["folder_path"]
        if not bookmark_id in tree.keys():
            # Download and store book
            download_bookmark_to_folder(bookmarks[bookmark_id], folder.absolute())
            # Wait for 1 second to give server a break
            time.sleep(1)
        else:
            # We have the book, move it to the folder
            shutil.move(paths[bookmark_id], folder / paths[bookmark_id].name)

def apply_diff_to_online_version(tree, bookmarks: Dict[int, Bookmark], online_diff : Dict):
    for bookmark_id, folder_id in online_diff.items():
        if folder_id == "unread":
            bookmarks[bookmark_id].unarchive()
        elif folder_id == "archive":
            bookmarks[bookmark_id].archive()
        elif bookmark_id in tree.keys():
            bookmarks[bookmark_id].move(folder_id)
        else:
            raise Exception("Bookmark not found in local tree. Uploading bookmarks is not supported.")
        
if __name__ == '__main__':
    # NOTE: Consider refactoring to a class
    with open("oauth_config.json", "r") as f:
        oauth_config = json.load(f)
    with open("user_credentials.json", "r") as f:
        user_credentials = json.load(f)
    instapaper = Instapaper(oauth_config['id'], oauth_config['secret'])
    instapaper.login(user_credentials['username'], user_credentials['password'])

    synchronize()