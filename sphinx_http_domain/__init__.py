# -*- coding: utf-8 -*-
"""
    sphinx.domains.http
    ~~~~~~~~~~~~~~~~~~~

    The HTTP domain.

    :copyright: Copyright 2011, David Zentgraf.
    :license: BSD, see LICENSE for details
"""

from itertools import izip

import subprocess
import json

from docutils.nodes import literal, Text

from sphinx.locale import l_
from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.util.nodes import make_refnode
from sphinx.ext import autodoc

from sphinx_http_domain.directives import HTTPMethod, HTTPResponse, HTTPExample
from sphinx_http_domain.nodes import (desc_http_method, desc_http_url,
                                      desc_http_path, desc_http_patharg,
                                      desc_http_query, desc_http_queryparam,
                                      desc_http_fragment, desc_http_response,
                                      desc_http_example)

import pprint

# TODO: extract into conf.py
API_URL = 'https://api.numenta.com/v2'
API_KEY = 'hJbcM9vWW4Te89L0eKhFdQMOTxlN9Tfb'
API_USER_ID = '0a0acdd4-d293-11e1-bb05-123138107980'

API_URL_TOKEN = '{API_URL}'
STREAM_ID_TOKEN = '{STREAM_ID}'
PROJECT_ID_TOKEN = '{PROJECT_ID}'
USER_ID_TOKEN = '{USER_ID}'
API_KEY_TOKEN = '{API_KEY}'

pp = pprint.PrettyPrinter(indent=4)

dummyProject = None
dummyDoomedProject = None
dummyStream = None
dummyDoomedStream= None

class HTTPDomain(Domain):
    """HTTP language domain."""
    name = 'http'
    label = 'HTTP'
    object_types = {
        'method': ObjType(l_('method'), 'method'),
        'response': ObjType(l_('response'), 'response'),
        'example': ObjType(l_('example'), 'example'),
    }
    directives = {
        'method': HTTPMethod,
        'response': HTTPResponse,
        'example': HTTPExample
    }
    roles = {
        'method': XRefRole(),
        'response': XRefRole(),
        'example': XRefRole()
    }
    initial_data = {
        'method': {},    # name -> docname, sig, title, method
        'response': {},  # name -> docname, sig, title
        'example': {},  # name -> docname, sig, title
    }

    def clear_doc(self, docname):
        """Remove traces of a document from self.data."""
        for typ in self.initial_data:
            for name, entry in self.data[typ].items():
                if entry[0] == docname:
                    del self.data[typ][name]

    def find_xref(self, env, typ, target):
        """Returns a self.data entry for *target*, according to *typ*."""
        try:
            return self.data[typ][target]
        except KeyError:
            return None

    def resolve_xref(self, env, fromdocname, builder,
                     typ, target, node, contnode):
        """
        Resolve the ``pending_xref`` *node* with the given *typ* and *target*.

        Returns a new reference node, to replace the xref node.

        If no resolution can be found, returns None.
        """
        match = self.find_xref(env, typ, target)
        if match:
            docname = match[0]
            sig = match[1]
            title = match[2]
            # Coerce contnode into the right nodetype
            nodetype = type(contnode)
            if issubclass(nodetype, literal):
                nodetype = self.directives[typ].nodetype
            # Override contnode with title, unless it has been manually
            # overridden in the text.
            if contnode.astext() == target:
                contnode = nodetype(title, title)
            else:
                child = contnode.children[0]
                contnode = nodetype(child, child)
            # Return the new reference node
            return make_refnode(builder, fromdocname, docname,
                                typ + '-' + target, contnode, sig)

    def get_objects(self):
        """
        Return an iterable of "object descriptions", which are tuples with
        five items:

        * `name`     -- fully qualified name
        * `dispname` -- name to display when searching/linking
        * `type`     -- object type, a key in ``self.object_types``
        * `docname`  -- the document where it is to be found
        * `anchor`   -- the anchor name for the object
        * `priority` -- how "important" the object is (determines placement
          in search results)

          - 1: default priority (placed before full-text matches)
          - 0: object is important (placed before default-priority objects)
          - 2: object is unimportant (placed after full-text matches)
          - -1: object should not show up in search at all
        """
        # Method descriptions
        for typ in self.initial_data:
            for name, entry in self.data[typ].iteritems():
                docname = entry[0]
                yield(name, name, typ, docname, typ + '-' + name, 0)


class RestDocumenter(autodoc.MethodDocumenter):
  """
  Used to displaying REST API endpoints, which are included in the API source
  code, without displaying the directive headers, which contain the actual
  handler class names and method signatures. We want to keep those away from
  users and only document the endpoints.
  """
  objtype = "rest"
  content_indent = ""

  def add_directive_header(self, sig):
    # don't print the header
    pass



def convert_curl_string_to_curl_command(curlString):
    # remove line break chars and split into components
    curl = curlString.replace('\\', '').split()
    # the problem is that this will split apart legit words in the -d value,
    # so we look for that block and squish them back together
    startIndex = None
    for i, subCmd in enumerate(curl):
      if subCmd == '-d':
        startIndex = i
        break

    endIndex = len(curl) - 1

    subStrings = []
    if startIndex:
      for i in reversed(range(startIndex+1, endIndex+1)):
        subStrings.append(curl.pop(i))
      subStrings.reverse()
      curl.insert(startIndex + 1, ' '.join(subStrings))

    return curl


def extract_curl_request(doclines):
    startIndex = None
    endIndex = None
    for i, line in enumerate(doclines):
        # replace the {API_URL} token with the real API URL
        doclines[i] = line.replace(API_URL_TOKEN, API_URL)
        if 'Curl request' in line:
            startIndex = i
        if 'Curl response' in line:
            endIndex = i
            break

    if startIndex is None:
        return None

    return convert_curl_string_to_curl_command(' '.join(doclines[startIndex+1:endIndex]))



def make_command_substitutions(cmd):
    global dummyProject, dummyDoomedStream
    projectToUse = dummyProject
    streamToUse = dummyStream
    if 'DELETE' in ' '.join(cmd):
        projectToUse = dummyDoomedProject
        streamToUse = dummyDoomedStream

#    if dummyProject:
#      print '\n for query: "' + ' '.join(cmd)
#      print '\ndummyProject: ' + dummyProject
#      print 'dummyDoomedProject: ' + dummyDoomedProject
#      print 'USING: ' + projectToUse + '\n'

    for i, item in enumerate(cmd):
        # replace API_KEY
        newItem = item.replace(API_KEY_TOKEN, API_KEY)
        # replace userId
        newItem = newItem.replace(USER_ID_TOKEN, API_USER_ID)
        # replace projectId
        if PROJECT_ID_TOKEN in newItem:
          newItem = newItem.replace(PROJECT_ID_TOKEN, projectToUse)
        # replace streamId
        if STREAM_ID_TOKEN in newItem:
          newItem = newItem.replace(STREAM_ID_TOKEN, streamToUse)

        # put new item in place of the old one
        cmd[i] = newItem



def escape_double_quotes_in_curl_data(curlRequest):
    for i, v in enumerate(curlRequest):
      if v == '-d':
        curlRequest[i+1] = curlRequest[i+1][1:-1]
        break



def execute_curl_request(request, headers=True, debug=False):
    if debug:
      print '\nexecuting curl request:'
      pp.pprint(request)
    make_command_substitutions(request)
    escape_double_quotes_in_curl_data(request)
    if debug:
      print 'Processed request: '
      pp.pprint(request)
    result = None
    body = None
    # add the -i option to print the response headers as well
    if headers:
      request.append('-i')
    print '\n' + ' '.join(request)
    raw = subprocess.Popen(request, stdout=subprocess.PIPE).communicate()[0]
    raw = raw.split('\r\n\r\n')

    if debug:
      pp.pprint(raw)

    if headers:
      result = {
        'headers': raw[0],
        'body': json.loads(raw[1])
      }
      body = result['body']
    else:
      result = json.loads(raw[0])
      body = result

    if 'errors' in body:
      raise Exception("Error executing curl during API doc build.\n\t" +
                      "Curl call details are: " + ' '.join(request) + '\n\t' +
                      "Errors from API: " + str(body['errors']))


    return result



def integrate_api_response(doclines, headers, respBody):
    newResponse = json.dumps(respBody, ensure_ascii=False, indent=2).split('\n')
    # add the header lines before the code
    doclines.append('')
    doclines.append('  Curl response:')
    doclines.append('')
    doclines.append('  .. code-block:: http')
    doclines.append('')
    for hdr in headers.split('\n'):
      doclines.append('    ' + hdr)
    doclines.append('')
    doclines.append('  .. code-block:: json')
    doclines.append('')

    # add 4 spaces to each response line to properly indent it within code-block
    for i, line in enumerate(newResponse):
      newResponse[i] = '    ' + line
    # add response to end of doclines
    doclines.extend(newResponse)



def replace_curl_examples(app, what, name, obj, options, lines):
    if not app.config.auto_curl:
        return
    if what == 'rest':
        curl_request = extract_curl_request(lines)
        if curl_request is not None:
            try:
              response = execute_curl_request(curl_request, debug=True)
            except Exception as e:
              raise Exception("Error executing curl during API doc build.\n\t" +
                              "Curl call details are: " + ' '.join(curl_request) + '\n\t' +
                              "Errors from API: " + str(e))
            integrate_api_response(lines, response['headers'], response['body'])



def prepopulate_api_objects(app):
  """
  Creates objects in the API that the doc build will use when making example
  calls to the API.
  """
  global dummyProject,\
  dummyDoomedProject,\
  dummyStream,\
  dummyDoomedStream

  if app.config.auto_curl:

    # dummy project for retrieval
    curl = 'curl ' + API_URL + '/users/' + API_USER_ID + '/projects -u '\
           + API_KEY + ': -X POST -d \'{"project":{"name":"My API Doc Project"}}\''
    curlCommand = convert_curl_string_to_curl_command(curl)
    response = execute_curl_request(curlCommand, headers=False, debug=False)
    dummyProject = response['project']['id']

    # dummy project for deletion
    curl = 'curl ' + API_URL + '/users/' + API_USER_ID + '/projects -u '\
           + API_KEY + ': -X POST -d \'{"project":{"name":"DUMMY"}}\''
    curlCommand = convert_curl_string_to_curl_command(curl)
    response = execute_curl_request(curlCommand, headers=False, debug=False)
    dummyDoomedProject = response['project']['id']

    # dummy stream for retrieval
    curl = 'curl ' + API_URL + '/users/' + API_USER_ID + '/streams -u '\
           + API_KEY + ': -X POST -d \'{"stream":{"name":"My Stream","dataSources":[{"name":"My Data Source","fields":[{"name":"My Field","dataFormat":{"dataType":"SCALAR"}}]}]}}\''
    curlCommand = convert_curl_string_to_curl_command(curl)
    response = execute_curl_request(curlCommand, headers=False, debug=False)
    dummyStream = response['stream']['id']
    # add data to this stream
    curl = 'curl ' + API_URL + '/streams/' + dummyStream + '/data -u '\
           + API_KEY + ': -d \'{ "input":[ [ 3.14 ], [ 42 ] ]}\''
    curlCommand = convert_curl_string_to_curl_command(curl)
    execute_curl_request(curlCommand, headers=False, debug=False)

    # dummy stream for deletion
    curl = 'curl ' + API_URL + '/users/' + API_USER_ID + '/streams -u '\
           + API_KEY + ': -X POST -d \'{"stream":{"name":"My Stream","dataSources":[{"name":"My Data Source","fields":[{"name":"My Field","dataFormat":{"dataType":"SCALAR"}}]}]}}\''
    curlCommand = convert_curl_string_to_curl_command(curl)
    response = execute_curl_request(curlCommand, headers=False, debug=False)
    dummyDoomedStream = response['stream']['id']



def teardown(app, what):
    print '\n\nTODO: Remove all projects, models, streams, and swarms for apidocs@numenta.com.\n\n'



def setup(app):
    app.add_autodocumenter(RestDocumenter)
    app.add_domain(HTTPDomain)
    desc_http_method.contribute_to_app(app)
    desc_http_url.contribute_to_app(app)
    desc_http_path.contribute_to_app(app)
    desc_http_patharg.contribute_to_app(app)
    desc_http_query.contribute_to_app(app)
    desc_http_queryparam.contribute_to_app(app)
    desc_http_fragment.contribute_to_app(app)
    desc_http_response.contribute_to_app(app)
    desc_http_example.contribute_to_app(app)
    app.add_config_value('auto_curl', False, False)
    app.connect('builder-inited', prepopulate_api_objects)
    app.connect('autodoc-process-docstring', replace_curl_examples)
    app.connect('build-finished', teardown)
