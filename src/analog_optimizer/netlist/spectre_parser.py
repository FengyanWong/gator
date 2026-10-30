"""Tokenized, source-located Spectre subset, not a simulator/PDK model parser."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from pathlib import Path
import re

from analog_optimizer.graph.circuit_graph import (
    CircuitGraph, Connection, Device, Diagnostic, Net, ParameterBinding,
    ParameterGroup, ParameterValue, SourceSpan,
)
from .config import ParserConfig
from .expressions import UnresolvedExpression, evaluate


class ParseError(ValueError):
    def __init__(self, message: str, source: SourceSpan):
        self.source = source
        super().__init__(f"{source}: {message}")


@dataclass(frozen=True)
class Token:
    text: str
    source: SourceSpan


_ATOM = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[A-Za-z]*|[A-Za-z_$][\w.$!:<>#]*")
_IDENT = re.compile(r"[A-Za-z_]\w*\Z")


def statements(text: str, file: str) -> list[list[Token]]:
    """Scan physical tokens before interpreting statement/assignment syntax."""
    result: list[list[Token]] = []
    current: list[Token] = []
    i, line, column = 0, 1, 1
    while i < len(text):
        char = text[i]
        source = SourceSpan(file, line, column)
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = end if end >= 0 else len(text)
            continue
        if char == "\\":
            match = re.match(r"\\[ \t]*\r?\n", text[i:])
            if not match:
                raise ParseError("Only backslash-newline continuation is supported", source)
            i += len(match[0])
            line, column = line + 1, 1
            continue
        if char == "\n":
            if current:
                result.append(current)
                current = []
            i, line, column = i + 1, line + 1, 1
            continue
        if char.isspace():
            i, column = i + 1, column + 1
            continue
        if char in "\"'":
            end = i + 1
            while end < len(text) and text[end] != char and text[end] != "\n":
                if text[end] == "\\":
                    raise ParseError("Escaped strings are outside this subset", source)
                end += 1
            if end >= len(text) or text[end] != char:
                raise ParseError("Unterminated quoted value", source)
            word = text[i:end + 1]
        elif char in "(){}[]=+-*/":
            word = "**" if text.startswith("**", i) else char
        else:
            match = _ATOM.match(text, i)
            if not match:
                raise ParseError(f"Unsupported character {char!r}", source)
            word = match[0]
        current.append(Token(word, source))
        i, column = i + len(word), column + len(word)
    if current:
        result.append(current)
    return result


def assignments(tokens: list[Token]) -> dict[str, tuple[str, SourceSpan]]:
    result: dict[str, tuple[str, SourceSpan]] = {}
    i = 0
    while i < len(tokens):
        start = tokens[i]
        if not _IDENT.fullmatch(start.text) or i + 1 >= len(tokens) or tokens[i + 1].text != "=":
            raise ParseError("Expected parameter=value", start.source)
        if start.text in result:
            raise ParseError(f"Duplicate parameter {start.text}", start.source)
        j, stack = i + 2, []
        while j < len(tokens):
            token = tokens[j]
            if not stack and j > i + 2 and j + 1 < len(tokens) and tokens[j + 1].text == "=":
                break
            if token.text in ("(", "{", "["):
                stack.append(token.text)
            elif token.text in (")", "}", "]"):
                if not stack or stack.pop() != {")": "(", "}": "{", "]": "["}[token.text]:
                    raise ParseError("Unbalanced parameter expression", token.source)
            j += 1
        if stack or j == i + 2:
            raise ParseError("Empty/unbalanced parameter expression", start.source)
        result[start.text] = (" ".join(t.text for t in tokens[i + 2:j]), tokens[i + 2].source)
        i = j
    return result


@dataclass
class Scope:
    name: str
    ports: tuple[str, ...] = ()
    parameters: dict[str, tuple[str, SourceSpan]] = field(default_factory=dict)
    body: list[list[Token]] = field(default_factory=list)


class Environment:
    def __init__(self, definitions: dict[str, tuple[str, SourceSpan]],
                 parent: Environment | None = None, overrides: dict[str, float | str] | None = None):
        self.definitions, self.parent = definitions, parent
        self.overrides = overrides or {}
        self.cache: dict[str, float] = {}
        self.active: set[str] = set()

    def lookup(self, name: str) -> float:
        if name in self.overrides:
            value = self.overrides[name]
            if isinstance(value, str):
                raise UnresolvedExpression(value)
            return value
        if name in self.cache:
            return self.cache[name]
        if name in self.active:
            raise UnresolvedExpression(f"Cyclic parameter dependency: {name}")
        if name not in self.definitions:
            if self.parent:
                return self.parent.lookup(name)
            raise UnresolvedExpression(f"Unknown parameter {name}")
        self.active.add(name)
        try:
            value = evaluate(self.definitions[name][0], self.lookup)
            self.cache[name] = value
            return value
        finally:
            self.active.remove(name)


class SpectreParser:
    def __init__(self, config: ParserConfig):
        self.config = config

    def parse_file(self, path: str | Path, *, top: str | None = None) -> CircuitGraph:
        path = Path(path).resolve()
        return self.parse_text(path.read_text(), source=str(path), circuit_id=path.stem, top=top)

    def parse_text(self, text: str, *, source: str = "<memory>",
                   circuit_id: str = "synthetic", top: str | None = None) -> CircuitGraph:
        manifest, root, scopes, globals_, context = self._declarations(text, source)
        graph = CircuitGraph(circuit_id, [], [], [], {}, metadata={
            "parser_version": "spectre-subset-2", "mapping_version": self.config.mapping_version,
            "source_manifest": manifest, "analysis_context": context, "selected_top": top,
            "globals": sorted(globals_), "scope_parameters": {
                name: s.parameters for name, s in [(root.name, root), *scopes.items()]},
        })
        self._expand(graph, root, scopes, globals_, source, top)
        self._parameter_groups(graph)
        graph.validate(require_complete=False)
        return graph

    def _declarations(self, text, source):
        """The statements of `text` and of every file it includes (each file's sha256 in `manifest`), sorted into the
        root scope and the subckt definitions: (manifest, root, scopes, globals_, context)."""
        manifest: dict[str, str] = {}

        def load(content: str, file: str, stack: tuple[Path, ...]) -> list[list[Token]]:
            manifest[file] = hashlib.sha256(content.encode()).hexdigest()
            output: list[list[Token]] = []
            for line in statements(content, file):
                if line[0].text != "include":
                    output.append(line)
                    continue
                if len(line) != 2 or line[1].text[:1] != '"':
                    raise ParseError("Only include \"file\" is supported; model sections are not expanded", line[0].source)
                if file.startswith("<"):
                    raise ParseError("Includes require an explicit source file path", line[0].source)
                path = (Path(file).parent / line[1].text[1:-1]).resolve()
                if not any(path.is_relative_to(root.resolve()) for root in self.config.include_roots):
                    raise ParseError("Include outside configured allowed roots", line[1].source)
                if path in stack:
                    raise ParseError("Include cycle", line[1].source)
                if len(stack) > self.config.max_include_depth:
                    raise ParseError("Include depth exceeded", line[1].source)
                try:
                    included = path.read_text()
                except (OSError, UnicodeError) as exc:
                    raise ParseError(f"Cannot read include: {type(exc).__name__}", line[1].source) from exc
                output.extend(load(included, str(path), (*stack, path)))
            return output

        root = Scope("<root>")
        scopes: dict[str, Scope] = {}
        scope = root
        globals_ = set(self.config.global_nets)
        context: list[dict] = []
        stack = () if source.startswith("<") else (Path(source).resolve(),)
        for line in load(text, source, stack):
            head, words = line[0], [t.text for t in line]
            if head.text == "simulator":
                if words != ["simulator", "lang", "=", "spectre"]:
                    raise ParseError("Only simulator lang=spectre is supported (no mixed dialects)", head.source)
            elif head.text == "global":
                if scope is not root or len(line) < 2:
                    raise ParseError("global must declare nets at top level", head.source)
                globals_.update(words[1:])
            elif head.text == "parameters":
                self._merge_parameters(scope, assignments(line[1:]), head.source)
            elif head.text == "subckt":
                if scope is not root or len(line) < 2:
                    raise ParseError("Nested/malformed subckt definition", head.source)
                name = words[1]
                if name in scopes:
                    raise ParseError(f"Duplicate subckt {name}", head.source)
                # Native Virtuoso Spectre exports omit parentheses in subckt
                # declarations. Instance port lists still require them.
                if len(line) > 2 and words[2] == "(":
                    ports, tail = self._ports(line, 2)
                else:
                    if any(not _ATOM.fullmatch(t.text) for t in line[2:]):
                        raise ParseError("Invalid bare subckt ports; put defaults on a parameters line", head.source)
                    ports, tail = tuple(words[2:]), []
                if tail:
                    raise ParseError("Put subckt defaults on a parameters line", tail[0].source)
                if len(set(ports)) != len(ports):
                    raise ParseError("Duplicate subckt port", head.source)
                scope = scopes[name] = Scope(name, ports)
            elif head.text == "ends":
                if scope is root or len(words) > 2 or (len(words) == 2 and words[1] != scope.name):
                    raise ParseError("Mismatched ends", head.source)
                scope = root
            elif head.text == "save" or (len(words) > 1 and words[1] in ("dc", "ac", "tran", "options", "info")):
                if scope is not root:
                    raise ParseError("Analysis/context inside subckt is outside this subset", head.source)
                context.append({"text": " ".join(words), "source": head.source})
            else:
                scope.body.append(line)
        if scope is not root:
            raise ParseError(f"Unclosed subckt {scope.name}", SourceSpan(source, len(text.splitlines())))
        return manifest, root, scopes, globals_, context

    def _expand(self, graph, root, scopes, globals_, source, top):
        """The devices, nets and connections of the selected top (or of the root scope), expanded through every subckt
        instance into `graph`."""
        nets: dict[str, Net] = {}

        def net(name: str, path: str, port_map: dict[str, str]) -> str:
            identifier = port_map.get(name, name if name in globals_ or not path else f"{path}/{name}")
            if identifier not in nets:
                roles = self.config.net_roles.get(identifier, ("normal",))
                origin = "config" if identifier in self.config.net_roles else "default"
                nets[identifier] = Net(identifier, roles, origin)
            return identifier

        def resolve(raw: str, location: SourceSpan, env: Environment, label: str,
                    *, numeric: bool = True) -> ParameterValue:
            try:
                value = evaluate(raw, env.lookup)
                return ParameterValue(raw, value, location)
            except UnresolvedExpression as exc:
                if numeric:
                    graph.diagnostics.append(Diagnostic("unresolved_expression", f"{label}: {exc}", location, "warning"))
                return ParameterValue(raw, None, location, str(exc))

        def expand(current: Scope, env: Environment, path: str,
                   port_map: dict[str, str], ancestry: tuple[str, ...]) -> None:
            if len(ancestry) > self.config.max_hierarchy_depth:
                raise ParseError("Hierarchy depth exceeded", SourceSpan(source, 1))
            seen: set[str] = set()
            for line in current.body:
                if len(line) < 4 or line[1].text != "(":
                    raise ParseError("Unsupported statement; expected instance (ports) model params", line[0].source)
                name = line[0].text
                if name in seen:
                    raise ParseError(f"Duplicate instance {name}", line[0].source)
                seen.add(name)
                ports, tail = self._ports(line, 1)
                if not tail:
                    raise ParseError("Missing model/subckt name", line[0].source)
                model = tail[0].text
                params = assignments(tail[1:])
                identifier = f"{path}/{name}" if path else name
                actual_nets = [net(p, path, port_map) for p in ports]
                mapping = self.config.models.get(model)
                if mapping is None and model in scopes:
                    child = scopes[model]
                    if model in ancestry:
                        raise ParseError(f"Recursive subckt {model}", line[0].source)
                    if len(ports) != len(child.ports):
                        raise ParseError(f"Wrong port count for subckt {model}", line[0].source)
                    if params.keys() - child.parameters.keys():
                        raise ParseError("Undeclared subckt parameter override (implicit m unsupported)", line[0].source)
                    overrides: dict[str, float | str] = {}
                    for key, (raw, loc) in params.items():
                        value = resolve(raw, loc, env, f"{identifier}.{key}")
                        overrides[key] = value.value if value.valid else value.reason or "Unresolved override"
                    expand(child, Environment(child.parameters, env, overrides), identifier,
                           dict(zip(child.ports, actual_nets)), (*ancestry, model))
                    continue
                if mapping:
                    if len(ports) != len(mapping.terminals):
                        raise ParseError(f"Wrong port count for mapped model {model}", line[0].source)
                    terminals, roles, kind = mapping.terminals, mapping.roles, mapping.kind
                else:
                    terminals = tuple(f"port_{i}" for i in range(len(ports)))
                    roles, kind = ("unknown",) * len(ports), "unknown"
                    graph.diagnostics.append(Diagnostic("unknown_device", f"Unmapped model {model} on {identifier}", line[0].source))
                graph.devices.append(Device(identifier, kind, model, terminals, line[0].source))
                values: dict[str, ParameterValue] = {}
                for key, (raw, loc) in params.items():
                    canonical = mapping.parameters.get(key, key) if mapping else key
                    if canonical in values:
                        raise ParseError(f"Conflicting parameter alias {canonical}", loc)
                    values[canonical] = replace(resolve(raw, loc, env, f"{identifier}.{canonical}",
                                                         numeric=mapping is None or key in mapping.parameters),
                                                source_name=key)
                graph.parameters[identifier] = values
                for ordinal, (terminal, role, target) in enumerate(zip(terminals, roles, actual_nets)):
                    graph.connections.append(Connection(identifier, target, terminal, ordinal, role))

        root_env = Environment(root.parameters)
        if top:
            if top not in scopes:
                raise ParseError(f"Unknown selected top {top}", SourceSpan(source, 1))
            selected = scopes[top]
            port_map = {p: net(p, "", {}) for p in selected.ports}
            expand(selected, Environment(selected.parameters, root_env), "", port_map, (top,))
            graph.metadata["ports"] = selected.ports
        else:
            expand(root, root_env, "", {}, ())
            graph.metadata["ports"] = ()
        graph.nets = list(nets.values())

    def _parameter_groups(self, graph):
        """The configured parameter groups; a group without a value takes its first member's, read from the graph."""
        for item in self.config.parameter_groups:
            spec = dict(item)
            spec["members"] = tuple(ParameterBinding(**member) for member in spec["members"])
            if not spec["members"]:
                raise ValueError(f"Empty parameter group {spec['id']}")
            if "value" not in spec:
                member = spec["members"][0]
                value = graph.parameters.get(member.device_id, {}).get(member.parameter)
                if value is None or not value.valid or member.ratio <= 0:
                    raise ValueError(f"Unresolved parameter group {spec['id']}")
                spec["value"] = value.value / member.ratio
            graph.parameter_groups.append(ParameterGroup(**spec))

    @staticmethod
    def _merge_parameters(scope: Scope, params: dict, source: SourceSpan) -> None:
        if scope.parameters.keys() & params.keys():
            raise ParseError("Duplicate parameter declaration", source)
        scope.parameters.update(params)

    @staticmethod
    def _ports(line: list[Token], start: int) -> tuple[tuple[str, ...], list[Token]]:
        if start >= len(line) or line[start].text != "(":
            raise ParseError("Expected parenthesized port list", line[0].source)
        end = start + 1
        while end < len(line) and line[end].text != ")":
            if line[end].text in "(=+-*/{}":
                raise ParseError("Unsupported net name in port list", line[end].source)
            end += 1
        if end == len(line):
            raise ParseError("Unclosed port list", line[start].source)
        return tuple(t.text for t in line[start + 1:end]), line[end + 1:]
