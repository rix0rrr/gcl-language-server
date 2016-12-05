import logging
import attr
from attr.validators import instance_of

from jsonrpc import JSONRPCResponseManager, Dispatcher
from jsonrpc import jsonrpc2


logger = logging.getLogger('gcls')


def log_exceptions(fn):
    def wrapped_function(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            logger.exception('Error handling RPC')
            raise
    wrapped_function.__name__ = fn.__name__
    return wrapped_function


class LanguageProtocolServer(object):
    def __init__(self, handler, istream, ostream):
        self.handler = handler
        self.istream = istream
        self.ostream = ostream
        self.running = True
        self.dispatcher = Dispatcher({
            'initialize': self.initialize,
            'shutdown': self.shutdown,
            '$/setTraceNotification': self.setTraceNotification,
            'textDocument/didOpen': self.didOpen,
            'textDocument/didChange': self.didChange,
            'textDocument/hover': self.hover,
            'textDocument/definition': self.definition,
            'textDocument/completion': self.completion,
            })

    def run(self):
        headers = []
        while self.running:
            line = self.istream.readline()
            if not line:
                break
            line = line.strip()
            logger.debug('< %s' % line)
            if not line:
                logger.debug('Headers: %r' % headers)
                headers = parse_headers(headers)
                if 'content-length' in headers:
                    length = int(headers['content-length'])
                    body = self.istream.read(length)
                    logger.debug('Read body: %s' % body)
                    self.write_output(self.handle(body))
                headers = []
            else:
                headers.append(line)

    def handle(self, payload):
        response = JSONRPCResponseManager.handle(payload, self.dispatcher)
        if not response:
            return None
        logger.debug('Response: %s', response.json)
        return response.json

    def write_output(self, output):
        if output:
            self.ostream.write('Content-Length: %d\r\n' % len(output))
            self.ostream.write('\r\n')
            self.ostream.write(output)
            self.ostream.flush()

    def publish_diagnostics(self, uri, diagnostics):
        request = jsonrpc2.JSONRPC20Request(method='textDocument/publishDiagnostics', is_notification=True, params={
            'uri': uri,
            'diagnostics': [attr.asdict(d) for d in diagnostics]
        })
        self.write_output(request.json)

    @log_exceptions
    def initialize(self, processId, rootPath, capabilities, trace):
        return {"capabilities": {
                    "textDocumentSync": TextDocumentSyncKind.Full,
                        "hoverProvider": True,
                        "completionProvider": {
                            "resolveProvider": False,
                            "triggerCharacters": ['.']
                        },
                        "definitionProvider": False  # FIXME
                    }
                }

    def shutdown(self):
        self.running = False

    def setTraceNotification(self, value):
        pass

    @log_exceptions
    def didOpen(self, textDocument):
        return self.handler.updateDocument(textDocument['uri'], textDocument['text'], self.publish_diagnostics)

    @log_exceptions
    def didChange(self, textDocument, contentChanges):
        return self.handler.updateDocument(textDocument['uri'], contentChanges[0]['text'], self.publish_diagnostics)

    @log_exceptions
    def hover(self, textDocument, position):
        try:
            value = self.handler.getHoverInfo(textDocument['uri'], position['line'] + 1, position['character'] + 1)
            assert value is None or isinstance(value, HoverInfo)
            if value and value.value:
                return {'contents': attr.asdict(value)}
            return {}
        except Exception as e:
            return {'contents': {'language': 'text', 'value': str(e)}}
        # contents: string =>  markdown
        # range { start { line, character }, end { line, character }}

    @log_exceptions
    def definition(self, textDocument, position):
        # FIXME: N/IMPL
        uri = textDocument['uri']
        line, character = position['line'], position['character']
        return {'uri': uri,
                'range': {'line': 0, 'character': 0}}

    @log_exceptions
    def completion(self, textDocument, position):
        completions = self.handler.getCompletions(textDocument['uri'], position['line'] + 1, position['character'] + 1)
        for c in completions.values():
            assert isinstance(c, Completion)

        return {'isIncomplete': False,
                'items': [attr.asdict(c) for c in completions]}


def parse_headers(lines):
    ret = {}
    for line in lines:
        key, value = line.split(':', 1)
        ret[key.lower().strip()] = value.strip()
    return ret


class LanguageProtocolHandler(object):
    def updateDocument(self, uri, text, diagnostic_publisher):
        raise NotImplementedError()

    def getHoverInfo(self, uri, line, char):
        raise NotImplementedError()

    def getCompletions(self, textDocument, position):
        raise NotImplementedError()

#----------------------------------------------------------------------
#  Standard defines and object types
#

class CompletionKind(object):
    Text = 1
    Method = 2
    Function = 3
    Constructor = 4
    Field = 5
    Variable = 6
    Class = 7
    Interface = 8
    Module = 9
    Property = 10
    Unit = 11
    Value = 12
    Enum = 13
    Keyword = 14
    Snippet = 15
    Color = 16
    File = 17
    Reference = 18


class DiagnosticSeverity(object):
    Error = 1
    Warning = 2
    Information = 3
    Hint = 4

class TextDocumentSyncKind(object):
    None_ = 0,
    Full = 1
    Incremental = 2


@attr.s
class HoverInfo(object):
    language = attr.ib()
    value = attr.ib()


@attr.s
class Completion(object):
    label = attr.ib()
    kind = attr.ib()
    detail = attr.ib()
    documentation = attr.ib()


@attr.s
class Position(object):
    line = attr.ib()
    character = attr.ib()

@attr.s
class Range(object):
    start = attr.ib(validator=instance_of(Position))
    end = attr.ib(validator=instance_of(Position))


@attr.s
class Diagnostic(object):
    range = attr.ib(validator=instance_of(Range))
    severity = attr.ib()
    source = attr.ib()
    message = attr.ib()
