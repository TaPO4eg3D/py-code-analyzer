from tree_sitter import Language, Parser

from tree.walker import TreeWalker

Language.build_library('build/my-languages.so', ('vendor/tree-sitter-python',))

PY_LANGUAGE = Language('build/my-languages.so', 'python')
PROJECT_ROOT = '/home/tapo4eg3d/testproject'
FILE_PATH = f'{PROJECT_ROOT}/test.py'

parser = Parser()
parser.set_language(PY_LANGUAGE)

with open(FILE_PATH, 'rb') as f:
    source_code = f.read()

tree = parser.parse(source_code)
cur = tree.walk()

walker = TreeWalker(cur)
m = walker.parse_file(FILE_PATH)

print('Done!')
