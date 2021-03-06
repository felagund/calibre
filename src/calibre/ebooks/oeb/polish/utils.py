#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2013, Kovid Goyal <kovid at kovidgoyal.net>'

import re, os
from bisect import bisect

from calibre import guess_type as _guess_type

def guess_type(x):
    return _guess_type(x)[0] or 'application/octet-stream'

def setup_cssutils_serialization(tab_width=2):
    import cssutils
    prefs = cssutils.ser.prefs
    prefs.indent = tab_width * ' '
    prefs.indentClosingBrace = False
    prefs.omitLastSemicolon = False

def actual_case_for_name(container, name):
    from calibre.utils.filenames import samefile
    if not container.exists(name):
        raise ValueError('Cannot get actual case for %s as it does not exist' % name)
    parts = name.split('/')
    base = ''
    ans = []
    for i, x in enumerate(parts):
        base = '/'.join(ans + [x])
        path = container.name_to_abspath(base)
        pdir = os.path.dirname(path)
        candidates = {os.path.join(pdir, q) for q in os.listdir(pdir)}
        if x in candidates:
            correctx = x
        else:
            for q in candidates:
                if samefile(q, path):
                    correctx = os.path.basename(q)
                    break
            else:
                raise RuntimeError('Something bad happened')
        ans.append(correctx)
    return '/'.join(ans)

def corrected_case_for_name(container, name):
    parts = name.split('/')
    ans = []
    base = ''
    for i, x in enumerate(parts):
        base = '/'.join(ans + [x])
        if container.exists(base):
            correctx = x
        else:
            try:
                candidates = {q for q in os.listdir(os.path.dirname(container.name_to_abspath(base)))}
            except EnvironmentError:
                return None  # one of the non-terminal components of name is a file instead of a directory
            for q in candidates:
                if q.lower() == x.lower():
                    correctx = q
                    break
            else:
                return None
        ans.append(correctx)
    return '/'.join(ans)

class PositionFinder(object):

    def __init__(self, raw):
        pat = br'\n' if isinstance(raw, bytes) else r'\n'
        self.new_lines = tuple(m.start() + 1 for m in re.finditer(pat, raw))

    def __call__(self, pos):
        lnum = bisect(self.new_lines, pos)
        try:
            offset = abs(pos - self.new_lines[lnum - 1])
        except IndexError:
            offset = pos
        return (lnum + 1, offset)

class CommentFinder(object):

    def __init__(self, raw, pat=r'(?s)/\*.*?\*/'):
        self.starts, self.ends = [], []
        for m in re.finditer(pat, raw):
            start, end = m.span()
            self.starts.append(start), self.ends.append(end)

    def __call__(self, offset):
        if not self.starts:
            return False
        q = bisect(self.starts, offset) - 1
        return q >= 0 and self.starts[q] <= offset <= self.ends[q]

def link_stylesheets(container, names, sheets, remove=False, mtype='text/css'):
    from calibre.ebooks.oeb.base import XPath, XHTML
    changed_names = set()
    snames = set(sheets)
    lp = XPath('//h:link[@href]')
    hp = XPath('//h:head')
    for name in names:
        root = container.parsed(name)
        if remove:
            for link in lp(root):
                if (link.get('type', mtype) or mtype) == mtype:
                    container.remove_from_xml(link)
                    changed_names.add(name)
                    container.dirty(name)
        existing = {container.href_to_name(l.get('href'), name) for l in lp(root) if (l.get('type', mtype) or mtype) == mtype}
        extra = snames - existing
        if extra:
            changed_names.add(name)
            try:
                parent = hp(root)[0]
            except (TypeError, IndexError):
                parent = root.makeelement(XHTML('head'))
                container.insert_into_xml(root, parent, index=0)
            for sheet in sheets:
                if sheet in extra:
                    container.insert_into_xml(
                        parent, parent.makeelement(XHTML('link'), rel='stylesheet', type=mtype,
                                                   href=container.name_to_href(sheet, name)))
            container.dirty(name)

    return changed_names

def lead_text(top_elem, num_words=10):
    ''' Return the leading text contained in top_elem (including descendants)
    upto a maximum of num_words words. More efficient than using
    etree.tostring(method='text') as it does not have to serialize the entire
    sub-tree rooted at top_elem.'''
    pat = re.compile(r'\s+', flags=re.UNICODE)
    words = []

    def get_text(x, attr='text'):
        ans = getattr(x, attr)
        if ans:
            words.extend(filter(None, pat.split(ans)))

    stack = [(top_elem, 'text')]
    while stack and len(words) < num_words:
        elem, attr = stack.pop()
        get_text(elem, attr)
        if attr == 'text':
            if elem is not top_elem:
                stack.append((elem, 'tail'))
            stack.extend(reversed(list((c, 'text') for c in elem.iterchildren('*'))))
    return ' '.join(words[:num_words])

