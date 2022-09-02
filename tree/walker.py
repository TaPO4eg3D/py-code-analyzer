from tree_sitter import TreeCursor

from .consts import BUILTINS
from .structures import Variable, BlockType, Block, ModuleBlockData


class TreeDebugger:
    def show(self, block: Block):
        self._show(block)

    def _show(self, block: Block, level = 0):
        def lprint(message: str, indent: int = 0):
            print('\t' * level + ' ' * indent + str(message))

        has_functions = False
        has_classes = False
        has_variables = len(block.variable_table)
        has_deps = len(block.uses)

        for _, inner_block in block.block_table.items():
            match inner_block.type:
                case BlockType.Function:
                    has_functions = True
                case BlockType.Class:
                    has_classes = True

        if has_functions:
            lprint('Functions: ')
            for block_name, func_block in block.block_table.items():
                if func_block.type == BlockType.Function:
                    lprint('Name: ' + block_name.decode('utf-8'), 2)
                    self._show(func_block, level + 1)

        if has_classes:
            lprint('Classes: ')
            for block_name, class_block in block.block_table.items():
                if class_block.type == BlockType.Class:
                    lprint('Name: ' + block_name.decode('utf-8'), 2)
                    self._show(class_block, level + 1)

        if has_variables:
            lprint('Declared_variables: ')
            for var_name, _ in block.variable_table.items():
                lprint('- ' + var_name.decode('utf-8'), 2)

        # TODO: Make it recursive to count inner_block deps
        if has_deps:
            lprint('Dependencies:')
            for dep in block.uses:
                lprint(f'- {dep.type}: ' + str(dep.name), 2)


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
    def _node_name(self) -> str | None:
        return self.cursor.current_field_name()

    def _rewind(self):
        self.cursor.goto_parent()
        self.cursor.goto_first_child()

    def _parse_block(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            match self._node_type:
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

        self._rewind()

        while True:
            match self._node_type:
                case 'function_definition':
                    function_name = self._parse_function_name()
                    function = block.block_table[function_name]

                    self._traverse_function_definition(function)
                case 'class_definition':
                    class_name = self._parse_class_name()
                    klass = block.block_table[class_name]

                    self._traverse_class_definition(klass)

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()

    def _traverse_function_definition(self, block: Block):
        self.cursor.goto_first_child()

        self._traverse_general(block)

        # General travers gives the control back when it stumbles upon the "block" node
        self._parse_block(block)

        self.cursor.goto_first_child()
        self._traverse_general(block)
        self.cursor.goto_parent()

        self.cursor.goto_parent()

    def _traverse_class_definition(self, block: Block):
        self.cursor.goto_first_child()

        self._traverse_general(block)

        # General travers gives the control back when it stumbles upon the "block" node
        self._parse_block(block)

        self.cursor.goto_first_child()
        self._traverse_general(block)
        self.cursor.goto_parent()

        self.cursor.goto_parent()

    def _traverse_inner_block_statement(self, block_type: BlockType, block: Block):
        inner_block = Block(
            type=block_type,
            parent=block,
            starts_at=self.cursor.node.start_point[0],
            ends_at=self.cursor.node.end_point[0],
            root_node=self.cursor.node,
        )
        inner_block.name = f'inner_block__{inner_block.starts_at}_{inner_block.ends_at}'.encode('utf-8')
        block.block_table[inner_block.name] = inner_block

        if self._node_type == 'for_statement':
            # The left side of the for_statement is basically assignment
            self.cursor.goto_first_child()
            self._traverse_assignment(inner_block)

            # Skip the left node completly
            self.cursor.goto_first_child()
            while self._node_name != 'right':
                self.cursor.goto_next_sibling()
        else:
            self.cursor.goto_first_child()

        self._traverse_general(inner_block)

        # Give back control when stumbles upon "block" node
        # General travers gives the control back when it stumbles upon the "block" node
        self._parse_block(inner_block)

        self.cursor.goto_first_child()
        self._traverse_general(inner_block)
        self.cursor.goto_parent()

        self.cursor.goto_parent()

    def _parse_function_name(self) -> bytes:
        self.cursor.goto_first_child()
        self.cursor.goto_next_sibling()

        if self.cursor.node.type != 'identifier':
            raise RuntimeError(
                f'Error in Function declaration!',
            )

        function_name = self.cursor.node.text
        self.cursor.goto_parent()

        return function_name

    def _parse_function_definition(self, parent: Block) -> Block:
        function = Block(
            type=BlockType.Function,
            parent=parent,
            root_node=self.cursor.node,
            starts_at=self.cursor.node.start_point[0],
            ends_at=self.cursor.node.end_point[0],
        )
        function.name = self._parse_function_name()

        if obj := parent.block_table.get(function.name):
            raise RuntimeError(
                f'{obj.type} "{function.name}" already decalred on pos: {obj.starts_at}'
            )

        return function

    def _parse_class_name(self) -> bytes:
        self.cursor.goto_first_child()
        self.cursor.goto_next_sibling()

        if self.cursor.node.type != 'identifier':
            raise RuntimeError(
                f'Error in Class declaration!',
            )

        class_name = self.cursor.node.text
        self.cursor.goto_parent()

        return class_name

    def _parse_class_definition(self, parent: Block) -> Block:
        klass = Block(
            type=BlockType.Class,
            parent=parent,
            root_node=self.cursor.node,
            starts_at=self.cursor.node.start_point[0],
            ends_at=self.cursor.node.end_point[0],
        )
        klass.name = self._parse_class_name()
        klass.variable_table[b'self'] = Variable(name=b'self')

        if obj := parent.block_table.get(klass.name):
            raise RuntimeError(
                f'{obj.type} "{klass.name}" already decalred on pos: {obj.starts_at}'
            )

        return klass

    def _parse_identifier_usage(self, block: Block):
        callable_name = self.cursor.node.text

        if self._node_type == 'attribute':
            callable_name = callable_name.split(b'.')[0]
        elif self._node_type != 'identifier':
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

    def _traverse_general(self, block: Block):
        while True:
            match (self._node_name, self._node_type):
                # Give up the control when a block is found
                case (_, 'block'):
                    return
                case ('name', 'identifier'):
                    pass
                case (_, 'parameters'):
                    self._traverse_function_params(block)
                case (_, 'function_definition' | 'class_definition' | 'def' | 'class'):
                    pass
                case (_, 'if_statement' | 'for_statement' | 'while_statement'):
                    if self._node_type == 'if_statement':
                        block_type = BlockType.Condition
                    else:
                        block_type = BlockType.Loop

                    self._traverse_inner_block_statement(block_type, block)
                case (_, 'assignment'):
                    self._traverse_assignment(block)
                case (_, 'identifier' | 'attribute'):
                    self._parse_identifier_usage(block)
                case _:
                    if self.cursor.goto_first_child():
                        self._traverse_general(block)

                        self.cursor.goto_parent()

            if not self.cursor.goto_next_sibling():
                break
    
    def _traverse_function_params(self, block: Block):
        assert block.type == BlockType.Function
        self.cursor.goto_first_child()
        while True:
            match self._node_type:
                case 'identifier':
                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[var.name] = var
                case 'typed_parameter' | 'default_parameter':
                    self.cursor.goto_first_child()
                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[var.name] = var
                    self.cursor.goto_parent()

            if not self.cursor.goto_next_sibling():
                break
        
        self.cursor.goto_parent()

    def _traverse_assignment(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            match (self._node_name, self._node_type):
                case ('left', 'identifier'):
                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[var.name] = var
                case ('left', 'pattern_list' | 'tuple_pattern'):
                    self._parse_pattern_list(block)
                case ('left', _):
                    raise NotImplemented()
                case ('right', _):
                    self._traverse_general(block)

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()

    def _parse_pattern_list(self, block: Block):
        self.cursor.goto_first_child()

        while True:
            match self._node_type:
                case 'identifier':
                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[self.cursor.node.text] = var
                case 'list_splat_pattern':
                    self.cursor.goto_first_child()
                    self.cursor.goto_next_sibling()

                    var = Variable(name=self.cursor.node.text)
                    block.variable_table[self.cursor.node.text] = var

                    self.cursor.goto_parent()

            if not self.cursor.goto_next_sibling():
                break

        self.cursor.goto_parent()
