import argparse
from os.path import basename, getsize
import socket
from threading import Thread
import time

HOST     = "127.0.0.1"  # Standard loopback interface address (localhost)
BUFSIZ   = 4096
INTERVAL = 3 * 10**9    #3 sec.

class ClientHandler(Thread):
    def __init__(self, conn, addr):
        Thread.__init__(self)
        self.conn = conn
        self.addr = addr[0] + ':' + str(addr[1])

    def run(self):
        filename_len = int.from_bytes(self.conn.recv(2))
        filename     = self.conn.recv(filename_len).decode()
        file_size    = int.from_bytes(self.conn.recv(8))

        with open("uploads/" + basename(filename), 'wb') as file:
            read_bytes, prev_read_bytes = 0, 0
            start_time = time.time_ns()
            last_time  = start_time

            while read_bytes < file_size:
                buffer = self.conn.recv(BUFSIZ)
                file.write(buffer)
                read_bytes += len(buffer)
                current_time = time.time_ns()

                if current_time - last_time > INTERVAL:
                    curent_speed = (read_bytes - prev_read_bytes) / 1024 / 1024 / (current_time - last_time) * 10**9
                    avg_speed    = read_bytes / 1024 / 1024 / (current_time - start_time) * 10**9
                    print(self.addr, ':', "curr =", curent_speed, "Mb/s", ",", "avg =", avg_speed, "Mb/s")
                    last_time = time.time_ns()
                    prev_read_bytes = read_bytes

            if 0 < time.time_ns() - start_time <= INTERVAL:
                avg_speed = read_bytes / 1024 / 1024 / (time.time_ns() - start_time) * 10**9
                print(self.addr, ':', "avg =", avg_speed, "Mb/s")

        print(self.addr, ':', 
              "Success" if getsize("uploads/" + basename(filename)) == file_size 
              else "Failure: received: " + str(read_bytes) + "expected: " + str(file_size))


class Server():
    def __init__(self, port):
        self.port = port

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as sock:
            sock.bind((HOST, self.port))
            sock.listen()
            while True:
                conn, addr = sock.accept()
                handler = ClientHandler(conn, addr)
                handler.start()


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default='6969', dest='port', type=int)
    return parser

if __name__ == '__main__':
    parser = create_parser()
    args = parser.parse_args()

    server = Server(args.port)
    server.start()
