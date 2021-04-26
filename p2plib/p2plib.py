#
# Part of info-beamer hosted. You can find the latest version
# of this file at:
#
# https://github.com/info-beamer/package-sdk
#
# Copyright (c) 2021 Florian Wesch <fw@info-beamer.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#
#     Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the
#     distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

VERSION = "1.0"

import requests, threading, time, sys, traceback, socket, json, hmac, hashlib, struct, os
from Crypto import Random
from Crypto.Cipher import AES
from binascii import unhexlify, hexlify
from collections import namedtuple

# This service uses its own UDP protocol. Multiple nodes might use
# this service. To avoid port collisions, based on a base port, a
# unique port number is derived for each node within the assigned
# setup.
P2P_GROUP_BASE_PORT = 61234

# The avoid delivering duplicate messages (either accidental or
# maliciously), each peer keeps a list of recently received messages.
# To avoid keeping too many of those the following limits the
# saved message ids.  
MAX_MESSAGE_PER_SEC = 300

def log(msg, name='p2plib.py'):
    print >>sys.stderr, "[{}] {}".format(name, msg)

PeerInfo = namedtuple('PeerInfo', 'ip device_id delta')

class Peer(object):
    def __init__(self, ip):
        self._ip = ip

        # protocol version
        self._version = 1

        # throw away packets if the device's time is off by more than x seconds
        self._discard_time_diff = 3

        # state to handle throwing away duplicate messages. The delivery
        # guarantees at-most-once semantics.
        self._last_cleanup = 0
        self._max_msg_ids = MAX_MESSAGE_PER_SEC * self._discard_time_diff
        self._msg_id_order = []
        self._msg_id_set = set()

    def update(self, device_id, pair_key, delta, is_leader):
        self._device_id = device_id
        self._pair_key = pair_key
        self._delta = delta
        self._is_leader = is_leader

    def add_seen_msg_id(self, msg_id, now):
        if msg_id in self._msg_id_set:
            return False
        if now > self._last_cleanup + 1 or len(self._msg_id_order) > self._max_msg_ids:
            self.cleanup_msg_ids(now)
            if len(self._msg_id_order) > self._max_msg_ids:
                return False
        discard_threshold = now + self._discard_time_diff
        if self._msg_id_order and discard_threshold < self._msg_id_order[-1][0]:
            # Our clock went backwards
            return False
        # self._msg_id_order is sorted by discard_threshold
        self._msg_id_order.append((discard_threshold, msg_id))
        self._msg_id_set.add(msg_id)
        return True

    def cleanup_msg_ids(self, now):
        deleted = 0
        while self._msg_id_order:
            discard_threshold, msg_id = self._msg_id_order[0]
            if now < discard_threshold:
                break
            self._msg_id_order.pop(0)
            self._msg_id_set.remove(msg_id)
            deleted += 1
        # log('cleaned up %d msg ids' % (deleted,))
        self._last_cleanup = now

    @property
    def is_leader(self):
        return self._is_leader

    @property
    def device_id(self):
        return self._device_id

    @property
    def ip(self):
        return self._ip

    @property
    def peer_info(self):
        return PeerInfo(self._ip, self._device_id, self._delta)

    def encode(self, data, direction):
        #
        # |     16      |     16      0   1           5                           x (%16=0)
        # |             |             | I | timestamp | {json message} ' <pad>  ' |
        # |             |             |                                           |
        # |             |- msg_id/IV -+-------------- Message --------------------|
        # |             |     '---------------------.----'                        |
        # |             |                        AES CBC                          |
        # |             |                           |                             |
        # |             |                           v                             |
        # |             |---------------------- Ciphertext -----------------------'
        # |      .---------- HMAC ------------------'                             |
        # |      v      |                                                         |
        # |---- MAC ----|                                                         |
        # 
        message = struct.pack("<BL", 
            direction << 7 | self._version, # info_bytes
            time.time()
        )
        message += json.dumps(
            data,
            ensure_ascii=False,
            separators=(',',':'),
        ).encode('utf8')
        message += ' ' * (16 - (len(message)-1) % 16 - 1) # pad
        msg_id = Random.get_random_bytes(16)
        cipher = AES.new(self._pair_key, AES.MODE_CBC, msg_id)
        encrypted = msg_id + cipher.encrypt(message)
        return hmac.HMAC(
            self._pair_key,
            encrypted,
            hashlib.sha256
        ).digest()[:16] + encrypted

    def decode(self, pkt, expected_direction):
        now = time.time()
        if now < 1000000000:
            # Don't receive with wrong local time
            return None
        mac, encrypted = pkt[:16], pkt[16:]
        if len(mac) != 16:
            return None
        if hmac.HMAC(
            self._pair_key,
            encrypted,
            hashlib.sha256
        ).digest()[:16] != mac:
            return None
        msg_id, ciphertext = encrypted[:16], encrypted[16:]
        if len(msg_id) != 16:
            return None
        if len(ciphertext) % 16:
            return None
        cipher = AES.new(self._pair_key, AES.MODE_CBC, msg_id)
        message = cipher.decrypt(ciphertext)
        hdr, data = message[:5], message[5:]
        info_byte, remote_ts = struct.unpack("<BL", hdr)
        version = info_byte & 0x7f
        if version != self._version:
            return None
        direction = info_byte >> 7
        if direction != expected_direction:
            return None
        # remote and our time too far off?
        if now >= remote_ts + self._discard_time_diff:
            return None
        if remote_ts <= now - self._discard_time_diff:
            return None
        if not self.add_seen_msg_id(msg_id, now):
            return None
        try:
            return json.loads(data)
        except Exception as err:
            return None

    def __repr__(self):
        return '<%d: %s>' % (self._device_id, self._ip)

ROLE_LEADER, ROLE_FOLLOWER = 1, 2
DIRECTION_LEADER_TO_PEER, DIRECTION_PEER_TO_LEADER = 0, 1

class PeerGroup(object):
    def __init__(self, port=None):
        # This assumed that the service is running within its node
        # directory.
        with open('config.json') as f:
            metadata = json.load(f)['__metadata']

        if port is not None:
            self._port = port
        else:
            self._port = P2P_GROUP_BASE_PORT + metadata.get('node_idx', 0)

        # Every node on the device can calculate its own
        # unicode node_scope value based on port, instance_id
        # and current work directory. Multiple devices
        # with the same setup assigned will all calculate
        # the same value. This avoid reusing the same
        # pairwise keys across multiple peer groups running
        # in different package services.
        self._node_scope = hashlib.sha256(
            '%d:%d:%s' % (
                self._port, metadata['instance_id'], os.getcwd(),
            )
        ).digest()

        self._no_p2p_fallback = [dict(
            device_id = metadata['device_id'],
            pair_key = '0' * 16,
            delta = 0,
            ip = '127.0.0.1',
        )]

        log("using peer group port %d, node scope %s" % (
            self._port, hexlify(self._node_scope)
        ))

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('0.0.0.0', self._port))

        self._role = None
        self._me = None
        self._leader = None
        self._peers, self._peers_lock = {}, threading.Lock()

        self.setup_peer()

        thread = threading.Thread(target=self._update_thread)
        thread.daemon = True
        thread.start()

        thread = threading.Thread(target=self._listen_thread)
        thread.daemon = True
        thread.start()

    ##----- Methods to overwrite ------

    def setup_peer(self):
        pass

    def promote_leader(self, peer_info):
        pass

    def demote_leader(self):
        pass

    def promote_follower(self, peer_info):
        pass

    def demote_follower(self):
        pass

    def on_peer_added(self, peer_info):
        pass

    def on_peer_removed(self, peer_info):
        pass

    # Handle message sent by broadcast_to_all.
    # The message is received at most once on all peers.
    def on_leader_message(self, msg, peer_info):
        pass

    # Handle message sent by send_to_leader.
    # This callback is only called when this peer is
    # a leader.
    def on_peer_message(self, msg, peer_info):
        pass

    ##----- Public Methods/Properties  -----

    @property
    def is_follower(self):
        return self._role == ROLE_FOLLOWER

    @property
    def is_leader(self):
        return self._role == ROLE_LEADER

    @property
    def num_peers(self):
        with self._peers_lock:
            return len(self._peers)

    @property
    def peers(self):
        peers = []
        with self._peers_lock:
            for ip, peer in self._peers.iteritems():
                peers.append(peer.peer_info)
        peers.sort()
        return peers

    def broadcast_to_all(self, **message):
        if self._role != ROLE_LEADER:
            return
        local_device = None
        with self._peers_lock:
            for ip, peer in self._peers.iteritems():
                if peer is self._me:
                    local_device = self._me
                else:
                    pkt = peer.encode(message,
                        direction = DIRECTION_LEADER_TO_PEER
                    )
                    self._sock.sendto(pkt, (ip, self._port))
        if local_device is not None:
            self.on_leader_message(json.loads(json.dumps(message)), local_device.peer_info)

    def send_to_leader(self, **message):
        local_device = None
        with self._peers_lock:
            if self._leader is self._me:
                local_device = self._me
            else:
                pkt = self._leader.encode(message,
                    direction = DIRECTION_PEER_TO_LEADER
                )
                self._sock.sendto(pkt, (self._leader.ip, self._port))
        if local_device is not None:
            self.on_peer_message(json.loads(json.dumps(message)), local_device.peer_info)

    ##--------------------------------

    def _listen_thread(self):
        while 1:
            try:
                pkt, (ip, port) = self._sock.recvfrom(2**16)
                if port != self._port:
                    continue
                receiver = None
                with self._peers_lock:
                    peer = self._peers.get(ip)
                    if peer is None:
                        continue
                    if peer.is_leader and self._role == ROLE_FOLLOWER:
                        receiver = self.on_leader_message
                        message = peer.decode(pkt,
                            expected_direction = DIRECTION_LEADER_TO_PEER
                        )
                    elif not peer.is_leader and self._role == ROLE_LEADER:
                        receiver = self.on_peer_message
                        message = peer.decode(pkt,
                            expected_direction = DIRECTION_PEER_TO_LEADER
                        )
                    else:
                        continue
                receiver(message, peer.peer_info)
            except Exception as err:
                traceback.print_exc()

    def _update_thread(self):
        while 1:
            try:
                r = requests.get(
                    'http://127.0.0.1:81/api/v1/peers/setup', timeout=0.5
                )
                peers = r.json()['peers']
                if not peers:
                    # If P2P is disabled or P2P traffic completely blocked
                    # for some reason, use a fallback list to make this
                    # device its own leader.
                    peers = self._no_p2p_fallback
                self._update_peers(peers)
            except Exception as err:
                log('cannot update setup peers: %s' % err)
                traceback.print_exc()
            time.sleep(3)

    def _update_peers(self, peers):
        me, leader = None, None
        seen = set()
        added, deleted = set(), set()
        with self._peers_lock:
            for idx, peer_info in enumerate(peers):
                device_id = peer_info['device_id']
                delta = peer_info['delta']
                ip = peer_info['ip']
                pair_key = hmac.HMAC(
                    unhexlify(peer_info['pair_key']),
                    self._node_scope,
                    hashlib.sha256
                ).digest()[:16] 
                seen.add(ip)
                peer = self._peers.get(ip)
                is_added = peer is None
                if is_added:
                    log('added peer %s' % ip)
                    peer = self._peers[ip] = Peer(ip)
                peer.update(device_id, pair_key, delta, idx == 0)
                if is_added:
                    added.add(peer.peer_info)

                # First device is always the leader. the peers/setup
                # response is guaranteed to be sorted the same on all devices
                # assuming they all know each other.
                if idx == 0:
                    leader = peer

                # This device will always be marked by 127.0.0.1
                if ip == '127.0.0.1':
                    me = peer
            known = set(self._peers.keys())
            for ip in known - seen:
                log('removed peer %s' % ip)
                peer = self._peers.pop(ip)
                deleted.add(peer.peer_info)

        self._me = me
        self._leader = leader 

        if me is None:
            new_role = None
        else:
            new_role = ROLE_LEADER if me == leader else ROLE_FOLLOWER

        for peer_info in added:
            self.on_peer_added(peer_info)

        if new_role != self._role:
            if self._role == ROLE_FOLLOWER:
                self.demote_follower()
            elif self._role == ROLE_LEADER:
                self.demote_leader()
            self._role = new_role
            if self._role == ROLE_FOLLOWER:
                self.promote_follower(me.peer_info)
            elif self._role == ROLE_LEADER:
                self.promote_leader(me.peer_info)

        for peer_info in deleted:
            self.on_peer_removed(peer_info)
