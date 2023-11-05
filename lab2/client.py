import argparse
from os.path import basename, getsize
import socket
import struct
import sys

BUFSIZ = 4096

class Client():
    def __init__(self, filename, address, port):
        self.filename = filename
        self.addr     = address
        self. port    = port 
    
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as sock:
            sock.connect((self.addr, self.port))
            filename_len = len(basename(self.filename))
            filename     = basename(self.filename)
            file_size    = getsize(self.filename)
            header = struct.pack("!h" + str(filename_len) + "sq" ,
                                 filename_len, filename.encode(), file_size)
            sock.send(header)
            
            with open(self.filename, "rb") as file:
                buffer = file.read(BUFSIZ)
                while buffer:
                    sock.send(buffer)
                    buffer = file.read(BUFSIZ)
            

def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', nargs='?')
    parser.add_argument('address', nargs='?')
    parser.add_argument('-p', '--port', default='6969', dest='port', type=int)
    return parser

if __name__ == '__main__':
    parser = create_parser()
    args = parser.parse_args()
    
    client = Client(args.filename, args.address, args.port)
    client.run()
