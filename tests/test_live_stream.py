import unittest

from campusguard.server.api import _StreamLimiter


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
