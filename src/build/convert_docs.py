#!/usr/bin/python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Tool to convert Markdown files to HTML.
#
# For usage run 'python src/build/convert-docs.py --help
#

import argparse
import cgi
import datetime
import markdown
import os
import re
import string
import sys


_HTML_TEMPLATE = string.Template("""
<!DOCTYPE html>
<html>
<head>
<title>$TITLE</title>
<style type="text/css">
/* Sorted in alphabetical order. */
body {
  font-family: sans-serif;
  line-height: 1.6;
  margin: 20px auto;
  width: 75%;
}
div#breadcrumb {
  color: #666;
  font-weight: bold;
  float: left;
}
div#breadcrumb a {
  color: #666;
  text-decoration: none;
}
div#breadcrumb a:hover {
  text-decoration: underline;
}
div#generated-at {
  color: #888;
  font-style: italic;
  text-align: right;
}
div#header {
  /* To clear floats. */
  overflow: auto;
}
form#search {
  float: right;
}
hr {
  color: #ccc;
  border-style: solid;
  border-width: 1px 0 0 0;
}
pre {
  background: #eee;
  border-radius: 4px;
  padding: 12px;
}
</style>
</head>
<body>
<div id="header">
<div id="breadcrumb">
<a href="index.html">Documentation</a> $BREADCRUMB_LEAF
</div>
<form id="search" action="/grep" method="get">
<input type=text name="q" size="15" value=""
><input value="Search" type="submit">
</form>
</div>
<h1>$TITLE</h1>
$CONTENT
<hr>
<div id="generated-at">
Generated at:
<script type=text/javascript>
   var date = new Date("$DATE");
   // Cannot use document.lastModified as it always returns the current
   // date and time on App Engine.
   document.write(date.toLocaleString());
</script>
</div>
</body>
</html>
""".lstrip())


class DocumentValidationError(Exception):
  """Raised when there is a problem with a document file."""


def _read(input_file_name):
  """Read a Markdown file and return its title and content."""

  with open(input_file_name, 'r') as f:
    try:
      title, second_line, text = f.read().split('\n', 2)
    except ValueError:
      raise DocumentValidationError(
          '%s: A document should contain at least 3 lines.' %
          input_file_name)

  # The first line should be the document title.
  if not title:
    raise DocumentValidationError(
        '%s: A non-blank title line as the first line is required.'
        % input_file_name)

  # The next line should be the first-level header marker.
  if not re.match(r'=+$', second_line):
    raise DocumentValidationError(
        '%s: The second line should be one or more = characters as the '
        'first line should be a top level header giving a title to the '
        'document.' % input_file_name)

  return title, text


def _generate_html(breadcrumb_leaf, content, title):
  """Generate HTML per the given parameters and _HTML_TEMPLATE."""

  template_dict = {}
  template_dict['BREADCRUMB_LEAF'] = breadcrumb_leaf
  template_dict['CONTENT'] = content
  template_dict['DATE'] = datetime.datetime.utcnow().isoformat()
  template_dict['TITLE'] = cgi.escape(title)
  return _HTML_TEMPLATE.substitute(template_dict)


def _convert(input_file_name):
  """Convert a Markdown file into HTML format.

  Return the document title and content.
  """

  title, text = _read(input_file_name)

  # Use 'toc' (Table of Contents) extension.
  text = '[TOC]\n' + text
  content = markdown.markdown(text, extensions=['toc'])

  breadcrumb_leaf = '&raquo; ' + cgi.escape(title)
  output = _generate_html(breadcrumb_leaf=breadcrumb_leaf,
                          content=content,
                          title=title)
  return title, output


def _generate_index(document_map):
  """Generate index.html content from the given document map."""

  toc = ['<ul>']
  for title, file_name in sorted(document_map):
    toc.append('<li><a href="%s">%s</a></li>' %
               (cgi.escape(file_name, quote=True),
                cgi.escape(title)))
  toc.append('</ul>')
  content = '\n'.join(toc)

  title = 'App Runtime for Chrome Documentation'
  # Do not show the breadcrumb leaf as this is the top level document.
  breadcrumb_leaf = ''
  output = _generate_html(breadcrumb_leaf=breadcrumb_leaf,
                          content=content,
                          title=title)
  return output


def validate_docs(file_names):
  """Validate the given document files.

  Return true if all document files are valid.
  """

  result = True
  for file_name in file_names:
    if not file_name.endswith('.md'):
      print '%s: A document should have ".md" suffix' % file_name
      result = False
    # Check if this document can be converted cleanly (i.e. formatted
    # correctly).
    try:
      title, html = _convert(file_name)
    except DocumentValidationError as e:
      print e
      result = False
  return result


def _convert_docs(input_file_names, output_dir):
  if not os.path.exists(output_dir):
    os.makedirs(output_dir)

  document_map = []  # Map of document title to base HTML file name.
  for input_file_name in input_file_names:
    name = os.path.splitext(os.path.basename(input_file_name))[0]
    output_file_name = os.path.join(output_dir, name + '.html')
    try:
      title, html = _convert(input_file_name)
    except DocumentValidationError as e:
      print e
      sys.exit(1)
    document_map.append((title, os.path.basename(output_file_name)))
    with open(output_file_name, 'w') as f:
      f.write(html)

  html = _generate_index(document_map)
  with open(os.path.join(output_dir, 'index.html'), 'w') as f:
    f.write(html)


def main():
  description = 'Tool to convert Markdown files to HTML.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('--output-dir',
                      help='Specify the directory to store test ouput files.')
  parser.add_argument('--validate',
                      help='Do not create any files; Just validate them.',
                      action='store_true')
  parser.add_argument('input_file_names',
                      help='Specify the input file names in Markdown format.',
                      metavar='FILE',
                      nargs='*')
  args = parser.parse_args()

  if args.validate:
    if validate_docs(args.input_file_names):
      return 0
    else:
      return -1

  if not args.output_dir:
    parser.error('--output-dir is required')
    return -1

  _convert_docs(args.input_file_names, args.output_dir)


if __name__ == '__main__':
  sys.exit(main())
