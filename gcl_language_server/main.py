#!/usr/bin/env python2.7
from __future__ import absolute_import

import argparse
import json
import logging
import sys
import os

from . import gclserver
from . import lps


TextDocumentSyncKind_Full = 1

logger = logging.getLogger('gcls')


def main():
    parser = argparse.ArgumentParser(description='GCL Language Protocol Server')
    parser.add_argument('--verbose', '-v', action='store_true', default=False, help='Show debug output')
    parser.add_argument('--file', '-f', help='Read input from file instead of stdin (testing only)')
    parser.add_argument('--include', '-i', action='append', default=[], help='GCL search directories (in addition to what\'s in GCLPATH)')

    args = parser.parse_args()

    loglevel = logging.ERROR if not args.verbose else logging.DEBUG

    logging.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s',
            stream=sys.stderr,
            level=loglevel)
    try:
        logger.info('Current directory is %s', os.getcwd())

        search_directories = args.include
        if 'GCLPATH' in os.environ:
            search_directories.extend(os.environ['GCLPATH'].split(':'))

        logger.info('Search path is %r', search_directories)

        gcl_server = gclserver.GCLServer(search_directories)
        handler = GCLProtocolHandler(gcl_server)

        if args.file:
            input_stream = open(args.file, 'rb')
        else:
            unbuffered_stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)
            input_stream = unbuffered_stdin

        proto_server = lps.LanguageProtocolServer(handler, input_stream, sys.stdout)
        proto_server.run()
    except Exception as e:
        logger.exception('Uncaught error')
        sys.exit(1)


class GCLProtocolHandler(lps.LanguageProtocolHandler):
    """Bridge between the Language Protocol and the GCL Server."""
    def __init__(self, gcl_server):
        self.gcl_server = gcl_server

    def updateDocument(self, uri, text, diagnostic_publisher):
        def report_parse_error(uri, line, col, messages):
            # Report a multi-line error message, all at the given location
            rng = lps.Range(
                lps.Position(line - 1, col - 1),
                lps.Position(line - 1, col + 2))  # Length is always 3
            diagnostic_publisher(uri, [lps.Diagnostic(
                    range=rng,
                    severity=lps.DiagnosticSeverity.Error,
                    source='gcls',
                    message=m) for m in messages])

        return self.gcl_server.update_document(uri, text, report_parse_error)

    def getHoverInfo(self, uri, line, char):
        value = self.gcl_server.hover_info(uri, line, char)
        return lps.HoverInfo(language='gcl', value=value or '')

    def getCompletions(self, textDocument, position):
        completion_map = self.gcl_server.completions(textDocument['uri'], position['line'] + 1, position['character'] + 1)
        return map(mkCompletion, completion_map.values())


def mkCompletion(c):
    return lps.Completion(label=c.name,
            kind=lps.CompletionKind.Field if c.builtin else lps.CompletionKind.Text,
            detail='built-in' if c.builtin else '',
            documentation=c.doc)


if __name__ == '__main__':
    main()
