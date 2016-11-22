#!/usr/bin/env python2.7
from __future__ import absolute_import

import argparse
import json
import logging
import sys
import pprint
import os

try:
  from mimetools import Message
except ImportError:
  from email.message import Message

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from jsonrpc import JSONRPCResponseManager, dispatcher
from jsonrpc import jsonrpc2

from . import gclserver


TextDocumentSyncKind_Full = 1

logger = logging.getLogger('gcls')


search_directories = []
if 'GCLPATH' in os.environ:
    search_directories = os.environ['GCLPATH'].split(':')

gcl_server = gclserver.GCLServer(search_directories)


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
                    "definitionProvider": False  # FIXME
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
    value = gcl_server.hover_info(textDocument['uri'], position['line'] + 1, position['character'] + 1)
    if value:
        return {'contents': {'language': 'gcl', 'value': value}}
    return {}
    # contents: string =>  markdown
    # range { start { line, character }, end { line, character }}


@named_add_method('textDocument/definition')
def definition(textDocument, position):
    uri = textDocument['uri']
    line, character = position['line'], position['character']
    return {'uri': uri,
            'range': {'line': 0, 'character': 0}}


@named_add_method('textDocument/completion')
def completion(textDocument, position):
    completions = gcl_server.completions(textDocument['uri'], position['line'] + 1, position['character'] + 1)
    return {'isIncomplete': False,
            'items': [mkCompletion(c) for c in completions.values()]}


def mkCompletion(c):
    return {'label': c.name,
            'kind': 5 if c.builtin else 1,
            'detail': 'built-in' if c.builtin else '',
            'documentation': c.doc}

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
    sys.stdout.write('Content-Length: %d\r\n' % len(output))
    sys.stdout.write('\r\n')
    sys.stdout.write(output)
    sys.stdout.flush()

running = True

def main():
    logging.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s',
            stream=sys.stderr,
            level=logging.ERROR)

    logger.info('Current directory is %s', os.getcwd())
    try:
        unbuffered_stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)

        headers = []
        while running:
            line = unbuffered_stdin.readline()
            if not line:
                break
            line = line.strip()
            logger.debug('< %s' % line)
            if not line:
                logger.debug('Headers: %r' % headers)
                headers = parse_headers(headers)
                if 'content-length' in headers:
                    length = int(headers['content-length'])
                    logger.debug('Waiting for %d bytes' % length)
                    body = unbuffered_stdin.read(length)
                    logger.debug('Read body: %s' % body)
                    output = handle(body)
                    if output:
                        write_output(output)
                headers = []
            else:
                headers.append(line)
    except Exception as e:
        logger.exception('Uncaught error')


if __name__ == '__main__':
    main()
