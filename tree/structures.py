import typing
from dataclasses import dataclass, field
from enum import Enum

from tree_sitter import Node


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
