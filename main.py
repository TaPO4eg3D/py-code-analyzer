import typing

from enum import Enum, auto

from dataclasses import dataclass, field
from collections import namedtuple

from tree_sitter import Language, Parser, TreeCursor, Node

from consts import BUILTINS

Language.build_library('build/my-languages.so', ('vendor/tree-sitter-python',))

PY_LANGUAGE = Language('build/my-languages.so', 'python')
PROJECT_ROOT = '/home/tapo4eg3d/testproject'
FILE_PATH = f'{PROJECT_ROOT}/test.py'

parser = Parser()
parser.set_language(PY_LANGUAGE)

with open(FILE_PATH, 'rb') as f:
    source_code = f.read()



@dataclass
class Variable:
    name: str


class BlockType(str, Enum):
    Module = 'Module'
    Class = 'Class'
    Function = 'Function'
    Undefined = 'Object'


@dataclass
class Block:
    type: BlockType
    root_node: Node | None

    # Additional info about the Block related to it's type
    data: typing.Union['ModuleBlockData', 'FunctionBlockData', 'ClassBlockData'] | None = None

    # All blocks (Module | Function | Class) has an associated name with
    # it but we can set it to None since Block cannot be Undefined
    name: str | None = None

    # Those two fields can help to detect when the User tries
    # to call a function that exits in the file but wasn't declared yet
    # so the interpreter won't be able to see it
    starts_at: int | None = None  # Line number in the file when the block starts
    ends_at: int | None = None  # Line number in the file when the block ends

    parent: typing.Optional['Block'] = None

    # Function calls, class intializations, etc.
    uses: list['Block'] = field(
        default_factory=list,
    )

    variable_table: dict[str, Variable] = field(
        default_factory=dict,
    )
    block_table: dict[str, 'Block'] = field(
        default_factory=dict,
    )

    def get_variable_in_scope(self, name: str) -> typing.Optional[Variable]:
        parent = self
        table = self.variable_table

        while parent is not None:
            if var := table.get(name):
                return var

            table = parent and parent.variable_table
            parent = parent.parent

        return None

    def get_block_in_scope(self, name: str) -> typing.Optional['Block']:
        parent = self.parent
        table = self.block_table

        while table is not None:
            if block := table.get(name):
                return block

            table = parent and parent.block_table
            parent = parent and parent.parent

        return None

@dataclass
class ModuleBlockData:
    # The full path to the file where the Module is declared
    declared_in: str


@dataclass
class FunctionBlockData:
    # Function signature
    signature: list[Variable] = field(
        default_factory=list,
    )


@dataclass
class ClassBlockData:
    # List of classes the Class inherits from
    inherits: list[Block] = field(
        default_factory=list,
    )


class TreeWalker:
    """
    A wrapper that parses a single file and produces a structure
    of "Blocks" that describes which Items each Block define and
    on which Items it depends
    """

    cursor: TreeCursor

    def __init__(self, cursor: TreeCursor) -> None:
        self.cursor = cursor

    def parse_file(self, file_path: str) -> Block:
        module = Block(
            type=BlockType.Module,
            root_node=self.cursor.node,
            data=ModuleBlockData(
                declared_in=file_path,
            ),
        )

        self._parse_block(module)

        return module

    @property
    def _node_type(self) -> str:
        return self.cursor.node.type

    @property
    def _node_name(self) -> str:
        return self.cursor.current_field_name()
    
    def _step_in(self, step_point: Block | Node):
        # TODO: Add TreeCursor reset binding
        if isinstance(step_point, Node):
            node = step_point
        else:
            assert step_point.root_node
            node = step_point.root_node

        self.cursor = node.walk()  # type: ignore
        self.cursor.goto_first_child()

    def _parse_block(self, block: Block, *, start_node: Node | None = None):
        self._step_in(start_node or block)

        while True:
            node_name = self.cursor.current_field_name()
            node_type = self.cursor.node.type

            match node_type:
                case 'function_definition':
                    function = self._parse_function_definition(block)
                    assert function.name
                    block.block_table[function.name] = function
                case 'class_definition':
                    klass = self._parse_class_definition(block)
                    assert klass.name
                    block.block_table[klass.name] = klass

            if not self.cursor.goto_next_sibling():
                break

        # TODO: Figure out why it happens
        if block.block_table:
            for node_name, block_item in block.block_table.items():
                # TODO: Add support for classes
                if block_item.type == BlockType.Function:
                    self._traverse_function_definition(block_item)

    def _traverse_function_definition(self, block: Block):
        self._step_in(block)

        while True:
            if self._node_name == 'body':
                break

            if not self.cursor.goto_next_sibling():
                raise RuntimeError('Unable to find the function body!')

        self._parse_block(block, start_node=self.cursor.node)

        self._step_in(block)
        self._traverse_blocked_entity(block)

    def _traverse_blocked_entity(self, block: Block):
        # TODO: Decompose to be more specific

        self.cursor.goto_first_child()

        while True:
            if self._node_name == 'body':
                break

            if not self.cursor.goto_next_sibling():
                raise RuntimeError('Unable to find the Entity body!')
        
        # Step into the body
        self.cursor.goto_first_child()

        while True:
            match self._node_type:
                case 'call':
                    self._traverse_call(block)
                case 'expression_statement':
                    self._traverse_expression(block)
                case 'if_statement' | 'for_statement' | 'while_statement':
                    # TODO: Write a separate functions for traversal
                    # since loops or conditions can call functions in their definitions
                    self._traverse_blocked_entity(block)

            if not self.cursor.goto_next_sibling():
                break

        # Step out of the body
        self.cursor.goto_parent()

        # Step out of the entity
        self.cursor.goto_parent()

    def _traverse_class_definition(self, block: Block):
        pass

    def _parse_function_definition(self, parent: Block) -> Block:
        function = Block(
            type=BlockType.Function,
            parent=parent,
            root_node=self.cursor.node,
            starts_at=self.cursor.node.start_point[0],
            ends_at=self.cursor.node.end_point[0],
        )

        self.cursor.goto_first_child()
        self.cursor.goto_next_sibling()

        if self.cursor.node.type != 'identifier':
            breakpoint()
            raise RuntimeError(
                f'Error in Function declaration on {function.starts_at}',
            )
        else:
            function.name = self.cursor.node.text

        self.cursor.goto_parent()
        
        if obj := parent.block_table.get(function.name):
            raise RuntimeError(
                f'{obj.type} "{function.name}" already decalred on pos: {obj.starts_at}'
            )

        return function

    def _parse_class_definition(self, parent: Block) -> Block:
        klass = Block(
            type=BlockType.Class,
            parent=parent,
            root_node=self.cursor.node,
            starts_at=self.cursor.node.start_point[0],
            ends_at=self.cursor.node.end_point[0],
        )

        self.cursor.goto_first_child()
        self.cursor.goto_next_sibling()

        if self.cursor.node.type != 'identifier':
            breakpoint()
            raise RuntimeError(
                f'Error in Class declaration on {klass.starts_at}',
            )
        else:
            klass.name = self.cursor.node.text

        self.cursor.goto_parent()
        
        if obj := parent.block_table.get(klass.name):
            raise RuntimeError(
                f'{obj.type} "{klass.name}" already decalred on pos: {obj.starts_at}'
            )

        return klass

    def _traverse_call(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            match (self._node_name, self._node_type):
                case ('function', ntype):
                    self._parse_function_call(ntype, block)
                case ('arguments', 'argument_list'):
                    self.cursor.goto_first_child()

                    while True:
                        if self._node_type == 'call':
                            self._traverse_call(block)

                        if not self.cursor.goto_next_sibling():
                            break

                    self.cursor.goto_parent()

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()

    def _parse_function_call(self, func_type: str, block: Block):
        callable_name = self.cursor.node.text

        if func_type == 'attribute':
            callable_name = callable_name.split('.')[0]
        elif func_type != 'identifier':
            raise NotImplemented()

        if callable_name in BUILTINS:
            return

        scope_variable = block.get_variable_in_scope(callable_name)

        if scope_variable:
            return

        scope_block = block.get_block_in_scope(callable_name)

        if scope_block:
            block.uses.append(scope_block)

            return

        undefined_block = Block(
            type=BlockType.Undefined,
            root_node=None,
        )
        block.uses.append(undefined_block)

    def _traverse_assignment(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            match (self._node_name, self._node_type):
                case ('left', 'identifier'):
                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[var.name] = var
                case ('left', 'pattern_list'):
                    raise NotImplemented()
                case ('left', _):
                    raise NotImplemented()
                case ('right', 'call'):
                    self._traverse_call(block)
                case ('right', _):
                    pass

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()

    def _traverse_expression(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            node_type = self.cursor.node.type

            match node_type:
                case 'assignment':
                    self._traverse_assignment(block)
                case 'call':
                    self._traverse_call(block)

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()


tree = parser.parse(source_code)
cur = tree.walk()

walker = TreeWalker(cur)
m = walker.parse_file(FILE_PATH)

print('Done!')
