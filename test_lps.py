import mock
try:
    from StringIO import StringIO as StreamBuf
except ImportError:
    from io import BytesIO as StreamBuf
import unittest
from gcl_language_server import lps

from jsonrpc import jsonrpc2

class TestLps(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.handler = mock.Mock()

    def serve(self):
        input = StreamBuf(bytes(''.join(self.requests)), 'utf-8')
        output = StreamBuf()

        server = lps.LanguageProtocolServer(self.handler, input, output)
        server.run()
        return output.getvalue()

    def queue(self, **kwargs):
        request_data = jsonrpc2.JSONRPC20Request(**kwargs).json
        self.requests.append('Content-Length: %d\n\n' % len(request_data) + request_data)

#----------------------------------------------------------------------

    def test_initialize(self):
        self.queue(method='initialize', params={"processId":6512, "rootPath":"/", "capabilities":{}, "trace":"off"})
        output = self.serve()
        self.assertNotEquals('', output)
