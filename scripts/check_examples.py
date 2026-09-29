#!/usr/bin/env python3
"""Hold every example on the site to the surface it is written for.

- canonical.json: each scenario's MCP arguments against the tool's schema,
  and its command against the CLI's own commands and flags.
- each client's examples: every tool has one per canonical scenario, and the
  code compiles or type-checks against that client, by its own toolchain.

    python3 scripts/check_examples.py --src ~/mobium-public [--lang go ...]

A language whose toolchain is missing fails, rather than passing unchecked.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
LANGS = ["python", "javascript", "go", "java", "dotnet"]


def load():
    data = json.loads((ROOT / "data/mobium.json").read_text())
    canon = {k: v for k, v in json.loads((EX / "canonical.json").read_text()).items() if not k.startswith("_")}
    return data, canon


# -- the schema ------------------------------------------------------------

TYPES = {"string": str, "boolean": bool, "integer": int, "number": (int, float), "array": list, "object": dict}


def validate(value, schema, where, errs):
    t = schema.get("type")
    if t and not isinstance(value, TYPES[t]) or (t in ("integer", "number") and isinstance(value, bool)):
        errs.append(f"{where}: {value!r} is not {t}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{where}: {value!r} not in {schema['enum']}")
    if t == "object" and "properties" in schema:
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{where}: missing required {k}")
        for k, v in value.items():
            if k not in schema["properties"]:
                if schema.get("additionalProperties") is False:
                    errs.append(f"{where}: {k} is not declared")
            else:
                validate(v, schema["properties"][k], f"{where}.{k}", errs)
    if t == "array" and "items" in schema:
        for i, v in enumerate(value):
            validate(v, schema["items"], f"{where}[{i}]", errs)


def check_canonical(data, canon):
    errs = []
    tools = {t["name"]: t for t in data["tools"]}
    surface = {t["tool"]: t for t in data["surface"]["tools"]}
    cmds = data["cli"]["commands"]
    for name in tools:
        if name not in canon:
            errs.append(f"{name}: no example")
    for name, scenarios in canon.items():
        if name not in tools:
            errs.append(f"{name}: not a tool")
            continue
        clis = [c.strip() for c in surface[name]["cli"].split(",")]
        for i, s in enumerate(scenarios):
            where = f"{name}[{i}]"
            validate(s["args"], tools[name]["inputSchema"], where + " args", errs)
            for part in re.split(r"\s*&&\s*", s["cli"]):
                words = shlex.split(part.split(" > ")[0])
                if words[0] != "mobium" or words[1] not in cmds:
                    errs.append(f"{where}: {part!r} is not a mobium command")
                    continue
                if words[1] not in clis:
                    errs.append(f"{where}: {words[1]} does not reach {name} (that is {clis})")
                known = {f["name"] for f in cmds[words[1]]["flags"] + cmds[words[1]]["global"]}
                shorts = {f["short"] for f in cmds[words[1]]["flags"] + cmds[words[1]]["global"] if f["short"]}
                for w in words[2:]:
                    if w.startswith("--") and w[2:].split("=")[0] not in known:
                        errs.append(f"{where}: {words[1]} has no flag {w}")
                    elif re.fullmatch(r"-[a-z]", w) and w[1] not in shorts:
                        errs.append(f"{where}: {words[1]} has no flag {w}")
    return errs


# -- the clients -----------------------------------------------------------


def client_examples(lang):
    p = EX / f"{lang}.json"
    return json.loads(p.read_text()) if p.exists() else None


def coverage(lang, canon, ex):
    errs = []
    if ex is None:
        return [f"{lang}: examples/{lang}.json is missing"]
    for name, scenarios in canon.items():
        got = ex.get("tools", {}).get(name, [])
        if len(got) != len(scenarios):
            errs.append(f"{lang} {name}: {len(got)} examples for {len(scenarios)} scenarios")
    for name in ex.get("tools", {}):
        if name not in canon:
            errs.append(f"{lang} {name}: not a tool")
    return errs


def snippets(ex):
    """Every snippet in a client's file, with a name to report it by."""
    out = []
    for name, items in ex.get("tools", {}).items():
        for i, s in enumerate(items):
            if s.get("code"):
                out.append((f"{name}[{i}]", s["code"]))
    for name, items in ex.get("members", {}).items():
        for i, s in enumerate(items):
            out.append((f"{name}[{i}]", s["code"]))
    if ex.get("intro"):
        # The client's index page: it makes its own device.
        out.append(("intro[0]", ex["intro"]["code"]))
    return out


def need(tool):
    if not shutil.which(tool):
        raise SystemExit(f"{tool} is not on PATH, so these examples cannot be checked")


def compile_python(src, snips):
    """Each snippet runs against an autospec of the real Device, which refuses
    a method that does not exist and a call its signature does not bind.

    Snippets run in a scratch directory with their output discarded, so one
    that saves a file or prints leaves nothing behind and reports nothing.
    `session` is an instance attribute, invisible to an autospec of the class,
    so the spec carries one; and a method annotated as returning a dict
    returns a real one, so a snippet can json.dump it."""
    prog = f"""
import sys, inspect, io, os, tempfile, typing, contextlib, collections
from unittest import mock
sys.path.insert(0, {str(Path(src) / 'clients/python')!r})
import mobium
os.chdir(tempfile.mkdtemp())
class Spec(mobium.Device):
    session = mobium.Session(device='', platform='', driver='')
dict_returns = []
for n, f in inspect.getmembers(mobium.Device, inspect.isfunction):
    try:
        r = typing.get_type_hints(f).get('return')
    except Exception:
        continue
    if (typing.get_origin(r) or r) is dict:
        dict_returns.append(n)
failed = 0
for name, code in {snips!r}:
    device = mock.create_autospec(Spec, instance=True, spec_set=True)
    for n in dict_returns:
        getattr(device, n).return_value = collections.defaultdict(mock.MagicMock)
    env = {{'device': device, 'mobium': mobium}}
    with mock.patch.object(mobium, 'start', mock.create_autospec(mobium.start, return_value=device)), \\
         mock.patch.object(mobium, 'connect', mock.create_autospec(mobium.connect, return_value=device)):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(code, name, 'exec'), env)
        except Exception as e:
            failed += 1
            print(f'{{name}}: {{type(e).__name__}}: {{e}}')
sys.exit(1 if failed else 0)
"""
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True)
    return [l for l in (r.stdout + r.stderr).splitlines() if l.strip()] if r.returncode else []


def compile_javascript(src, snips):
    """Each snippet is its own module, type-checked with tsc --strict against
    the client's index.d.ts, installed as the package `mobium` so a snippet
    can `import { start } from 'mobium'` as a user would. Its import lines are
    hoisted to the top of the module; the rest runs in an async function body
    with `device: Device` in scope (unless the snippet declares its own
    `device`), and `mobium` bound to the namespace unless it imports it."""
    need("npx")
    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d, "node_modules/mobium")
        pkg.mkdir(parents=True)
        pkg.joinpath("index.d.ts").write_text((Path(src) / "clients/javascript/index.d.ts").read_text())
        pkg.joinpath("package.json").write_text(json.dumps({"name": "mobium", "type": "module", "types": "index.d.ts"}))
        types = ROOT / "node_modules/@types"
        if not (types / "node").is_dir():
            r = subprocess.run(["npm", "install", "--no-save", "--silent", "--prefix", d, "@types/node"],
                               capture_output=True, text=True)
            if r.returncode:
                return [f"could not install @types/node: {r.stderr.strip()}"]
            types = Path(d, "node_modules/@types")
        where, files = {}, []
        is_import = re.compile(r"\s*import\s")
        for n, (name, code) in enumerate(snips):
            lines = code.splitlines()
            imports = [l for l in lines if is_import.match(l)]
            rest = [l for l in lines if not is_import.match(l)]
            head = imports + ['import type { Device as __Device } from "mobium"']
            if not re.search(r"\bas\s+mobium\b|\bimport\s+mobium\b", "\n".join(imports)):
                head.append('import * as mobium from "mobium"; void mobium')
            param = "" if re.search(r"\b(const|let|var)\s+device\b", code) else "device: __Device"
            head += ["export {}", f"export async function example({param}) {{"]
            where[f"ex{n}.ts"] = (name, len(head), rest)
            Path(d, f"ex{n}.ts").write_text("\n".join(head + rest + ["}"]) + "\n")
            files.append(f"ex{n}.ts")
        Path(d, "tsconfig.json").write_text(json.dumps({"compilerOptions": {
            "noEmit": True, "strict": True, "target": "es2022", "module": "es2022", "moduleResolution": "bundler",
            "types": ["node"], "typeRoots": [str(types)], "skipLibCheck": True}, "files": files}))
        r = subprocess.run(["npx", "-y", "-p", "typescript@5", "tsc", "-p", "tsconfig.json", "--pretty", "false"],
                           cwd=d, capture_output=True, text=True)
        if not r.returncode:
            return []
        out = []
        for l in (r.stdout + r.stderr).splitlines():
            m = re.match(r"(ex\d+\.ts)\((\d+),\d+\): (.*)", l)
            if m:
                # Name the snippet and quote the line of it that failed.
                name, nhead, rest = where[m.group(1)]
                i = int(m.group(2)) - 1 - nhead
                quoted = rest[i].strip() if 0 <= i < len(rest) else "(imports)"
                out.append(f"{name}: {m.group(3)}  [{quoted}]")
            elif l.startswith(" ") and out:
                out[-1] += " " + l.strip()
            elif l.strip():
                out.append(l)
        return out or ["tsc failed with no output"]


def name_errors(r, snips, fname):
    return [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]


def compile_go(src, snips):
    need("go")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "go.mod").write_text(
            "module examples\n\ngo 1.24\n\nrequire github.com/mobiumdev/mobium/clients/go v0.0.0\n\n"
            f"replace github.com/mobiumdev/mobium/clients/go => {Path(src) / 'clients/go'}\n")
        # time and os too: the client takes time.Duration (WaitOptions.Timeout,
        # LongPress, DragFor), and a snippet that saves a file needs os.
        body = ["package examples", "", "import (", '\t"context"', '\t"errors"', '\t"fmt"', '\t"log"',
                '\t"os"', '\t"time"', "", '\t"github.com/mobiumdev/mobium/clients/go"', ")", "",
                "var _ = errors.Is", "var _ = fmt.Println", "var _ = log.Fatal", "var _ = os.WriteFile",
                "var _ = time.Second", ""]
        # Which snippet each line of examples.go belongs to, so a compiler
        # message names the snippet rather than a line in a temporary file.
        owner = {}
        for n, (name, code) in enumerate(snips):
            chunk = f"// {name}\nfunc ex{n}(ctx context.Context, dev *mobium.Device) error {{\n{code}\n\treturn nil\n}}\n"
            start = sum(b.count("\n") + 1 for b in body) + 1
            for i in range(chunk.count("\n") + 1):
                owner[start + i] = (name, i - 1)
            body.append(chunk)
        Path(d, "examples.go").write_text("\n".join(body))
        env = dict(os.environ, GOFLAGS="-mod=mod", GOWORK="off")
        # Build with -e first, which reports every error rather than the first
        # ten; vet then adds its own checks on code that compiles.
        r = subprocess.run(["go", "build", "-gcflags=-e", "./..."], cwd=d, capture_output=True, text=True, env=env)
        if not r.returncode:
            r = subprocess.run(["go", "vet", "./..."], cwd=d, capture_output=True, text=True, env=env)
        if not r.returncode:
            return []
        out = []
        for l in (r.stdout + r.stderr).splitlines():
            m = re.search(r"examples\.go:(\d+):(?:\d+:)?\s*(.*)", l)
            if m and int(m.group(1)) in owner:
                name, line = owner[int(m.group(1))]
                out.append(f"{name} (snippet line {line}): {m.group(2)}")
            elif l.strip() and not l.startswith("#"):
                out.append(l)
        return out


def compile_java(src, snips):
    need("javac")
    with tempfile.TemporaryDirectory() as d:
        # java.time too: Duration is how the client takes every timeout.
        body = ["import dev.mobium.*;", "import java.util.*;", "import java.nio.file.*;", "import java.time.*;",
                "", "class Examples {"]
        starts = []  # (line of the snippet's "// name" comment, its name), to name the snippet in each error
        for n, (name, code) in enumerate(snips):
            starts.append((1 + sum(b.count("\n") + 1 for b in body), name))
            body.append(f"  // {name}\n  static void ex{n}(Mobium {'unused' if name == 'intro[0]' else 'device'}) throws Exception {{\n{code}\n  }}")
        body.append("}")
        Path(d, "Examples.java").write_text("\n".join(body) + "\n")
        r = subprocess.run(["javac", "-d", d, "-sourcepath", str(Path(src) / "clients/java/src/main/java"),
                            "-Xlint:none", str(Path(d, "Examples.java"))], capture_output=True, text=True)
        if not r.returncode:
            return []
        out = []
        for l in (r.stdout + r.stderr).splitlines():
            m = re.match(r".*Examples\.java:(\d+): (.*)", l)
            if m:
                line = int(m.group(1))
                hit = [(s, nm) for s, nm in starts if s <= line]
                if hit:
                    s, nm = hit[-1]
                    l = f"{nm} line {line - s - 1}: {m.group(2)}"
            if l.strip():
                out.append(l)
        return out


def compile_dotnet(src, snips):
    """Builds every snippet against a copy of the client, so the build writes
    nothing into the source tree. Errors and warnings in the snippets are
    reported by snippet name; the nullable warnings stay on, because
    dereferencing what WaitFor or ScrollTo can return as null is a misuse."""
    dotnet = os.environ.get("DOTNET", "dotnet")
    if not shutil.which(dotnet):
        raise SystemExit("dotnet is not on PATH (or DOTNET), so the .NET examples cannot be checked")
    with tempfile.TemporaryDirectory() as d:
        lib = Path(d, "Mobium")
        lib.mkdir()
        client = Path(src) / "clients/dotnet/Mobium"
        for f in [client / "Mobium.csproj", *client.glob("*.cs")]:
            shutil.copy(f, lib / f.name)
        # Unused locals and uncalled wrappers are the nature of a snippet.
        Path(d, "Examples.csproj").write_text(f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable>
  <OutputType>Library</OutputType><NoWarn>CS1998;CS8321;CS0168;CS0219</NoWarn>
  <DefaultItemExcludes>$(DefaultItemExcludes);Mobium/**</DefaultItemExcludes></PropertyGroup>
  <ItemGroup><ProjectReference Include="{lib / 'Mobium.csproj'}" /></ItemGroup>
</Project>
""")
        body = ["using System;", "using System.Collections.Generic;", "using System.IO;", "using System.Linq;",
                "using Mobium;", "", "static class Examples {"]
        where = []  # (first line, last line, name), 1-based, of each snippet's body
        for n, (name, code) in enumerate(snips):
            body.append(f"  // {name}\n  static void Ex{n}(Device {'unused' if name == 'intro[0]' else 'device'}) {{")
            first = sum(b.count("\n") + 1 for b in body) + 1
            body.append(code)
            where.append((first, first + code.count("\n"), name))
            body.append("  }")
        body.append("}")
        Path(d, "Examples.cs").write_text("\n".join(body) + "\n")
        r = subprocess.run([dotnet, "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=d,
                           capture_output=True, text=True)
        out, seen = [], set()
        for l in (r.stdout + r.stderr).splitlines():
            m = re.search(r"Examples\.cs\((\d+),(\d+)\): (error|warning) (\w+): (.*?)(?: \[[^\]]*\])?$", l)
            if m:
                line = int(m[1])
                name = next((nm for a, b, nm in where if a <= line <= b), f"Examples.cs:{line}")
                msg = f"{name} line {line - next((a for a, b, nm in where if nm == name), line) + 1}: {m[3]} {m[4]}: {m[5]}"
            elif r.returncode and re.search(r"\berror\b", l):
                msg = l.strip()
            else:
                continue
            if msg not in seen:
                seen.add(msg)
                out.append(msg)
        if r.returncode and not out:
            out.append(f"dotnet build failed with no error line: {(r.stdout + r.stderr).strip()[-500:]}")
        return out


COMPILERS = {"python": compile_python, "javascript": compile_javascript, "go": compile_go,
             "java": compile_java, "dotnet": compile_dotnet}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.environ.get("MOBIUM_SRC", "../mobium"))
    ap.add_argument("--lang", action="append", choices=LANGS)
    a = ap.parse_args()
    # Absolute: go.mod's replace and javac's sourcepath are read from a
    # temporary directory, where a relative path means something else.
    a.src = str(Path(a.src).expanduser().resolve())
    data, canon = load()
    errs = check_canonical(data, canon)
    print(f"canonical: {sum(len(v) for v in canon.values())} scenarios, {len(errs)} problems")
    for lang in a.lang or LANGS:
        ex = client_examples(lang)
        e = coverage(lang, canon, ex)
        if ex is not None:
            snips = snippets(ex)
            e += [f"{lang}: {l}" for l in COMPILERS[lang](a.src, snips)]
            print(f"{lang}: {len(snips)} snippets, {len(e)} problems")
        errs += e
    for e in errs:
        print("  " + e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
