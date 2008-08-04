# Miro - an RSS based video player application
# Copyright (C) 2005-2008 Participatory Culture Foundation
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

from threading import Event
import logging
import os
import traceback

import pygst
pygst.require('0.10')
import gobject
import gst
import gst.interfaces
import gtk
import pygtk

from miro import app
from miro import config
from miro import eventloop
from miro import prefs
from miro.download_utils import nextFreeFilename
from miro.plat.utils import confirmMainThread
from miro.plat import options

def to_seconds(t):
    return t / 1000000000.0

def from_seconds(s):
    return s * 1000000000

class Tester:
    def __init__(self, filename):
        self.done = Event()
        self.success = False
        self.actual_init(filename)

    def actual_init(self, filename):
        confirmMainThread()
        self.playbin = gst.element_factory_make('playbin')
        self.videosink = gst.element_factory_make("fakesink", "videosink")
        self.playbin.set_property("video-sink", self.videosink)
        self.audiosink = gst.element_factory_make("fakesink", "audiosink")
        self.playbin.set_property("audio-sink", self.audiosink)

        self.bus = self.playbin.get_bus()
        self.bus.add_signal_watch()
        self.watch_id = self.bus.connect("message", self.on_bus_message)

        self.playbin.set_property("uri", "file://%s" % filename)
        self.playbin.set_state(gst.STATE_PAUSED)

    def result(self):
        self.done.wait(5)
        self.disconnect()
        return self.success

    def on_bus_message(self, bus, message):
        confirmMainThread()
        if message.src == self.playbin:
            if message.type == gst.MESSAGE_STATE_CHANGED:
                prev, new, pending = message.parse_state_changed()
                if new == gst.STATE_PAUSED:
                    self.success = True
                    self.done.set()
                    # Success
            if message.type == gst.MESSAGE_ERROR:
                self.success = False
                self.done.set()

    def disconnect(self):
        confirmMainThread()
        self.bus.disconnect (self.watch_id)
        self.playbin.set_state(gst.STATE_NULL)
        del self.bus
        del self.playbin
        del self.audiosink
        del self.videosink

class Renderer:
    def __init__(self):
        confirmMainThread()
        logging.info("GStreamer version: %s", gst.version_string())
        self.playbin = gst.element_factory_make("playbin", "player")
        self.bus = self.playbin.get_bus()
        self.bus.add_signal_watch()
        self.bus.enable_sync_message_emission()        
        self.watch_id = self.bus.connect("message", self.on_bus_message)
        self.bus.connect('sync-message::element', self.on_sync_message)

        videosink = config.get(options.GSTREAMER_IMAGESINK)
        try:
            self.sink = gst.element_factory_make(videosink, "sink")

        except gst.ElementNotFoundError:
            logging.info("gstreamerrenderer: ElementNotFoundError '%s'" % videosink)
            videosink = "ximagesink"
            self.sink = gst.element_factory_make(videosink, "sink")

        except Exception, e:
            logging.info("gstreamerrenderer: Exception thrown '%s'" % e)
            logging.exception("sink exception")
            videosink = "ximagesink"
            self.sink = gst.element_factory_make(videosink, "sink")

        logging.info("GStreamer sink:    %s", videosink)
        self.playbin.set_property("video-sink", self.sink)

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        message_name = message.structure.get_name()
        if message_name == 'prepare-xwindow-id':
            imagesink = message.src
            imagesink.set_property('force-aspect-ratio', True)
            imagesink.set_xwindow_id(self.widget.window.xid)        

    def on_bus_message(self, bus, message):
        confirmMainThread()
        "recieves message posted on the GstBus"
        if message.type == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            logging.error("on_bus_message: gstreamer error: %s", err)
        elif message.type == gst.MESSAGE_EOS:
            app.playback_manager.on_movie_finished()

    def set_widget(self, widget):
        confirmMainThread()
        widget.connect_after("realize", self.on_realize)
        widget.connect("unrealize", self.on_unrealize)
        widget.connect("expose-event", self.on_expose)
        self.widget = widget

    def on_realize(self, widget):
        confirmMainThread()
        self.gc = widget.window.new_gc()
        self.gc.foreground = gtk.gdk.color_parse("black")

    def on_unrealize(self, widget):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_NULL)
        self.sink = None

    def on_expose(self, widget, event):
        confirmMainThread()
        if self.sink:
            if hasattr(self.sink, "expose"):
                self.sink.expose()
                return True
        else:
            widget.window.draw_rectangle(self.gc,
                                         True,
                                         0, 0,
                                         widget.allocation.width,
                                         widget.allocation.height)
            return True
        return False

    def can_play_file(self, filename):
        """whether or not this renderer can play this data"""
        return Tester(filename).result()

    def fill_movie_data(self, filename, movie_data, callback):
        confirmMainThread()
        d = os.path.join(config.get(prefs.ICON_CACHE_DIRECTORY), "extracted")
        try:
            os.makedirs(d)
        except:
            pass
        screenshot = os.path.join(d, os.path.basename(filename) + ".png")
        movie_data["screenshot"] = nextFreeFilename(screenshot)

        extracter = Extracter(filename, movie_data["screenshot"], handle_result)

    def go_fullscreen(self):
        """Handle when the video window goes fullscreen."""
        confirmMainThread()
        logging.debug("haven't implemented go_fullscreen method yet!")

    def exit_fullscreen(self):
        """Handle when the video window exits fullscreen mode."""
        confirmMainThread()
        logging.debug("haven't implemented exit_fullscreen method yet!")

    def select_item(self, anItem):
        self.select_file(anItem.getFilename())

    def select_file(self, filename):
        """starts playing the specified file"""
        confirmMainThread()
        self.stop()
        self.playbin.set_property("uri", "file://%s" % filename)

    def get_progress(self):
        confirmMainThread()
        logging.info("get_progress: what does this do?")

    def get_current_time(self):
        confirmMainThread()
        try:
            position, format = self.playbin.query_position(gst.FORMAT_TIME)
            return to_seconds(position)
        except Exception, e:
            logging.error("get_current_time: caught exception: %s" % e)
            return None

    def set_current_time(self, seconds):
        self.seek(seconds)

    def seek(self, seconds):
        confirmMainThread()
        event = gst.event_new_seek(1.0,
                                   gst.FORMAT_TIME,
                                   gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
                                   gst.SEEK_TYPE_SET,
                                   from_seconds(seconds),
                                   gst.SEEK_TYPE_NONE, 0)
        result = self.playbin.send_event(event)
        if not result:
            logging.error("seek failed")

    def play_from_time(self, seconds):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_PAUSED)

        self.playbin.get_state()

        self.seek(seconds)
        self.play()

    def get_duration(self):
        confirmMainThread()
        try:
            duration, format = self.playbin.query_duration(gst.FORMAT_TIME)
            return to_seconds(duration)
        except Exception, e:
            logging.error("get_duration: caught exception: %s" % e)
            return None

    def reset(self):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_NULL)

    def set_volume(self, level):
        confirmMainThread()
        self.playbin.set_property("volume", level * 4.0)

    def play(self):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_PLAYING)

    def pause(self):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_PAUSED)

    def stop(self):
        confirmMainThread()
        self.playbin.set_state(gst.STATE_NULL)
 
    def get_rate(self):
        confirmMainThread()
        return 256

    def set_rate(self, rate):
        confirmMainThread()
        logging.info("gstreamer set_rate: set rate to %s" % rate)

    def movie_data_program_info(self, movie_path, thumbnail_path):
        return (("python", 'plat/renderers/gst_extractor.py', movie_path, thumbnail_path), None)
