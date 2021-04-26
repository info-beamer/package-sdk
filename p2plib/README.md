# Peer-to-Peer (P2P) support library

This library allows easy collaboration of [package services](https://info-beamer.com/doc/package-services)
running on multiple co-located devices. It uses the [Peer-to-Peer feature](https://info-beamer.com/doc/device-configuration#p2p)
for device detection, automatic leader selection and secure communication setup. 

It requires info-beamer OS with a version later than '202104xx'.

## Introduction

The library can be used to synchronize content playback or other state across multiple devices running the
same setup. Examples might be:

 * The selected leader device decides which item within a playlist to play next and notifies all follower devices.
 * An event (for example GPIO) triggered on a single device should trigger an action on all other devices as well.
 * Some data (like a counter) value should be synced across multiple devices.

A single device within the group of devices running the same setup is automatically promoted to leader. All
other devices become followers. The leader can broadcast short (recommended size ~1KB) messages to all
follower devices. Similarly any device can send a message to the current leader devices. The library can
also be used if only a single device is active: All messages are then locally delivery within the same program.
This allows you to use the same code regardless of the number of active devices.

The library automatically handles device detection within the local network using features provided by the
info-beamer OS. It then uses knowledge of other devices to select a single 'leader' among those devices.
It automatically sets up cryptographic keys that allow secure two-way communication across the devices.

For communication it uses UDP. The protocol guarantees at-most-once delivery of messages to other devices.
Due to the lossy nature of UDP it cannot guarantee delivery though. So you should be prepared to lose
messages if the network isn't reliably. Using Ethernet is preferred to WiFi. Message size should not exceed
around 1KB when serialized as JSON. The protocol overhead is around 40 bytes per message.

Clocks on all participating devices must be reasonably in sync (at most 3 seconds difference) for
communication to work. This also means that it won't work on completely offline devices that don't
have a correct time at all.

A network split might result in multiple leaders. Usually detection of new or disappeared peers happens
within 5-10 seconds and results in a newly selected leader.

## Example Code

```python
#!/usr/bin/python
import time, sys, threading
from p2plib import PeerGroup

class ExampleGroup(PeerGroup):
    def leader_thread(self):
        while self._leader_running:
            self.broadcast_to_all(
                value = time.time(),
            )
            time.sleep(1)

    def promote_leader(self, peer_info):
        print >>sys.stderr, "Now a leader"
        self._leader_running = True
        self._leader_thread = threading.Thread(target=self.leader_thread)
        self._leader_thread.daemon = True
        self._leader_thread.start()

    def demote_leader(self):
        print >>sys.stderr, "No longer a leader"
        self._leader_running = False
        self._leader_thread.join()

    def on_leader_message(self, message, peer_info):
        print >>sys.stderr, "received message from leader %r: %r" % (peer_info, message)

if __name__ == "__main__":
    group = ExampleGroup()
    while 1:
        time.sleep(1)
```

The ExampleGroup is based on the PeerGroup class. When instantiated it
automatically starts two threads handling peer detection and network
communication. After a short moment the `promote_leader` callback
will be called on a single device. In the example code this then starts
its own worker thread that sends a short message every second to all
other peers (including the leader peer itself) using `broadcast_to_all`.

On all devices running the same setup, the `on_leader_message` will be
called for each message sent by the leader. In the example the message
is written to stderr (and ends up in the log).

Should the current leader device go offline, it might take a few
seconds for all remaining devices to select a new leader.
The `promote_leader` will again be called on the selected device.

Should the previous offline leader return, the current leader will
be demoted and its `demote_leader` callback will be called. In the
example this shut down the thread.

Similarly a device can also send messages to the current leader
using `send_to_leader`. On the leader, such messages will
be delivered to the `on_peer_message` callback.

## Hints

If a device has disabled support Peer-to-Peer support or a device
is alone in its current networking environment, a PeerGroup
will consist of only this one device and it will be selected
as the leader. `broadcast_to_all` and `send_to_leader` will be
local method calls in that case. This allows you to use the
same code regardless of the Peer-to-Peer state on a device as
it transparently scales back from multiple devices to just a
single one.

A device should always handle lost messages. If the state you need
to sync is reasonably small, it might be easiest to just sync the
state from leader to follower every second. A lost message will
be hopefully received on a later attempt.

For precise timing it's recommended to send an exact future
timestamp within the message itself. That way all devices will
eventually receive the message and can begin acting on it based
on the timestamp within the message itself. The protocol itself
makes no guarantee with regards to latency. So you should not use
the `broadcast_to_all` to directly trigger events within the
`on_leader_message` callback.

# API

The following API calls are provided by the PeerGroup class.
The API is threadsafe and any property or method can be used
within all callbacks or by an external caller.

## Constructor `PeerGroup(port=None)`

Sets up a new peer group. The optional port argument can be provided
for force the use of a specific UDP port for communication. Usually
this is not recommended as an automatic port is selected based
on the current node directory.

Currently there is no way to shut down a constructed PeerGroup.
The code you write should always handle an unclean device shutdown
or termination of the process.

## Callback `group.setup_peer(self)`

This call is invoked once after the PeerGroup is fully set up.
It can be used to handle one-time initializations required on
all devices.

## Callback `group.promote_leader(self, peer_info)`

Called on the currently selected leader. Set up required data structures
needed to fulfil the leader role. This can include starting new background
threads. `peer_info` provides information about the leader.

## Callback `group.demote_leader(self)`

Called if the device is no longer the leader. You should shut down
any resources allocated in the `promote_leader` callback.

## Callback `group.promote_follower(self, peer_info)`

Called on a device if it's not a leader. Usually not required as
the distinction between a follower (so any device not being the leader)
and all devices (so leader and all followers) might not be useful.
Usually all devices (including the leader device itself) handle
data send by the leader and you don't need the follower distinction.
`peer_info` provides information about the follower.

## Callback `group.demote_follower(self)`

Called on a devices if it's no longer a follower.

## Callback `group.on_peer_added(self, peer_info)`

Called if a new peer is added to the group. This callback is called
before a peer with the same `ip` value in `peer_info` is provided in
an eventual call to `promote_follower` or `promote_leader`.

## Callback `group.on_peer_removed(self, peer_info)`

Called if a peer is no longer available. This callback is called
after a peer is demoted.

## Callback `group.on_leader_message(self, msg, peer_info)`

Called on a device if a message from the current leader is received.
`msg` is the data sent by `broadcast_to_all`. `peer_info` is some
metadata about the current leader. See below.

## Callback `group.on_peer_message(self, msg, peer_info)`

Called on the leader device if any of the other peers calls
`send_to_leader`. `msg` is the sent data and `peer_info` provides
information about the current leader.

## Property `group.is_follower`

True if the device is a follower (so not a leader).

## Property `group.is_follower`

True if the device is the selected leader.

## Property `group.num_peers`

Returns the total number of devices (including the one calling)
within the PeerGroup.

## Property `group.peers`

Returns a list of `peer_info` objects for all peers.

## Method `group.broadcast_to_all(**message)`

This method can be called on the leader to send the message
to all devices within the PeerGroup. If the device isn't
the leader, the call has no effect.

The data in `message` must be serializable as JSON and the
resulting serialized version should not exceed around 1KB
in total size. Otherwise message delivery might not be as
reliable as the resulting UDP paket will be fragmented.
It's best to only send short messages.

Note that this method also invokes `on_leader_message`
on the same local PeerGroup instance itself using a local
method call.

Message delivery is not guaranteed (as UDP is used for
transport and devices might disappear or be unreachable
at any time). The transport protocol guarantees at-most-once
delivery though if the message rate does not exceed
300 messages/second.

## Method `group.send_to_leader(**message)`

This method send a message from any device to the current
leader. It can be called on any device within the
current PeerGroup. If it's called on the leader itself,
a local method call to `on_peer_message` will be issued
instead of using network communication.

The data in `message` must be serializable as JSON and the
resulting serialized version should not exceed around 1KB
in total size. Otherwise message delivery might not be as
reliable as the resulting UDP paket will be fragmented.
It's best to only send short messages.

Message delivery is not guaranteed (as UDP is used for
transport and devices might disappear or be unreachable
at any time). The transport protocol guarantees at-most-once
delivery though if the message rate does not exceed
300 messages/second.

## `peer_info` Object

The `peer_info` object provides basic information about known peers.
It defines three properties: 

 * `ip` is the IP address of the peer. This is always '127.0.0.1' for this device.
 * `device_id` is the device id of the device.
 * `delta` is a timing delta and provides an estimated time offset to the local device in seconds.

If you need to keep a mapping from `peer_info` to your own data, use the
`ip` value as key, as it's the only value guaranteed to be unique across
different peers.
