from pyfakefs.fake_filesystem_unittest import TestCase
import os
from copy import deepcopy
import json
from synchronize import BookmarkSynchronizer
from instapaper import Instapaper
import unittest
from typing import Optional

# Full table of diffing cases
# | online | local | index |  
# |--------|-------|-------|
# |   a    |   a   |   a   |x 
# |   a    |   a   |   b   |x
# |   a    |   a   |   -   |x 
# |   a    |   b   |   a   |x 
# |   a    |   b   |   b   |x 
# |   a    |   b   |   -   |x 
# |   a    |   -   |   a   |x 
# |   a    |   -   |   b   |x 
# |   a    |   -   |   -   |x 
# |   b    |   a   |   b   |x 
# |   b    |   a   |   a   |x 
# |   b    |   a   |   -   |x 
# |   b    |   b   |   a   |x 
# |   b    |   b   |   b   |x
# |   b    |   b   |   -   |x 
# |   b    |   -   |   a   |x 
# |   b    |   -   |   b   |x 
# |   b    |   -   |   -   |x 
# |   -    |   a   |   a   |x 
# |   -    |   a   |   b   |x 
# |   -    |   a   |   -   |x 
# |   -    |   b   |   a   |x 
# |   -    |   b   |   b   |x 
# |   -    |   b   |   -   |x 
# |   -    |   -   |   a   | 
# |   -    |   -   |   b   |
# |   -    |   -   |   -   |x 

# Table of equivalent cases (x,y can be {a,b})
# | online | local | index | description  
# |--------|-------|-------|---------------
# |   x    |   x   |   x   | none changed
# |   -    |   -   |   -   | none added
# |   x    |   x   |   y   | online local changed consistently
# |   x    |   x   |   -   | both added consistently (or: index cleared)
# |   x    |   y   |   x   | local changed
# |   y    |   x   |   x   | online changed
# |   x    |   y   |   -   | both added inconsistently (or: index cleared)
# |   x    |   -   |   x   | local deleted
# |   x    |   -   |   y   | local deleted, online changed
# |   x    |   -   |   -   | online added
# |   -    |   x   |   x   | online deleted
# |   -    |   x   |   y   | online deleted, local changed
# |   -    |   x   |   -   | local added
# |   -    |   -   |   x   | both deleted


fixture_file_name = "InPa_Test_Bookmark_1.epub"
fixture_file_contents = "test content"
fixture_bookmark_data = dict(
    bookmark_id=1,
    title="Test Bookmark",
    url="http://example.com",
    starred=False,
    html=fixture_file_contents
)

fixture_folders = {
    "unread": dict(folder_id="unread", title="unread", bookmarks=[]),
    "archive": dict(folder_id="archive", title="archive", bookmarks=[]),
    "1": dict(folder_id="1", title="testfolder", bookmarks=[]),
    "2": dict(folder_id="2", title="testfolder2", bookmarks=[]),
}



class MockedBookmark(object):
    bookmark_id: int
    title: str
    url: str
    starred: bool

    def __init__(self, folders):
        self.folders = folders

    def unarchive(self):
        self.move("unread")

    def archive(self):
        self.move("archive")

    def move(self, folder_id):
        for folder in self.folders.values():
            if self in folder["bookmarks"]:
                folder["bookmarks"].remove(self)
        self.folders[folder_id]["bookmarks"].append(self)            

class MockedInstapaper(Instapaper):

    def __init__(self, folders, bookmark):
        self._folders = folders
        self.http = self
        self.bookmark = bookmark

    def request(self, url: str, **kwargs):
        if url.find("archive") > -1:
            self.bookmark.archive()
        return {"status": "200"}, None

    def folders(self):
        return self._folders.values()

    def bookmarks(self, folder="unread", limit=100):
        return self._folders[folder]["bookmarks"]

class SynchronizationTest(TestCase):

    def setUp(self):
        self.setUpPyfakefs()

        self.folders = deepcopy(fixture_folders)
        self.bookmark = MockedBookmark(self.folders)
        self.bookmark.__dict__.update(fixture_bookmark_data)

        self.fs.create_dir("/home/instapaper")
        for folder in self.folders.values():
            folder_name = self.folder_name_for_folder(folder["folder_id"])
            self.fs.create_dir(f'/home/instapaper/books/{folder_name}')
        os.chdir('/home/instapaper')

        self.synchronizer = BookmarkSynchronizer()
        self.synchronizer.instapaper = MockedInstapaper(self.folders, self.bookmark)

    def folder_name_for_folder(self, folder_id):
        folder = self.folders[folder_id]
        return f'{folder["title"]}_{folder["folder_id"]}'

    def bookmark_online_folder(self, folder_id):
        if folder_id == None:
            return
        self.bookmark.move(folder_id)

    def bookmark_local_folder(self, folder_id):
        if folder_id == None:
            return
        folder_name = self.folder_name_for_folder(folder_id)
        self.fs.create_file(f'/home/instapaper/books/{folder_name}/{fixture_file_name}', 
                            contents=fixture_file_contents)
        
    def bookmark_index_folder(self, folder_id):
        if folder_id == None:
            return
        index = {self.bookmark.bookmark_id: folder_id}
        self.fs.create_file(f'/home/instapaper/index.json', 
                            contents=json.dumps(index))

    def folder_ids_without(self, folder_id):
        folder_ids = list(self.folders.keys())
        if folder_id in folder_ids:
            folder_ids.remove(folder_id)
        return folder_ids
    
    def assert_bookmark_online_in_folder(self, folder_id:Optional[str]):
        if folder_id:
            self.assertIn(self.bookmark, self.folders[folder_id]["bookmarks"])
        for other_folder_id in self.folder_ids_without(folder_id):
            self.assertNotIn(self.bookmark, self.folders[other_folder_id]["bookmarks"], f"Found in {other_folder_id}, folders state is {self.folders}")

    def assert_bookmark_local_in_folder(self, folder_id:Optional[str]):
        if folder_id:
            folder_name = self.folder_name_for_folder(folder_id)
            self.assertTrue(os.path.exists(f'/home/instapaper/books/{folder_name}/{fixture_file_name}'))
        for other_folder_id in self.folder_ids_without(folder_id):
            folder_name = self.folder_name_for_folder(other_folder_id)
            self.assertFalse(os.path.exists(f'/home/instapaper/books/{folder_name}/{fixture_file_name}'))

    def assert_bookmark_index_in_folder(self, folder_id:Optional[str]):
        with open('/home/instapaper/index.json', 'r') as f:
            index = json.load(f)
        if folder_id:
            self.assertEqual(index[str(self.bookmark.bookmark_id)], str(folder_id), "Index was " + str(index)) 
        else:
            self.assertNotIn(str(self.bookmark.bookmark_id), index.keys())

    def state_before(self, online:Optional[str]="", local:Optional[str]="", index:Optional[str]=""):
        if "" in [online, local, index]:
            self.fail("Before state not fully specificed")
        self.bookmark_online_folder(online)
        self.bookmark_local_folder(local)
        self.bookmark_index_folder(index)

    def assert_state(self, online:Optional[str]="", local:Optional[str]="", index:Optional[str]=""):
        if "" in [online, local, index]:
            self.fail("Before state not fully specificed")
        self.assert_bookmark_online_in_folder(online)
        self.assert_bookmark_local_in_folder(local)
        self.assert_bookmark_index_in_folder(index)

    def test_no_change(self):
        self.state_before(online="1", local="1", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="1", local="1", index="1")

    def test_no_added(self):
        self.state_before(online=None, local=None, index=None)
        self.synchronizer.synchronize()
        self.assert_state(online=None, local=None, index=None)

    def test_local_changed(self):
        self.state_before(online="1", local="2", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="2", local="2", index="2")

    def test_online_changed(self):
        self.state_before(online="2", local="1", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="2", local="2", index="2")
    
    def test_both_changed_consistenly(self):
        self.state_before(online="2", local="2", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="2", local="2", index="2")

    def test_both_changed_inconsistently(self):
        self.state_before(online="2", local="1", index="unread")
        self.synchronizer.synchronize()
        self.assert_state(online="2", local="2", index="2")

    def test_online_added(self):
        self.state_before(online="unread", local=None, index=None)
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_local_added(self):
        """We do not upload files, so there will be no new file online."""
        self.state_before(online=None, local="unread", index=None)
        self.synchronizer.synchronize()
        self.assert_state(online=None, local="unread", index="unread")

    def test_both_added_consistently_or_index_cleared(self):
        self.state_before(online="unread", local="unread", index=None)
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_both_added_inconsistently_or_index_cleared(self):
        self.state_before(online="unread", local="archive", index=None)
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_online_deleted(self):
        self.state_before(online=None, local="unread", index="unread")
        self.synchronizer.synchronize()
        self.assert_state(online=None, local=None, index=None)

    def test_online_deleted_local_changed(self):
        self.state_before(online=None, local="archive", index="unread")
        self.synchronizer.synchronize()
        # The following models the API behavior to not list bookmarks beyond a count of 500 while still allowing us to operate on those bookmarks.
        # Thus, locally archiving a bookmark, will put it in the online archive. Normally it would not be listed though.
        self.assert_state(online="archive", local=None, index=None)

    def test_local_deleted(self):
        """We ignore local deletions for now, as there is no failure handling for inconsistent file system operations."""
        self.state_before(online="unread", local=None, index="unread")
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local=None, index=None)
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_local_deleted_online_changed(self):
        """We ignore local deletions for now, as there is not failure handling for inconsistent file system operations."""
        self.state_before(online="archive", local=None, index="unread")
        self.synchronizer.synchronize()
        self.assert_state(online="archive", local="archive", index="archive")

    def test_both_deleted(self):
        self.state_before(online=None, local=None, index="unread")
        self.synchronizer.synchronize()
        self.assert_state(online=None, local=None, index=None)

    #
    # Tests for special patching operations
    #
    def test_local_changed_to_unread(self):
        self.state_before(online="1", local="unread", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_local_changed_to_archive(self):
        self.state_before(online="1", local="archive", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="archive", local="archive", index="archive")

    def test_online_changed_to_unread(self):
        self.state_before(online="unread", local="1", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="unread", local="unread", index="unread")

    def test_online_changed_to_archive(self):
        self.state_before(online="archive", local="1", index="1")
        self.synchronizer.synchronize()
        self.assert_state(online="archive", local="archive", index="archive")

if __name__ == '__main__':
    unittest.main()