import argparse
import dns
from dns import message
import select
import socket
import struct
import sys
import uuid


BUFSIZ = 4096

SERVER_ADDR = "0.0.0.0"
DNS_ADDR = socket.gethostbyname("dns.google")
DNS_PORT = 53

# PROTOCOL PARAMETERS
VER = b"\x05"
RSV = b"\x00"

M_NOAUTH = b"\x00"
M_NOTAVAILABLE = b"\xff"

CMD_CONNECT = b"\x01"

ATYP_IPV4 = b"\x01"
ATYP_DOMAINNAME = b"\x03"

# STATUS CODE
ST_REQUEST_GRANTED = b"\x00"
ST_HOST_UNREACHABLE = b"\x04"
ST_COMMAND_NOT_SUPPORTED = b"\x07"


def client_greeting(data):
    """
    The client connects to the server, and sends a version
    identifier/method selection message
    """
    # Client Version identifier/method selection message
    # +----+----------+----------+
    # |VER | NMETHODS | METHODS  |
    # +----+----------+----------+

    if VER != data[0:1]:
        return M_NOTAVAILABLE

    nmethods = data[1]
    methods = data[2:]
    if len(methods) != nmethods:
        return M_NOTAVAILABLE

    for method in methods:
        if method == ord(M_NOAUTH):
            return M_NOAUTH

    return M_NOTAVAILABLE


def server_choice(data, client):
    """
    The client connects to the server, and sends a version
    identifier/method selection message
    The server selects from one of the methods given in METHODS, and
    sends a METHOD selection message
    """
    # Server Method selection message
    # +----+--------+
    # |VER | METHOD |
    # +----+--------+

    method = client_greeting(data)

    reply = VER + method
    client.sendall(reply)

    return method != M_NOTAVAILABLE


def request_client(data):
    """Client request details"""
    # +----+-----+-------+------+----------+----------+
    # |VER | CMD |  RSV  | ATYP | DST.ADDR | DST.PORT |
    # +----+-----+-------+------+----------+----------+

    if data[0:1] != VER or data[1:2] != CMD_CONNECT or data[2:3] != RSV:
        return None

    if data[3:4] == ATYP_IPV4:
        return ATYP_IPV4
    elif data[3:4] == ATYP_DOMAINNAME:
        return ATYP_DOMAINNAME
    else:
        return None


def request(status, atype, dst):
    """
    The SOCKS request information is sent by the client as soon as it has
    established a connection to the SOCKS server, and completed the
    authentication negotiations.  The server evaluates the request, and
    returns a reply
    """
    # Server Reply
    # +----+-----+-------+------+----------+----------+
    # |VER | REP |  RSV  | ATYP | BND.ADDR | BND.PORT |
    # +----+-----+-------+------+----------+----------+

    bnd = socket.inet_aton(dst.getsockname()[0]) + struct.pack(
        "!H", dst.getsockname()[1]
    )
    reply = VER + status + RSV + atype + bnd

    return reply


def init_server(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    sock.bind((SERVER_ADDR, port))
    sock.listen(5)
    sock.setblocking(False)

    return sock


def init_dns():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.connect((DNS_ADDR, DNS_PORT))
    sock.setblocking(False)

    return sock


def init_dst_sock(dst_addr, dst_port):
    dst_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    dst_sock.connect((dst_addr, dst_port))
    dst_sock.setblocking(False)

    return dst_sock


class Socks5Proxy:
    def __init__(self, port):
        self.port = port
        self.server = init_server(port)
        self.dns = init_dns()

    def handle_client_leave(self, client, clients, inputs, clients_dst, dst_clients):
        print(
            f"Client {client.getsockname()[0]}:{client.getsockname()[1]} disconnected"
        )

        dst = clients_dst.get(client, None)

        if dst:
            dst.close()

            del dst_clients[dst]
            del clients_dst[client]
            if dst in inputs:
                inputs.remove(dst)

        clients.remove(client)

    def handle_dst_leave(self, dst, clients, inputs, clients_dst, dst_clients):
        print(f"Dst {dst.getsockname()[0]}:{dst.getsockname()[1]} disconnected")

        client = dst_clients.get(dst, None)

        if client:
            client.close()
            del dst_clients[dst]
            del clients_dst[client]
            if client in clients:
                clients.remove(client)
            if client in inputs:
                inputs.remove(client)

    def handle_dst_message(self, dst, inputs, dst_clients, data):
        client = dst_clients.get(dst, None)

        if not client:
            print("Dst sent message to unknown client", file=sys.stderr)
            dst.close()
            inputs.remove(dst)
            return

        print(
            f"Dst {dst.getsockname()[0]}:{dst.getsockname()[1]} sent message to {client.getsockname()[0]}:{client.getsockname()[1]}"
        )
        try:
            client.send(data)
        except Exception:
            client.close()
            dst.close()
            inputs.remove(dst)
            inputs.remove(client)

    def handle_client_greeting(self, client, clients, inputs, data):
        if server_choice(data, client):  # Проверка версии socks
            print(
                f"Client {client.getsockname()[0]}:{client.getsockname()[1]} accepted"
            )
            clients.append(client)

    def resolve_domainname(self, data):
        domainname_len = data[4]
        domainname = data[5 : 5 + domainname_len]
        dst_port = struct.unpack("!H", data[5 + domainname_len : len(data)])[0]

        return domainname, dst_port

    def create_dns_query(self, domainname):
        dns_id = uuid.uuid4()
        dns_query = dns.message.make_query(
            str(domainname)[2:-1], dns.rdatatype.A, id=dns_id
        )
        dns_query.flags |= dns.flags.CD | dns.flags.AD
        return dns_query, dns_id

    def handle_client_conn_request(
        self,
        client,
        inputs,
        clients,
        clients_dst,
        dst_clients,
        dns_id_clients,
        dns_id_port,
        data,
    ):
        dst_atype = request_client(data)
        print(
            f"Client {client.getsockname()[0]}:{client.getsockname()[1]} sent message about dst"
        )

        if dst_atype == ATYP_IPV4:  # IPv4
            dst_addr = socket.inet_ntoa(data[4:-2])
            dst_port = struct.unpack("!H", data[8:])[0]
            dst = init_dst_sock(dst_addr, dst_port)
            reply = request(ST_REQUEST_GRANTED, dst_atype, dst)

            client.send(reply)

            clients_dst[client] = dst
            dst_clients[dst] = client
            inputs.append(dst)
        elif dst_atype == ATYP_DOMAINNAME:  # Domain name
            domainname, dst_port = self.resolve_domainname(data)
            dns_query, dns_id = self.create_dns_query(domainname)
            self.dns.send(dns_query.to_wire())
            dns_id_clients[dns_id] = client
            dns_id_port[dns_id] = dst_port
            print(
                f"Client {client.getsockname()[0]}:{client.getsockname()[1]} waiting a domain resolve from dns server"
            )
        else:  # Unsupported
            print(f"Unsupported atype, message: {data}", file=sys.stderr)
            request(ST_COMMAND_NOT_SUPPORTED, ATYP_IPV4, client)
            client.close()
            clients.remove(client)
            inputs.remove(client)

    def handle_client_message(self, client, clients, inputs, clients_dst, data):
        print(
            f"Client {client.getsockname()[0]}:{client.getsockname()[1]} sent message to dst"
        )
        dst = clients_dst.get(client, None)

        if not dst:
            print(
                f"Error with destination to client {client.getsockname()[0]}:{client.getsockname()[1]}",
                file=sys.stderr,
            )
            client.close()
            clients.remove(client)
            inputs.remove(client)
        else:
            dst.send(data)

    def handle_connection_reset_error(
        self, sock, inputs, clients, clients_dst, dst_clients
    ):
        sock.close()
        inputs.remove(sock)
        if sock in clients:
            dst = clients_dst.get(sock)
            if dst:
                dst.close()
                del clients_dst[sock]
                del dst_clients[dst]
                inputs.remove(dst)
                clients.remove(sock)
        else:
            client = dst_clients.get(sock)
            client.close()
            del clients_dst[client]
            del dst_clients[sock]
            clients.remove(client)
            inputs.remove(client)

        print(f"Connection reset for sock", file=sys.stderr)

    def handle_message(
        self,
        sock,
        clients,
        inputs,
        clients_dst,
        dst_clients,
        dns_id_clients,
        dns_id_port,
    ):
        try:
            data = sock.recv(BUFSIZ)
        except ConnectionResetError:
            self.handle_connection_reset_error(
                sock, inputs, clients, clients_dst, dst_clients
            )
            return
        except socket.error as e:
            # print('Error while receiving data:', e.strerror, file=sys.stderr)
            return

        if not data:
            if sock in clients:  # клиент выходит
                self.handle_client_leave(
                    sock, clients, inputs, clients_dst, dst_clients
                )
            else:
                self.handle_dst_leave(sock, clients, inputs, clients_dst, dst_clients)

            sock.close()
            inputs.remove(sock)
        elif sock in dst_clients.keys():  # Пришло сообщение от dst
            self.handle_dst_message(sock, inputs, dst_clients, data)
        elif sock not in clients:  # Первое сообщение клиента после коннекта
            self.handle_client_greeting(sock, clients, inputs, data)
        elif sock not in clients_dst.keys():
            self.handle_client_conn_request(
                sock,
                inputs,
                clients,
                clients_dst,
                dst_clients,
                dns_id_clients,
                dns_id_port,
                data,
            )
        else:
            self.handle_client_message(sock, clients, inputs, clients_dst, data)

    def resolve_dns_response(self, response_data):
        response = dns.message.from_wire(response_data)

        if response.answer:
            for answer in response.answer:
                if answer.rdtype == dns.rdatatype.A:
                    return answer[0].address, response.id

        return None, response.id

    def handle_dns_response(
        self, inputs, dst_clients, clients_dst, dns_id_clients, dns_id_port
    ):
        response_data = self.dns.recv(BUFSIZ)
        dst_addr, dns_id = self.resolve_dns_response(response_data)

        client = dns_id_clients.get(dns_id, None)

        if not client:
            print(f"Client does not waiting dns", file=sys.stderr)
            del dns_id_clients[dns_id]
            del dns_id_port[dns_id]
            return
        if not dst_addr:
            print(
                f"Dns does not know about domain for {client.getsockname()[0]}:{client.getsockname()[1]}",
                file=sys.stderr,
            )
            reply = request(ST_HOST_UNREACHABLE, ATYP_IPV4, client)
        else:
            dst_port = dns_id_port[dns_id]
            dst = init_dst_sock(dst_addr, dst_port)
            if not dst:
                reply = request(ST_HOST_UNREACHABLE, ATYP_IPV4, client)
            else:
                inputs.append(dst)
                clients_dst[client] = dst
                dst_clients[dst] = client

                reply = request(ST_REQUEST_GRANTED, ATYP_IPV4, dst)
        print(
            f"Dns received resolved domain for {client.getsockname()[0]}:{client.getsockname()[1]}"
        )
        client.send(reply)
        del dns_id_clients[dns_id]
        del dns_id_port[dns_id]

    def run(self):
        inputs = [self.server, self.dns]
        clients = []
        clients_dst = {}
        dst_clients = {}
        dns_id_clients = {}
        dns_id_port = {}

        print(
            f"Server start receiving messages on address {self.server.getsockname()}\n"
        )
        while True:
            reads, _, _ = select.select(inputs, [], inputs)

            for sock in reads:
                if sock == self.server:  # клиент хочет присоединиться
                    conn, addr = self.server.accept()
                    print(f"New connection: {addr}")
                    inputs.append(conn)
                elif sock == self.dns:  # днс прислал ответ
                    self.handle_dns_response(
                        inputs, dst_clients, clients_dst, dns_id_clients, dns_id_port
                    )
                else:  # кто-то хочет отправить сообщение
                    self.handle_message(
                        sock,
                        clients,
                        inputs,
                        clients_dst,
                        dst_clients,
                        dns_id_clients,
                        dns_id_port,
                    )


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default="1080", dest="port", type=int)
    return parser


if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()

    proxy = Socks5Proxy(args.port)
    proxy.run()
