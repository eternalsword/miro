# Miro - an RSS based video player application
# Copyright (C) 2010 Participatory Culture Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the OpenSSL
# library.
#
# You must obey the GNU General Public License in all respects for all of
# the code used other than OpenSSL. If you modify file(s) with this
# exception, you may extend this exception to your version of the file(s),
# but you are not obligated to do so. If you do not wish to do so, delete
# this exception statement from your version. If you delete this exception
# statement from all source files in the program, then also delete it here.

import os
import threading

from miro import app
from miro import config
from miro import eventloop
from miro import messages
from miro import playlist
from miro import prefs

import libdaap

# Helper utilities
# Translate neutral constants to native protocol constants with this, or
# fixup strings if necessary.
def daap_item_fixup(item_id, entry):
    daapitem = []
    # no need for id -> miid because that's the indexing key.

    # Easy ones - can do a direct translation
    mapping = [('name', 'minm'), ('enclosure_format', 'asfm'),
               ('size', 'assz'), ('duration', 'astm')]
    for p, q in mapping:
        if isinstance(entry[p], unicode):
            attribute = (q, entry[p].encode('utf-8'))
        else:
            attribute = (q, entry[p])
        daapitem.append(attribute)

    # Manual ones
    daapitem.append(('miid', item_id))

    # Also has movie or tv shows but Miro doesn't support it so make it
    # a generic video.
    if entry['file_type'] == 'video':
        daapitem.append(('aeMK', libdaap.DAAP_MEDIAKIND_VIDEO))
    else:
        daapitem.append(('aeMK', libdaap.DAAP_MEDIAKIND_AUDIO))

    return daapitem
    
class SharingManagerBackend(object):
    types = ['videos', 'audios']
    id    = None                # Must be None
    items = dict()              # Neutral format - not really needed.
    daapitems = dict()          # DAAP format XXX - index via the items
    # XXX daapplaylist should be hidden from view. 
    daap_playlists = dict()     # Playlist, in daap format
    playlist_item_map = dict()  # Playlist -> item mapping


    def register_protos(self, proto):
        pass

    def handle_item_list(self, message):
        self.make_item_dict(message.items)

    def handle_items_changed(self, message):
        # If items are changed, just redelete and recreate the entry.
        for x in message.removed:
            del self.items[x.id]
            del self.daapitems[x.id]
        self.make_item_dict(message.added)
        self.make_item_dict(message.changed)

    # Note: this should really be a util function and be separated
    def make_daap_playlists(self, items):
        mappings = [('title', 'minm'), ('id', 'miid'), ('id', 'mper')]
        for x in items:
            attributes = []
            for p, q in mappings:
                if isinstance(getattr(x, p), unicode):
                    attributes.append((q, getattr(x, p).encode('utf-8')))
                else:
                    attributes.append((q, getattr(x, p)))
            attributes.append(('mpco', 0))    # Parent container ID
            attributes.append(('mimc', 0))    # Item count
            self.daap_playlists[x.id] = attributes

    def handle_playlist_added(self, obj, added):
        self.make_daap_playlists(added)

    def handle_playlist_changed(self, obj, changed):
        for x in changed:
            del self.daap_playlists[x.id]
        self.make_daap_playlists(changed)

    def handle_playlist_removed(self, obj, removed):
        for x in removed:
            del self.daap_playlists[x.id]

    def populate_playlists(self):
        self.make_daap_playlists(playlist.SavedPlaylist.make_view())
        for playlist_id in self.daap_playlists.keys():
            # Save the position as well?  But I don't think it matters, remote
            # guy can sort himself.
            self.playlist_item_map[playlist_id] = [x.item_id
              for x in playlist.PlaylistItemMap.playlist_view(playlist_id)]

    def start_tracking(self):
        for t in self.types:
            app.info_updater.item_list_callbacks.add(t, self.id,
                                                self.handle_item_list)
            app.info_updater.item_changed_callbacks.add(t, self.id,
                                                self.handle_items_changed)

        self.populate_playlists()

        app.info_updater.connect('playlists-added',
                                 self.handle_playlist_added)
        app.info_updater.connect('playlists-changed',
                                 self.handle_playlist_changed)
        app.info_updater.connect('playlists-removed',
                                 self.handle_playlist_removed)

    def stop_tracking(self):
        for t in self.types:
            app.info_updater.item_list_callbacks.remove(t, self.id,
                                                self.handle_item_list)
            app.info_updater.item_changed_callbacks.remove(t, self.id,
                                                self.handle_items_changed)

        app.info_updater.disconnect(self.handle_playlist_added)
        app.info_updater.disconnect(self.handle_playlist_changed)
        app.info_updater.disconnect(self.handle_playlist_removed)

    def get_filepath(self, itemid):
        return self.items[itemid]['path']

    def get_playlists(self):
        playlists = []
        for k in self.daap_playlists.keys():
            playlists.append(('mlit', self.daap_playlists[k]))
        return playlists

    def get_items(self, playlist_id=None):
        # FIXME Guard against handle_item_list not having been run yet?
        # But if it hasn't been run, it really means at there are no items
        # (at least, in the eyes of Miro at this stage).
        # XXX cache me.  Ideally we cache this per-protocol then we create
        # this eagerly, then the self.items becomes a mapping from proto
        # to a list of items.

        # Easy: just return
        if not playlist_id:
            return self.daapitems
        return [x for x in self.daapitems
                  if x.id in playlist_item_map[playlist_id]]

    def make_item_dict(self, items):
        # See lib/messages.py for a list of full fields that can be obtained
        # from an ItemInfo.  Note that, this only contains partial information
        # as it does not contain metadata about the item.  We do make one or
        # two assumptions here, in particular the file_type will always either
        # be video or audio.  For the actual file extension we strip it off
        # from the actual file path.  We create a dict object for this,
        # which is not very economical.  Is it possible to just keep a 
        # reference to the ItemInfo object?
        interested_fields = ['id', 'name', 'size', 'file_type', 'file_format',
                             'video_path', 'duration']
        for x in items:
            name = x.name
            size = x.size
            duration = x.duration
            file_type = x.file_type
            path = x.video_path
            f, e = os.path.splitext(path)
            # Note! sometimes this doesn't work because the file has no
            # extension!
            if e:
                e = e[1:]
            self.items[x.id] = dict(name=name, size=size, duration=duration,
                                  file_type=file_type, path=path,
                                  enclosure_format=e)
            self.daapitems[x.id] = daap_item_fixup(x.id, self.items[x.id])

class SharingManager(object):
    def __init__(self):
        self.sharing = False
        self.discoverable = False
        self.config_watcher = config.ConfigWatcher(
            lambda func, *args: eventloop.add_idle(func, 'config watcher',
                 args=args))
        self.callback_handle = self.config_watcher.connect('changed',
                               self.on_config_changed)
        # Create the sharing server backend that keeps track of all the list
        # of items available.  Don't know whether we can just query it on the
        # fly, maybe that's a better idea.
        self.backend = SharingManagerBackend()
        # We can turn it on dynamically but if it's not too much work we'd
        # like to get these before so that turning it on and off is not too
        # onerous?
        self.backend.start_tracking()
        # Enable sharing if necessary.
        self.twiddle_sharing()

    def on_config_changed(self, obj, key, value):
        # We actually know what's changed but it's so simple let's not bother.
        self.twiddle_sharing()

    def twiddle_sharing(self):
        sharing = app.config.get(prefs.SHARE_MEDIA)
        discoverable = app.config.get(prefs.SHARE_DISCOVERABLE)

        if sharing != self.sharing:
            if sharing:
                # TODO: if this didn't work, should we set a timer to retry
                # at some point in the future?
                if not self.enable_sharing():
                    return
            else:
                self.disable_discover()
                self.disable_sharing()

        # Short-circuit: if we have just disabled the share, then we don't
        # need to check the discoverable bits since it is not relevant, and
        # would already have been disabled anyway.
        if not self.sharing:
            return

        if discoverable != self.discoverable:
            if discoverable:
                self.enable_discover()
            else:
                self.disable_discover()

    def enable_discover(self):
        name = app.config.get(prefs.SHARE_NAME)
        self.mdns_ref = libdaap.install_mdns(name)
        self.discoverable = True

    def disable_discover(self):
        self.discoverable = False
        libdaap.uninstall_mdns(self.mdns_ref)
        del self.mdns_ref

    def server_thread(self):
        libdaap.runloop(self.server)

    def enable_sharing(self):
        try:
            name = app.config.get(prefs.SHARE_NAME)
            self.server = libdaap.make_daap_server(self.backend, name=name)
            self.thread = threading.Thread(target=self.server_thread,
                                           name='DAAP Server Thread')
            self.thread.start()
            self.sharing = True
        except OSError:
            # Woups.  Mostly probably the bind() failed due to EADDRINUSE.
            self.sharing = False

        return self.sharing

    def disable_sharing(self):
        self.sharing = False
        self.server.shutdown()
        self.thread.join()
        del self.thread
        del self.server

