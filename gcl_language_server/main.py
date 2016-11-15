#!/usr/bin/env python2.7
import json
import logging
import sys
import pprint
import os
from mimetools import Message
from StringIO import StringIO

from jsonrpc import JSONRPCResponseManager, dispatcher
from jsonrpc import jsonrpc2

import gclserver


TextDocumentSyncKind_Full = 1

logger = logging.getLogger('gcls')

def log(text):
    logger.info(text)


gcl_server = gclserver.GCLServer()


def named_add_method(name):
    def handler(fn):
        dispatcher.add_method(fn, name)
    return handler


def notify_parse_error(uri, line, col, messages):
    start = {'line': line - 1, 'character': col - 1 }
    end   = {'line': line - 1, 'character': col  }

    request = jsonrpc2.JSONRPC20Request(method='textDocument/publishDiagnostics', is_notification=True, params={
        'uri': uri,
        'diagnostics': [
            {
                'range': { 'start': start, 'end': end },
                'severity': 1,  # Error
                'source': 'gcls',
                'message': message
            } for message in messages
        ]
    })
    write_output(request.json)


@dispatcher.add_method
def initialize(processId, rootPath, capabilities, trace):
    return {"capabilities": {
                "textDocumentSync": TextDocumentSyncKind_Full,
                    "hoverProvider": True,
                    "completionProvider": {
                        "resolveProvider": False,
                        "triggerCharacters": ['.']
                    },
                    "definitionProvider": True
                }
            }


@dispatcher.add_method
def shutdown():
    global running
    running = False


@named_add_method('$/setTraceNotification')
def setTraceNotification(value):
    pass


@named_add_method('textDocument/didOpen')
def didOpen(textDocument):
    gcl_server.update_document(textDocument['uri'], textDocument['text'], notify_parse_error)


@named_add_method('textDocument/didChange')
def didChange(textDocument, contentChanges):
    gcl_server.update_document(textDocument['uri'], contentChanges[0]['text'], notify_parse_error)


@named_add_method('textDocument/hover')
def hover(textDocument, position):
    uri = textDocument['uri']
    line, character = position['line'], position['character']
    return {'contents': {'language': 'gcl', 'value': 'haha'}}
    # contents: string =>  markdown
    # range { start { line, character }, end { line, character }}


@named_add_method('textDocument/definition')
def definition(textDocument, position):
    uri = textDocument['uri']
    line, character = position['line'], position['character']
    return {'uri': uri,
            'range': {'line': 0, 'character': 0}}


@named_add_method('textDocument/completion')
def definition(textDocument, position):
    uri = textDocument['uri']
    line, character = position['line'], position['character']
    return {'isIncomplete': False,
            'items': [
                { 'label': 'hoop le boop' },
                { 'label': 'hoogey woop' },
                ]}


def parse_headers(lines):
    ret = {}
    for line in lines:
        key, value = line.split(':', 1)
        ret[key.lower().strip()] = value.strip()
    return ret


def handle(payload):
    response = JSONRPCResponseManager.handle(payload, dispatcher)
    return response.json if response else None


def write_output(output):
    log('Output was %s' % output)
    sys.stdout.write('Content-Length: %d\r\n' % len(output))
    sys.stdout.write('\r\n')
    sys.stdout.write(output)
    sys.stdout.flush()

running = True

def main():
    logging.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s',
            filename='/Users/rix0rrr/gcls.log',
            level=logging.DEBUG)
    log('Current directory is %s' % os.getcwd())
    try:
        unbuffered_stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)

        headers = []
        while running:
            line = unbuffered_stdin.readline()
            if not line:
                break
            line = line.strip()
            log('< %s' % line)
            if not line:
                log('Headers: %r' % headers)
                headers = parse_headers(headers)
                if 'content-length' in headers:
                    length = int(headers['content-length'])
                    log('Waiting for %d bytes' % length)
                    body = unbuffered_stdin.read(length)
                    log('Read body: %s' % body)
                    output = handle(body)
                    if output:
                        write_output(output)
                headers = []
            else:
                headers.append(line)
    except Exception as e:
        import traceback
        log(traceback.format_exc(e))
        traceback.print_exc(e)

if __name__ == '__main__':
    main()