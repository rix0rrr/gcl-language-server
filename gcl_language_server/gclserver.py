import logging
from os import path
import urlparse
import sys

import gcl
from gcl import ast_util
from gcl import runtime
from gcl import framework

logger = logging.getLogger(__name__)


class GCLServer(object):
  """Coordinates in this code are in base-1."""
  def __init__(self, search_directories):
    self.documents = {}
    self.loader = InMemoryLoader(self, InMemoryFiles(self, search_directories))

  def contains(self, full_path):
    logger.info('Contains? %s in %r', full_path, self.documents.keys())
    return 'file://' + full_path in self.documents

  def get(self, full_path):
    return self.documents['file://' + full_path]

  def get_memory_file(self, full_path):
    logger.info('Loaded %s from memory', full_path)
    return self.get(full_path).text

  def update_document(self, uri, text, parse_error_notifier):
    assert isinstance(uri, basestring)
    assert isinstance(text, basestring)
    doc = self.documents[uri] = Document(uri, text, self.loader)
    try:
      doc.normal_parse()
      parse_error_notifier(uri, 1, 1, [])
    except gcl.ParseError as e:
      parse_error_notifier(uri, e.sourcelocation.lineno, e.sourcelocation.col, e.error_message.split('\n'))
    except Exception as e:
      import traceback
      traceback.print_exc()

  def completions(self, uri, line, col):
    doc = self.documents[uri]
    return doc.completions(line, col)

  def hover_info(self, uri, line, col):
    doc = self.documents[uri]
    return doc.hover_info(line, col)


class Document(object):
  def __init__(self, uri, text, loader):
    self.url = urlparse.urlparse(uri)
    self.text = text
    self.loader = loader
    self._normal_parse = None
    self._error_parse = None

  def normal_parse(self):
    if self._normal_parse is None:
      self._normal_parse = gcl.reads(self.text, filename=self.url.path, loader=self.loader)
    return self._normal_parse

  def error_parse(self):
    try:
      if self._error_parse is None:
        self._error_parse = gcl.reads(self.text, filename=self.url.path, allow_errors=True, loader=self.loader)
      return self._error_parse
    except gcl.ParseError as e:
      import traceback
      traceback.print_exc(file=sys.stderr)
      sys.stderr.write('Unexpected parse error, please raise a bug report\n')
      raise

  def completions(self, line, col):
    with framework.DisableCaching():
      return ast_util.find_completions_at_cursor(self.error_parse(), self.url.path, line, col)

  def hover_info(self, line, col):
    with framework.DisableCaching():
      return ast_util.find_value_at_cursor(self.error_parse(), self.url.path, line, col)


class InMemoryFiles(runtime.OnDiskFiles):
  def __init__(self, gclserver, search_path):
    super(InMemoryFiles, self).__init__(search_path)
    self.gclserver = gclserver

  def exists(self, full_path):
    logger.info('Existing')
    return self.gclserver.contains(full_path) or path.isfile(full_path)

  def load(self, full_path):
    logger.info('Loading')
    if self.gclserver.contains(full_path):
      return self.gclserver.get_memory_file(full_path)

    with open(full_path, 'r') as f:
      return f.read()


class InMemoryLoader(object):
  def __init__(self, gclserver, fs):
    self.gclserver = gclserver
    self.fs = fs

  def __call__(self, current_file, rel_path, env=None):
    nice_path, full_path = self.fs.resolve(current_file, rel_path)

    if path.splitext(nice_path)[1] == '.json':
      return json.loads(self.fs.load(full_path))

    if self.gclserver.contains(full_path):
      return framework.eval(self.gclserver.get(full_path).error_parse(), env=env)

    return gcl.loads(self.fs.load(full_path), filename=nice_path, loader=self, env=env)
