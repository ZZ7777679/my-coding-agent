"""沙箱转发的二进制、POST、升级连接样本。 Binary, POST and upgraded-connection fixture."""

import http.server
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    """返回真实内容并回显字节，不依赖网络或第三方服务。

    Serve and echo bytes without external services.
    """

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        """返回大文件或升级到双向字节回显。 Return a large body or upgrade to duplex byte echo."""
        if self.path == "/duplex":
            self.send_response(101)
            self.send_header("Connection", "Upgrade")
            self.send_header("Upgrade", "test-echo")
            self.end_headers()
            while data := self.rfile.read1(65536):
                self.wfile.write(data)
                self.wfile.flush()
            self.close_connection = True
            return
        body = bytes(range(256)) * 8192
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """完整回显请求，覆盖同时读写与超出日志缓冲的负载。

        Echo the request, covering duplex I/O and payloads larger than log buffers.
        """
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
