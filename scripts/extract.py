#!/usr/bin/env python3
"""Read Mobium's surfaces into data/: the tools as the MCP server lists them,
every CLI command's help, and each client's public members with their doc
comments and the tools they call.

Nothing here is written by hand. The site is generated from what the source
says, so a page cannot describe a flag or a method that no longer exists.

    python3 scripts/extract.py --src ~/mobium-public --bin ./mobium
"""

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOOL_RE = re.compile(r"""["'](app_[a-z_]+)["']""")
SECTION_RE = re.compile(r"^\s*(?://|#) -- ([a-z][a-z ,]+?) -+\s*$")


def run(*args, stdin=None):
    return subprocess.run(args, input=stdin, capture_output=True, text=True, check=True).stdout


# -- MCP -------------------------------------------------------------------


def mcp_tools(binary):
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "mobium-docs", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    out = run(binary, "mcp", stdin="".join(json.dumps(m) + "\n" for m in msgs))
    for line in out.splitlines():
        msg = json.loads(line)
        if msg.get("id") == 2:
            return msg["result"]["tools"]
    raise SystemExit("mobium mcp did not answer tools/list")


# -- CLI -------------------------------------------------------------------

FLAG_RE = re.compile(r"^\s+(?:-(\w), )?--([\w-]+)(?: (\w+))?\s{2,}(.*)$")


def parse_help(text):
    """Split cobra's help into its parts: the description, usage, aliases,
    examples, subcommands, flags and global flags."""
    parts = {"description": [], "usage": [], "aliases": [], "examples": [],
             "commands": [], "flags": [], "global": []}
    heads = {"Usage:": "usage", "Aliases:": "aliases", "Examples:": "examples",
             "Available Commands:": "commands", "Flags:": "flags",
             "Global Flags:": "global"}
    cur = "description"
    for line in text.splitlines():
        if line.strip() in heads and not line.startswith(" "):
            cur = heads[line.strip()]
            continue
        if line.startswith("Use \"mobium") or line.startswith("Additional help topics"):
            cur = None
            continue
        if cur:
            parts[cur].append(line)

    def flags(lines):
        out = []
        for line in lines:
            m = FLAG_RE.match(line)
            if m:
                short, name, typ, desc = m.groups()
                if name == "help":
                    continue
                default = None
                d = re.search(r" \(default (.*)\)$", desc)
                if d:
                    default, desc = d.group(1), desc[: d.start()]
                out.append({"name": name, "short": short, "type": typ or "bool",
                            "description": desc.strip(), "default": default})
            elif out and line.strip():
                out[-1]["description"] += " " + line.strip()
        return out

    usage = [l.strip() for l in parts["usage"] if l.strip()]
    return {
        "description": "\n".join(parts["description"]).strip(),
        "usage": [u for u in usage if not u.endswith("[command]")] or usage,
        "aliases": ", ".join(l.strip() for l in parts["aliases"] if l.strip()),
        "examples": "\n".join(l[2:] if l.startswith("  ") else l
                              for l in parts["examples"]).strip("\n"),
        "commands": [l.split()[0] for l in parts["commands"] if l.strip()],
        "shorts": {l.split()[0]: l.split(None, 1)[1].strip() for l in parts["commands"] if len(l.split()) > 1},
        "flags": flags(parts["flags"]),
        "global": flags(parts["global"]),
    }


def cli_commands(binary):
    root = parse_help(run(binary, "--help"))
    out = {"root": root, "commands": {}}

    def walk(path, short):
        h = parse_help(run(binary, *path, "--help"))
        h["short"] = short
        out["commands"][" ".join(path)] = h
        for sub in h["commands"]:
            if sub not in ("help", "completion"):
                walk(path + [sub], h["shorts"].get(sub, ""))

    for c in root["commands"]:
        if c not in ("help", "completion"):
            walk([c], root["shorts"].get(c, ""))
    return out


# -- clients ---------------------------------------------------------------


def tools_in(text):
    seen = []
    for t in TOOL_RE.findall(text):
        if t not in seen:
            seen.append(t)
    return seen


def c_style(path, doc_kind, lang):
    """Members of a Go, Java or C# file: each public declaration with the
    doc comment above it, the section it sits in, and the tools its body
    names. doc_kind is 'go' (//), 'javadoc' (/** */) or 'xml' (///)."""
    lines = Path(path).read_text().splitlines()
    members, doc, section, cls = [], [], "", ""
    i = 0
    in_block = False
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = SECTION_RE.match(line)
        if m:
            section, doc = m.group(1), []
            i += 1
            continue
        if doc_kind == "javadoc":
            if s.startswith("/**"):
                in_block, doc = True, []
            if in_block:
                doc.append(s)
                if s.endswith("*/"):
                    in_block = False
                i += 1
                continue
        elif doc_kind == "xml" and s.startswith("///"):
            doc.append(s[3:].strip())
            i += 1
            continue
        elif doc_kind == "go" and s.startswith("//"):
            doc.append(s[2:].strip() if not s.startswith("// ") else s[3:])
            i += 1
            continue
        decl = declaration(lines, i, lang)
        if decl:
            text, end, kind, name, owner = decl
            if kind == "class":
                cls = name
            members.append({"kind": kind, "name": name, "owner": owner or cls,
                            "signature": text, "doc": clean_doc(doc, doc_kind),
                            "section": section, "line": i + 1})
            i = end
            doc = []
            continue
        if s and not s.startswith("@"):
            doc = []
        i += 1
    # The tools each member calls: its body runs to the next member.
    bodies = {}
    for n, mem in enumerate(members):
        start = mem["line"] - 1
        stop = members[n + 1]["line"] - 1 if n + 1 < len(members) else len(lines)
        code = "\n".join(l for l in lines[start:stop] if not re.match(r"\s*(?://|/\*|\*|#)", l))
        mem["tools"] = tools_in(code) if mem["kind"] != "class" else []
        bodies[id(mem)] = code
    # A public method that reaches its tool through a private helper —
    # Go's network(), say — calls what the helper calls.
    # So does an overload that hands its call to another.
    helpers = {}
    for m in members:
        if m["kind"] in ("private", "method", "func") and m["tools"]:
            helpers.setdefault(m["name"], [])
            helpers[m["name"]] += [t for t in m["tools"] if t not in helpers[m["name"]]]
    for mem in members:
        if mem["kind"] in ("method", "func") and not mem["tools"]:
            for h, tools in helpers.items():
                calls = len(re.findall(r"(?<![\w.])" + re.escape(h) + r"\(|\bthis\." + re.escape(h) + r"\(|\bd\." + re.escape(h) + r"\(", bodies[id(mem)]))
                if calls > (1 if h == mem["name"] else 0):
                    mem["tools"] += [t for t in tools if t not in mem["tools"]]
    if lang in ("java", "cs"):
        owners(lines, members)
    return [m for m in members if m["kind"] != "private"]


def owners(lines, members):
    """The class each member belongs to, by brace depth: a nested class ends
    where its braces close, and the members after it are the outer class's."""
    depth, before = 0, []
    for l in lines:
        before.append(depth)
        code = re.sub(r'"(?:\\.|[^"\\])*"|'"'"r"(?:\\.|[^'\\])'"r"|//.*", "", l)
        depth += code.count("{") - code.count("}")
    spans = []
    for m in members:
        if m["kind"] == "class":
            i, d = m["line"] - 1, before[m["line"] - 1]
            end = i + 1
            while end < len(lines) and before[end] <= d and "{" not in lines[end - 1]:
                end += 1
            while end < len(lines) and before[end] > d:
                end += 1
            spans.append((m["line"], end, m["name"]))
    for m in members:
        if m["kind"] != "class":
            inside = [s for s in spans if s[0] < m["line"] <= s[1]]
            if inside:
                m["owner"] = max(inside)[2]


GO_FUNC = re.compile(r"^func (?:\((\w+) \*?(\w+)\) )?([A-Z]\w*)")
GO_PRIVATE = re.compile(r"^func (?:\(\w+ \*?(\w+)\) )?([a-z]\w*)\(")
PRIVATE = re.compile(r"^\s*(?:private|internal|protected)(?: static)?(?: async)?(?: final)? [\w<>\[\], .?]+? (\w+)\s*\(")
GO_TYPE = re.compile(r"^type ([A-Z]\w*) ")
JAVA_CLASS = re.compile(r"^\s*public (?:static )?(?:final |sealed |abstract )*(class|record|interface|enum) (\w+)")
JAVA_MEMBER = re.compile(r"^\s*public (?:static )?(?:final )?(?:<[^>]+> )?([\w<>\[\], .?]+?) (\w+)\(")
JAVA_CTOR = re.compile(r"^\s*public (\w+)\(")
CS_MEMBER = re.compile(r"^\s*public (?:static )?(?:override )?(?:async )?([\w<>\[\], .?()]+?) (\w+)(?:<[^>]*>)?\s*\(")
CS_PROP = re.compile(r"^\s*public (?:static )?([\w<>\[\], .?]+?) (\w+)\s*(?:\{|=>)")


def declaration(lines, i, lang):
    line = re.sub(r"^(\s*)(?:@\w+(?:\([^)]*\))?\s+)+(?=public )", r"\1", lines[i])
    if lang == "go":
        m = GO_FUNC.match(line)
        if m:
            recv = m.group(2)
            if recv and not recv[0].isupper():
                return None
        m = GO_PRIVATE.match(line)
        if m and (not m.group(1) or m.group(1)[0].isupper()):
            return line.strip(), i + 1, "private", m.group(2), m.group(1) or ""
        m = GO_FUNC.match(line)
        if m:
            recv = m.group(2)
            sig = line.split("{")[0].strip() if "{" in line else line.strip()
            end = i + 1
            if not line.rstrip().endswith("{") and "{" not in line:
                while end < len(lines) and "{" not in lines[end]:
                    sig += " " + lines[end].strip()
                    end += 1
            return sig.rstrip(" {"), i + 1, "method" if recv else "func", m.group(3), recv or ""
        m = GO_TYPE.match(line)
        if m:
            body = [line]
            end = i + 1
            if line.rstrip().endswith("{"):
                while end < len(lines) and lines[end] != "}":
                    body.append(lines[end])
                    end += 1
                body.append("}")
                end += 1
            return "\n".join(body), end, "type", m.group(1), ""
        return None
    if lang in ("java", "cs"):
        m = JAVA_CLASS.match(line)
        if m:
            sig = line.strip().rstrip("{").strip()
            end = i + 1
            if m.group(1) == "record":
                while ")" not in sig and end < len(lines):
                    sig += " " + lines[end].strip()
                    end += 1
                sig = sig.split("{")[0].strip()
            return sig, end, "class", m.group(2), ""
        m = PRIVATE.match(line)
        if m and not JAVA_CLASS.match(line):
            return line.strip(), i + 1, "private", m.group(1), ""
        if not line.lstrip().startswith("public "):
            return None
        m = (JAVA_MEMBER if lang == "java" else CS_MEMBER).match(line)
        ctor = JAVA_CTOR.match(line)
        if m or ctor:
            sig = line.strip()
            end = i + 1
            depth = sig.count("(") - sig.count(")")
            while depth > 0 and end < len(lines):
                sig += " " + lines[end].strip()
                depth = sig.count("(") - sig.count(")")
                end += 1
            sig = re.split(r"\s*(?:\{|=>)", sig, maxsplit=1)[0].rstrip(";").strip()
            name = ctor.group(1) if ctor and not m else m.group(2)
            return sig, end, "method", name, ""
        if lang == "cs":
            m = CS_PROP.match(line)
            if m:
                sig = line.strip()
                return sig, i + 1, "property", m.group(2), ""
    return None


def clean_doc(doc, kind):
    if kind == "javadoc":
        text = "\n".join(re.sub(r"^/?\*+/?\s?", "", l).rstrip("*/").rstrip() for l in doc)
        text = re.sub(r"\{@code ([^}]*)\}", r"`\1`", text)
        text = re.sub(r"\{@link(?:plain)? #?([^}]*)\}", r"`\1`", text)
        text = re.sub(r"</?p>", "\n", text)
        text = re.sub(r"<pre>\{@code|<pre>|</pre>", "```", text)
        return text.strip()
    if kind == "xml":
        text = "\n".join(doc)
        text = re.sub(r"<c>(.*?)</c>", r"`\1`", text, flags=re.S)
        text = re.sub(r'<see (?:cref|langword)="(?:[A-Z]:)?([^"]*)"\s*/>', r"`\1`", text)
        text = re.sub(r'<paramref name="([^"]*)"\s*/>', r"`\1`", text)
        text = re.sub(r'<param name="([^"]*)">', r"\n- `\1`: ", text)
        text = re.sub(r"<returns>", "\nReturns ", text)
        text = re.sub(r"<exception cref=\"([^\"]*)\">", r"\nThrows `\1` ", text)
        text = re.sub(r"<code>", "\n```\n", text)
        text = re.sub(r"</code>", "\n```\n", text)
        text = re.sub(r"</?(summary|remarks|para|param|returns|exception|example|list|item|description)[^>]*>", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    return "\n".join(doc).strip()


def code_of(src, fn):
    """A function's source without its docstring, whose examples name tools
    the function does not call."""
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    return "\n".join(ast.get_source_segment(src, n) or "" for n in body)


def python_members(pkg):
    out = []
    for f in sorted(Path(pkg).glob("*.py")):
        src = f.read_text()
        lines = src.splitlines()
        sections = {n + 1: m.group(1) for n, l in enumerate(lines) if (m := SECTION_RE.match(l))}
        tree = ast.parse(src)

        def section_at(lineno):
            prior = [s for n, s in sections.items() if n < lineno]
            return prior[-1] if prior else ""

        def sig(fn, owner):
            a = ast.unparse(fn.args)
            if owner:
                a = re.sub(r"^self,?\s*", "", a)
            ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
            return f"def {fn.name}({a}){ret}"

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                out.append({"kind": "func", "name": node.name, "owner": "", "signature": sig(node, ""),
                            "doc": ast.get_docstring(node) or "", "section": "", "line": node.lineno,
                            "file": f.name, "tools": tools_in(code_of(src, node))})
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                out.append({"kind": "class", "name": node.name, "owner": "",
                            "signature": f"class {node.name}({bases})" if bases else f"class {node.name}",
                            "doc": ast.get_docstring(node) or "", "section": "", "line": node.lineno,
                            "file": f.name, "tools": []})
                for fn in node.body:
                    if isinstance(fn, ast.FunctionDef) and (not fn.name.startswith("_") or fn.name in ("__enter__", "__exit__")):
                        if fn.name.startswith("__"):
                            continue
                        deco = [ast.unparse(d) for d in fn.decorator_list]
                        out.append({"kind": "property" if "property" in deco else "method",
                                    "name": fn.name, "owner": node.name, "signature": sig(fn, node.name),
                                    "doc": ast.get_docstring(fn) or "", "section": section_at(fn.lineno),
                                    "line": fn.lineno, "file": f.name,
                                    "tools": tools_in(code_of(src, fn))})
    return out


def js_members(dts, impl):
    """index.d.ts has the signatures and the docs; index.js has the bodies,
    so the tools a method calls come from there."""
    bodies = {}
    src = [l if not re.match(r"\s*(?://|/\*|\*)", l) else "" for l in Path(impl).read_text().splitlines()]
    name, start = None, 0
    for n, l in enumerate(src):
        m = re.match(r"^  (?:async )?([a-z]\w*)\(", l) or re.match(r"^export (?:async )?function (\w+)\(", l)
        if m:
            if name:
                bodies.setdefault(name, "")
                bodies[name] += "\n".join(src[start:n])
            name, start = m.group(1), n
    if name:
        bodies[name] = bodies.get(name, "") + "\n".join(src[start:])

    out, doc, section, cls = [], [], "", ""
    in_block = False
    for n, l in enumerate(Path(dts).read_text().splitlines()):
        s = l.strip()
        if s.startswith("/**"):
            in_block, doc = True, []
        if in_block:
            doc.append(s)
            if s.endswith("*/"):
                in_block = False
            continue
        m = SECTION_RE.match(l)
        if m:
            section, doc = m.group(1), []
            continue
        m = re.match(r"^  // ([a-z][a-z ,]+)$", l)
        if m:
            section, doc = m.group(1), []
            continue
        m = re.match(r"^export (?:declare )?(class|interface|type|function) (\w+)", l)
        if m:
            kind = {"function": "func"}.get(m.group(1), "class")
            if kind == "class":
                cls = m.group(2)
            out.append({"kind": kind, "name": m.group(2), "owner": "", "signature": s.rstrip("{").strip(),
                        "doc": clean_doc(doc, "javadoc"), "section": section if kind == "func" else "",
                        "line": n + 1, "tools": tools_in(bodies.get(m.group(2), "")) if kind == "func" else []})
            doc = []
            continue
        m = re.match(r"^  (?:static )?([a-z]\w*)(\??)(\(|:)", l)
        if m and cls:
            kind = "method" if m.group(3) == "(" else "property"
            out.append({"kind": kind, "name": m.group(1), "owner": cls, "signature": s,
                        "doc": clean_doc(doc, "javadoc"), "section": section if cls == "Device" else "",
                        "line": n + 1, "tools": tools_in(bodies.get(m.group(1), "")) if cls == "Device" else []})
            doc = []
            continue
        if s and not s.startswith("//"):
            doc = []
    return out


def client_members(src):
    c = Path(src) / "clients"
    go = []
    for f in sorted((c / "go").glob("*.go")):
        if not f.name.endswith("_test.go"):
            go += [dict(m, file=f.name) for m in c_style(f, "go", "go")]
    java, cs = [], []
    for f in sorted((c / "java/src/main/java/dev/mobium").glob("*.java")):
        java += [dict(m, file=f.name) for m in c_style(f, "javadoc", "java")]
    for f in sorted((c / "dotnet/Mobium").glob("*.cs")):
        cs += [dict(m, file=f.name) for m in c_style(f, "xml", "cs")]
    return {
        "go": go,
        "python": python_members(c / "python/mobium"),
        "javascript": js_members(c / "javascript/index.d.ts", c / "javascript/index.js"),
        "java": java,
        "dotnet": cs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="a checkout of mobiumdev/mobium")
    ap.add_argument("--bin", required=True, help="mobium built from that checkout")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    src = Path(a.src).expanduser()
    commit = run("git", "-C", str(src), "rev-parse", "HEAD").strip()
    version = run(a.bin, "--version").strip()
    data = {
        "source": {"commit": commit, "version": version},
        "tools": mcp_tools(a.bin),
        "cli": cli_commands(a.bin),
        "surface": json.loads((src / "docs/api/surface.json").read_text()),
        "clients": client_members(src),
    }
    (DATA / "mobium.json").write_text(json.dumps(data, indent=1) + "\n")
    counts = {k: len(v) for k, v in data["clients"].items()}
    print(f"{len(data['tools'])} tools, {len(data['cli']['commands'])} commands, members {counts}, from {commit[:7]}")


if __name__ == "__main__":
    main()
