#!/usr/bin/env python
#
# A Telepathy Observer for the Call interface.
#
# Copyright (C) 2012  Collabora Ltd.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
# USA
#
# Authors:
#     Danielle Madeley  <danielle.madeley@collabora.co.uk>

from __future__ import print_function
import sys

from gi.repository import TelepathyGLib as Tp
from gi.repository import GObject, Gio

def print_obj(obj, *args, **kwargs):
    if isinstance(obj, Tp.CallChannel):
        colour = 31 # red
    elif isinstance(obj, Tp.CallContent):
        if obj.get_media_type() == Tp.MediaStreamType.AUDIO:
            colour = 32 # green
        else:
            colour = 34 # blue
    elif isinstance(obj, Tp.CallStream):
        if obj._content.get_media_type() == Tp.MediaStreamType.AUDIO:
            colour = 33 # yellow
        else:
            colour = 35 # magenta
    else:
        colour = 37 # white

    sys.stdout.write('\033[%s%sm' % (
        '1;' if kwargs.get('bold', False) else '',
        colour))
    print(*args)
    sys.stdout.write('\033[0m')

def join_flags(flags):
    return ', '.join(flags.value_nicks) if flags != 0 else '--'

def create_gdbus_proxy(proxy, iface, path=None):
    if not path: path = proxy.get_object_path()

    return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
        Gio.DBusProxyFlags.NONE, None,
        proxy.get_bus_name(), path, iface, None)

def dump_media_properties(media_proxy, obj):
    for prop in media_proxy.get_cached_property_names():
        print_obj(obj, "   - %s: %s" % (prop,
            media_proxy.get_cached_property(prop).unpack()))

def stream_local_sending_state_changed(stream):
    print_obj(stream, "Stream (%s) local sending state: %s" % (
        stream._content.get_name(),
        stream.get_local_sending_state().value_name),
        bold=True)

def stream_members_changed(stream):
    print_obj(stream, "Stream (%s) members:" % stream._content.get_name(),
        bold=True)
    for contact, state in stream.get_remote_members().iteritems():
        state = Tp.SendingState(state).value_name
        print_obj(stream, " %s: %s" % (contact.get_identifier(), state),
            bold=True)

def stream_media_properties_changed(media_proxy, changed, invalidated,
    stream):

    print_obj(stream,
        "Stream (%s) media properties:" % stream._content.get_name())
    dump_media_properties(media_proxy, stream)
    print_obj(stream, '---')

def endpoint_media_properties_changed(media_proxy, changed, invalidated,
    stream):

    print_obj(stream,
        "Endpoint (%s) media properties:" % stream._content.get_name())
    dump_media_properties(media_proxy, stream)
    print_obj(stream, '---')

def streams_added(content, streams, user_data):
    def func(stream, result, user_data):
        stream.prepare_finish(result)

        print_obj(stream, "New stream on %s (%s)" % (
            stream._content.get_name(),
            stream.get_object_path()))
        print_obj(stream, "  Interfaces:")
        for iface in content.get_property('interfaces'):
            print_obj(stream, "   - %s" % iface)

        stream_local_sending_state_changed (stream)
        stream_members_changed(stream)

        stream.connect('notify::local-sending-state',
            lambda s, *args: stream_local_sending_state_changed(s), None)
        stream.connect('remote-members-changed',
            lambda s, *args: stream_members_changed(s),
            None)

        # we have to get the media interface the old fashioned way
        media_proxy = create_gdbus_proxy(stream,
            Tp.IFACE_CALL_STREAM_INTERFACE_MEDIA)
        stream_media_properties_changed (media_proxy, None, None, stream)
        media_proxy.connect('g-properties-changed',
            stream_media_properties_changed, stream)

        # and the endpoint
        for path in media_proxy.get_cached_property('Endpoints'):
            endpoint = create_gdbus_proxy(stream,
                Tp.IFACE_CALL_STREAM_ENDPOINT, path=path)
            endpoint_media_properties_changed(endpoint, None, None, stream)
            endpoint.connect('g-properties-changed',
                endpoint_media_properties_changed, stream)

    for stream in streams:
        stream._content = content
        stream.prepare_async(None, func, None)

def streams_removed(content, streams, reason, user_data):
    for stream in streams:
        print_obj(stream, "Stream (%s) removed" % stream._content.get_name())

def content_media_properties_changed(media_proxy, changed, invalidated,
    content):

    print_obj(content, "  Content (%s) media properties:" % content.get_name())
    dump_media_properties(media_proxy, content)

def content_added(channel, content, user_data):
    def func(content, result, user_data):
        content.prepare_finish(result)

        print_obj(content, "New content: %s (%s)" % (
            content.get_name(), content.get_object_path()))
        print_obj(content,
            "  Media type: %s" % content.get_media_type().value_name)
        print_obj(content, "  Interfaces:")
        for iface in content.get_property('interfaces'):
            print_obj(content, "   - %s" % iface)

        streams_added(content, content.get_streams(), None)

        content.connect('streams-added', streams_added, None)
        content.connect('streams-removed', streams_removed, None)

        # we have to get the media interface the old fashioned way
        media_proxy = create_gdbus_proxy(content,
            Tp.IFACE_CALL_CONTENT_INTERFACE_MEDIA)
        content_media_properties_changed (media_proxy, None, None, content)
        media_proxy.connect('g-properties-changed',
            content_media_properties_changed, content)

    content.prepare_async(None, func, None)

def content_removed(channel, content, reason, user_data):
    print_obj(content, "Content removed: %s" % content.get_name())

def invalidated(channel, domain, code, message, user_data):
    print_obj(channel, "Channel closed: %s" % message)

def state_changed(channel, pspec, user_data):
    state, flags, details, reason = channel.get_state()
    print_obj(channel, "State changed: %s (flags: %s)" % (
        state.value_name, join_flags(flags)))

def channel_members_changed(channel):
    # just request the members here
    print_obj(channel, "Channel members:", bold=True)
    for contact, flags in channel.get_members().iteritems():
        flags = Tp.CallMemberFlags(flags)
        print_obj(channel,
            " %s: %s" % (contact.get_identifier(), join_flags(flags)),
            bold=True)

def observe_call(client, account, conn, channels, dispatch_op, requests,
    context, user_data):

    for channel in channels:
        if not isinstance(channel, Tp.CallChannel):
            continue

        print_obj(channel, "Observing channel %s" % channel.get_object_path())

        print_obj(channel,
            " -- %s --" % ("outgoing" if channel.get_property('requested') else "incoming"))
        state_changed (channel, None, None)

        for content in channel.get_contents():
            content_added(channel, content, None)

        channel_members_changed(channel)

        channel.connect('content-added', content_added, None)
        channel.connect('content-removed', content_removed, None)
        channel.connect('invalidated', invalidated, None)
        # state-changed signal does not work nicely with g-i
        channel.connect('notify::state', state_changed, None)
        channel.connect('members-changed',
            lambda c, *args: channel_members_changed(c),
            None)

    context.accept()

def __main__():
    factory = Tp.AutomaticClientFactory.new(Tp.DBusDaemon.dup())
    client = Tp.SimpleObserver.new_with_factory(factory, False,
        "CallObserver", True, observe_call, None)
    client.add_observer_filter({
        Tp.PROP_CHANNEL_CHANNEL_TYPE: Tp.IFACE_CHANNEL_TYPE_CALL,
        Tp.PROP_CHANNEL_TARGET_HANDLE_TYPE: int(Tp.HandleType.CONTACT),
    })
    client.register()

    print("Observing calls as %s" % client.get_bus_name())
    print("Ctrl-C to end")

    loop = GObject.MainLoop()

    try:
        loop.run()
    except KeyboardInterrupt:
        print()
        print("Quitting")
        pass

if __name__ == '__main__':
    __main__()
