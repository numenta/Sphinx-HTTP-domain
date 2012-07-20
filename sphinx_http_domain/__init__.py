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

API_KEY = 'hJbcM9vWW4Te89L0eKhFdQMOTxlN9Tfb'
apiUserId = '0a0acdd4-d293-11e1-bb05-123138107980'
projectId = '355b6b5c-7a66-4857-ae1f-85e196e7ebbb'

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



def extract_curl_request(doclines):
    startIndex = None
    endIndex = None
    for i, line in enumerate(doclines):
        if 'Curl request' in line:
            startIndex = i
        if 'Curl response' in line:
            endIndex = i
            break
    curl = ' '.join(doclines[startIndex+1:endIndex])
    # remove line break chars and split into components
    curl = curl.replace('\\', '').split()
    # the problem is that this will split apart legit words in the -d value,
    # so we look for that block and squish them back together
    startIndex = None
    for i, subcmd in enumerate(curl):
        if subcmd == '-d':
            startIndex = i
            break

    endIndex = len(curl) - 1

    substrings = []
    if startIndex:
        for i in reversed(range(startIndex+1, endIndex+1)):
            substrings.append(curl.pop(i))
        substrings.reverse()
        curl.insert(startIndex + 1, ' '.join(substrings))

    return curl



def make_command_substitutions(cmd):
    for i, item in enumerate(cmd):
        # replace API_KEY
        newItem = item.replace('{API_KEY}', API_KEY)
        # replace userId
        newItem = newItem.replace('{USER_ID}', apiUserId)
        # replace projectId
        newItem = newItem.replace('{PROJECT_ID}', projectId)
        # replace modelId

        # put new item in place of the old one
        cmd[i] = newItem



def escape_double_quotes_in_curl_data(curlRequest):
    for i, v in enumerate(curlRequest):
      if v == '-d':
        curlRequest[i+1] = curlRequest[i+1][1:-1]
        break



def execute_curl_request(request):
    make_command_substitutions(request)
    escape_double_quotes_in_curl_data(request)
    response = subprocess.Popen(request, stdout=subprocess.PIPE).communicate()[0]
    return response



def process_api_response(doclines, response):
    jsonObj = json.loads(response)

    if 'errors' in jsonObj:
      raise Exception(jsonObj['errors'])

    newResponse = json.dumps(jsonObj, ensure_ascii=False, indent=2).split('\n')

    # add the header lines before the code
    doclines.append('')
    doclines.append('  Curl response:')
    doclines.append('')
    doclines.append('  .. code-block:: json')
    doclines.append('')
    # add 4 spaces to each response line to properly indent it within code-block
    for i, line in enumerate(newResponse):
      newResponse[i] = '    ' + line
    # add response to end of doclines
    doclines.extend(newResponse)



def replace_curl_examples(app, what, name, obj, options, lines):
    if what == 'rest':
        curl_request = extract_curl_request(lines)
        print "CURL REQUEST: " + ' '.join(curl_request)
        response = execute_curl_request(curl_request)
        try:
          process_api_response(lines, response)
        except Exception as e:
          raise Exception("Error executing curl during API doc build.\n\t" +
                          "Curl call details are: " + ' '.join(curl_request) + '\n\t' +
                          "Errors from API: " + str(e.message))


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
#    app.connect('doctree-resolved', replace_curl_examples)
    app.connect('autodoc-process-docstring', replace_curl_examples)
