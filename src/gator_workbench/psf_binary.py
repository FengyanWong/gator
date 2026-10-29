"""Spectre's binary PSF (psfbin) of one result without a sweep - an operating-point info file such as ``dcOpInfo.info``
or ``finalTimeOP.info`` (record 7.298, operating points of Maestro-measured tasks).

The format is self-describing, big-endian 32-bit words:

- the file ends with the section table, the word ``Clarissa`` and the offset of that table (its last 4 bytes);
- the table pairs a section number (0 header, 1 types, 2 sweeps, 3 traces, 4 values) with its offset;
- a section starts with 21 and its end offset; the type and value sections then hold a minor section (22 + end) of
  items (16), then an index (19) this reader does not need;
- a header item is a property: 33 string, 34 int32, 35 double (name and value);
- a type item: 16, id, name, array kind, data type (1 int8 and 5 int32 in a word each, 11 double, 12 complex,
  16 struct: its member types follow, closed by 18), then its properties;
- a value item: 16, id, name, type id, the value as that type lays it out (a struct: its members in order), then its
  properties.

Strings are a length word and the bytes, padded to a whole word. Only results without a sweep are read: a swept file
(``PSF sweeps`` > 0) or anything that does not parse is refused with PsfError, never guessed at."""
from __future__ import annotations

import struct

SIGNATURE = b'Clarissa'
HEADER, TYPES, VALUES = 0, 1, 4
MAJOR, MINOR, ITEM, STRUCT_END, INDEX = 21, 22, 16, 18, 19
PROPERTIES = {33: 'string', 34: 'int', 35: 'double'}
INT8, INT32, DOUBLE, COMPLEX, STRUCT = 1, 5, 11, 12, 16


class PsfError(ValueError):
    """The file is not a binary PSF result this reader understands."""


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def word(self, at: int) -> int:
        if at < 0 or at + 4 > len(self.data):
            raise PsfError(f'truncated at byte {at}')
        return struct.unpack_from('>i', self.data, at)[0]

    def double(self, at: int) -> float:
        if at < 0 or at + 8 > len(self.data):
            raise PsfError(f'truncated at byte {at}')
        return struct.unpack_from('>d', self.data, at)[0]

    def string(self, at: int) -> tuple[str, int]:
        size = self.word(at)
        if size < 0 or at + 4 + size > len(self.data):
            raise PsfError(f'bad string at byte {at}')
        text = self.data[at + 4:at + 4 + size].decode('latin-1')
        return text, at + 4 + (size + 3) // 4 * 4

    def properties(self, at: int, end: int, found: dict | None=None) -> int:
        while at < end and self.word(at) in PROPERTIES:
            kind = self.word(at)
            name, at = self.string(at + 4)
            if kind == 33:
                value, at = self.string(at)
            elif kind == 34:
                value, at = self.word(at), at + 4
            else:
                value, at = self.double(at), at + 8
            if found is not None:
                found[name] = value
        return at


def _sections(reader: _Reader) -> dict[int, int]:
    data = reader.data
    if len(data) < 32 or data[-12:-4] != SIGNATURE:
        raise PsfError('not a binary PSF file (no "Clarissa" signature)')
    table = reader.word(len(data) - 4)
    if not 0 < table <= len(data) - 12 or (len(data) - 12 - table) % 8:
        raise PsfError('bad section table')
    return {reader.word(at): reader.word(at + 4) for at in range(table, len(data) - 12, 8)}


def _section_items(reader: _Reader, start: int) -> tuple[int, int]:
    """(first item offset, end offset) of a type or value section: after its major and minor section words."""
    if reader.word(start) != MAJOR:
        raise PsfError(f'no section at byte {start}')
    end = reader.word(start + 4)
    at = start + 8
    if reader.word(at) == MINOR:
        end, at = reader.word(at + 4), at + 8
    if not start < at <= end <= len(reader.data):
        raise PsfError('bad section bounds')
    return at, end


def _type(reader: _Reader, offset: int, end: int, types: dict) -> tuple[int, int]:
    if reader.word(offset) != ITEM:
        raise PsfError(f'no type definition at byte {offset}')
    type_id = reader.word(offset + 4)
    name, offset = reader.string(offset + 8)
    datatype = reader.word(offset + 4)
    offset += 8
    members = []
    if datatype == STRUCT:
        while reader.word(offset) == ITEM:
            member, offset = _type(reader, offset, end, types)
            members.append(member)
        if reader.word(offset) not in (STRUCT_END, STRUCT_END - 1):
            raise PsfError(f'unclosed struct type {name!r}')
        offset += 4
    elif datatype not in (INT8, INT32, DOUBLE, COMPLEX):
        raise PsfError(f'type {name!r} has a data type ({datatype}) this reader does not read')
    offset = reader.properties(offset, end)
    types[type_id] = (name, datatype, tuple(members))
    return type_id, offset


def _value(reader: _Reader, type_id: int, offset: int, types: dict) -> tuple[int | float | complex | dict, int]:
    if type_id not in types:
        raise PsfError(f'value of an undefined type {type_id}')
    name, datatype, members = types[type_id]
    if datatype in (INT8, INT32):
        return reader.word(offset), offset + 4
    if datatype == DOUBLE:
        return reader.double(offset), offset + 8
    if datatype == COMPLEX:
        return complex(reader.double(offset), reader.double(offset + 8)), offset + 16
    record = {}
    for member in members:
        record[types[member][0]], offset = _value(reader, member, offset, types)
    return record, offset


def read(data: bytes) -> tuple[dict, dict]:
    """(header properties, {item name: value}) of a binary PSF result without a sweep; a struct value is a dict of its
    members (an operating point: {'ids': ..., 'gm': ..., 'region': ...})."""
    reader = _Reader(bytes(data))
    sections = _sections(reader)
    if HEADER not in sections or TYPES not in sections or VALUES not in sections:
        raise PsfError('a header, type and value section are required')
    header = {}
    start = sections[HEADER]
    if reader.word(start) != MAJOR:
        raise PsfError('no header section')
    reader.properties(start + 8, reader.word(start + 4), header)
    if header.get('PSF sweeps', 0) != 0:
        raise PsfError('a swept result: this reader reads results without a sweep only')
    types = {}
    at, end = _section_items(reader, sections[TYPES])
    while at < end and reader.word(at) == ITEM:
        _, at = _type(reader, at, end, types)
    values = {}
    at, end = _section_items(reader, sections[VALUES])
    while at < end and reader.word(at) == ITEM:
        name, at = reader.string(at + 8)
        type_id = reader.word(at)
        values[name], at = _value(reader, type_id, at + 4, types)
        at = reader.properties(at, end)
    if at != end:
        raise PsfError(f'the value section ends at byte {end}, the items at {at}')
    return header, values


def read_file(path) -> tuple[dict, dict]:
    """Decode an unswept binary PSF result from a file."""
    with open(path, 'rb') as handle:
        return read(handle.read())
