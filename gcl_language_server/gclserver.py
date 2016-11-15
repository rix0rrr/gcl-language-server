import urlparse
import gcl


class GCLServer(object):
    def __init__(self):
        self.documents = {}

    def update_document(self, uri, text, parse_error_notifier):
        assert isinstance(uri, basestring)
        assert isinstance(text, basestring)
        doc = self.documents[uri] = Document(uri, text)
        try:
            doc.normal_parse()
            parse_error_notifier(uri, 1, 1, [])
        except gcl.ParseError as e:
            parse_error_notifier(uri, e.sourcelocation.lineno, e.sourcelocation.col, e.error_message.split('\n'))
        except Exception as e:
            import traceback
            traceback.print_exc()


class Document(object):
    def __init__(self, uri, text):
        self.url = urlparse.urlparse(uri)
        self.text = text
        self._normal_parse = None
        self._error_parse = None

    def normal_parse(self):
        if self._normal_parse is None:
            self._normal_parse = gcl.reads(self.text, filename=self.url.path)
        return self._normal_parse
