import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from campusguard.server.api import _StreamLimiter
from campusguard.server.client import RemoteServerClient


class _FakeStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        frames = (b"first-jpeg-frame", b"second-jpeg-frame")
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            for frame in frames:
                self.wfile.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                    + frame + b"\r\n"
                )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass


class LiveStreamClientTests(unittest.TestCase):
    def test_reads_multipart_frames_until_stopped(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeStreamHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        frames = []
        stop = threading.Event()
        try:
            client = RemoteServerClient(f"http://127.0.0.1:{server.server_address[1]}", "test-token")
            def received(frame):
                frames.append(frame)
                if len(frames) >= 2:
                    stop.set()
            client.stream_frames("CAM-001", received, stop.is_set)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(frames, [b"first-jpeg-frame", b"second-jpeg-frame"])


class StreamLimiterTests(unittest.TestCase):
    def test_limits_streams_per_desktop(self):
        limiter = _StreamLimiter()
        for _ in range(limiter.MAX_PER_ADDRESS):
            self.assertTrue(limiter.acquire("10.0.0.10"))
        self.assertFalse(limiter.acquire("10.0.0.10"))
        limiter.release("10.0.0.10")
        self.assertTrue(limiter.acquire("10.0.0.10"))

    def test_limits_total_streams_across_the_server(self):
        limiter = _StreamLimiter()
        for index in range(limiter.MAX_GLOBAL // limiter.MAX_PER_ADDRESS):
            address = f"10.0.0.{index + 1}"
            for _ in range(limiter.MAX_PER_ADDRESS):
                self.assertTrue(limiter.acquire(address))
        self.assertFalse(limiter.acquire("10.0.1.1"))
        limiter.release("10.0.0.1")
        self.assertTrue(limiter.acquire("10.0.1.1"))


if __name__ == "__main__":
    unittest.main()
