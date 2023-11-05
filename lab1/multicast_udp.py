import socket
import struct
import sys
from threading import Thread, Lock
import time

LISTEN_PORT = 6969
MULTICAST_TTL = 32
_ips = dict()
_mutex = Lock()


class Receiver(Thread):
    def __init__(self, address, id):
        Thread.__init__(self)
        self.address = address
        self.id = id

    def run(self):
        # Look up multicast group address in name server and find out IP version
        addrinfo = socket.getaddrinfo(self.address, None)[0]

        # Create a socket
        sock = socket.socket(addrinfo[0], socket.SOCK_DGRAM)

        # Allow multiple copies of this program on one machine
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind it to the port
        sock.bind(("", LISTEN_PORT))

        group_bin = socket.inet_pton(addrinfo[0], addrinfo[4][0])
        # Join group
        if addrinfo[0] == socket.AF_INET:  # IPv4
            mreq = group_bin + struct.pack("=I", socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        else:  # IPv6
            mreq = group_bin + struct.pack("@I", 0)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)

        while True:
            data, sender = sock.recvfrom(256)
            if data[0] == 2:
                with _mutex:
                    _ips.pop(sender[0], None)
            elif data[0] == 1:
                length = int.from_bytes(data[2:3])
                struct.unpack("!Bh" + str(length) + "s", data)
                with _mutex:
                    _ips[sender[0]] = time.time()
                #print(*_ips, sep="\n")
            else:
                continue


class Sender(Thread):
    def __init__(self, address, id):
        Thread.__init__(self)
        self.address = address
        self.id = id

    def run(self):
        addrinfo = socket.getaddrinfo(self.address, None)[0]

        sock = socket.socket(addrinfo[0], socket.SOCK_DGRAM)

        if addrinfo[0] == socket.AF_INET:  # IPv4
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
        else:  # IPv6
            sock.setsockopt(
                socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, MULTICAST_TTL
            )

        while True:
            data = struct.pack(
                "!Bh" + str(len(id)) + "s", 1, len(id), id.encode("utf-8")
            )
            sock.sendto(data, (addrinfo[4][0], LISTEN_PORT))
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: {0} <group address> <id>".format(sys.argv[0]))
        sys.exit(0)

    address, id = sys.argv[1], sys.argv[2]

    receiver = Receiver(address, id)
    receiver.start()

    sender = Sender(address, id)
    sender.start()

    while True:
        with _mutex:
            old_len = len(_ips)
            _ips = dict(filter(lambda item: time.time() - item[1] <= 10, _ips.items()))
            new_len = len(_ips)
        if new_len != old_len:
            print("\033[H\033[J")
            print(*_ips, sep="\n")
