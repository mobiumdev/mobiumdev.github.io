#!/usr/bin/env python3
"""Write the site's pages from what the source says.

- docs/reference/: a page per command, per MCP tool, and per tool in each
  client, from data/mobium.json (scripts/extract.py), with the examples in
  examples/ (scripts/check_examples.py) and what the emulator printed and
  showed in data/runs.json (scripts/capture.py).
- docs/quickstart/ and docs/guides/: copied from the Mobium repository, with
  their links pointed at the site or at GitHub.

    python3 scripts/generate.py --src ~/mobium-public
"""

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REF = DOCS / "reference"
REPO = "https://github.com/mobiumdev/mobium"

SURFACES = [
    # key, label, directory, code fence
    ("cli", "CLI", "cli", "sh"),
    ("mcp", "MCP", "mcp", "json"),
    ("python", "Python", "python", "python"),
    ("javascript", "JavaScript", "javascript", "js"),
    ("go", "Go", "go", "go"),
    ("java", "Java", "java", "java"),
    ("dotnet", ".NET", "dotnet", "csharp"),
]
LABEL = {k: l for k, l, _, _ in SURFACES}
FENCE = {k: f for k, _, _, f in SURFACES}
CLIENTS = ["python", "javascript", "go", "java", "dotnet"]

CODE_FENCE = {"python": "python", "javascript": "js", "go": "go", "java": "java", "dotnet": "csharp"}


def slug(tool):
    return tool.removeprefix("app_").replace("_", "-")


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def fm(**kv):
    out = ["---"]
    for k, v in kv.items():
        out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(out + ["---", ""])


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def category(path, label, position, description=None):
    c = {"label": label, "position": position, "link": {"type": "doc", "id": None}}
    del c["link"]
    if description:
        c["link"] = {"type": "generated-index", "description": description}
    write(path / "_category_.json", json.dumps(c, indent=2))


class Site:
    def __init__(self, data, canon, examples, runs):
        self.data = data
        self.tools = {t["name"]: t for t in data["tools"]}
        self.surface = {t["tool"]: t for t in data["surface"]["tools"]}
        self.cli = data["cli"]["commands"]
        self.canon = canon
        self.ex = examples
        self.runs = runs
        self.members = data["clients"]
        # command -> tool
        self.cmd_tool = {}
        for tool, s in self.surface.items():
            for c in s["cli"].split(","):
                self.cmd_tool[c.strip()] = tool

    # -- shared pieces ------------------------------------------------------

    def elsewhere(self, tool, here):
        links = []
        for k, label, d, _ in SURFACES:
            if k == "cli":
                target = f"/reference/cli/{self.surface[tool]['cli'].split(',')[0].strip()}"
            else:
                target = f"/reference/{d}/{slug(tool)}"
            links.append(f"**{label}**" if k == here else f"[{label}]({target})")
        return "This tool on every surface: " + " · ".join(links) + "\n"

    def run_for(self, tool, i):
        r = self.runs.get(f"{tool}[{i}]")
        if r and r.get("verbatim") and r["command"] == self.canon[tool][i]["cli"]:
            return r
        return None

    def pictures(self, tool, i):
        """Before and after, from the run of this scenario."""
        r = self.runs.get(f"{tool}[{i}]")
        if not r or r["command"] != self.canon[tool][i]["cli"]:
            return ""
        return self.figure(r)

    def figure(self, r, caption=None):
        shots = [(k, r[k]) for k in ("before", "after") if r.get(k)]
        if not shots:
            return ""
        cap = caption or f"`{r['command']}` on an Android 15 emulator"
        alt = cap.replace("`", "")
        if len(shots) == 1:
            return f"\n![{cell(alt)}]({shots[0][1]})\n\n*{cap}*\n"
        return (f"\n| Before | After |\n| --- | --- |\n| ![Before: {cell(alt)}]({shots[0][1]}) | "
                f"![After: {cell(alt)}]({shots[1][1]}) |\n\n*{cap}*\n")

    def other_pictures(self, tool):
        out = []
        for key, r in self.runs.items():
            if r["tool"] == tool and r.get("index") is None:
                out.append(self.figure(r, f"`{r['command']}` on an Android 15 emulator"))
        return "".join(out)

    # -- CLI -----------------------------------------------------------------

    def cli_pages(self):
        base = REF / "cli"
        category(base, "CLI", 2)
        root = self.data["cli"]["root"]
        rows = []
        for name in sorted(self.cli):
            h = self.cli[name]
            if " " in name:
                continue
            rows.append(f"| [`mobium {name}`](/reference/cli/{name.replace(' ', '-')}) | {cell(h.get('short') or h['description'].splitlines()[0])} |")
        glob = "\n".join(f"| `--{f['name']}`{' `-' + f['short'] + '`' if f['short'] else ''} | {f['type']} | {cell(f['description'])} |"
                         for f in root["global"])
        write(base / "index.md", fm(title="CLI", sidebar_position=0, slug="/reference/cli") + f"""
# The command line

`mobium` is one binary. Every command below is a tool of the same layer an
MCP client and the five client libraries call, so a command and a method
cannot answer differently — the command's page links the same tool on every
other surface.

```
{root['description']}
```

## Global flags

Every command takes these.

| Flag | Type | What it does |
| --- | --- | --- |
{glob}

`--json` prints the tool's structured answer. A command that fails prints
`error: …` on stderr and exits with the status of its error's code: 2
`invalid_argument`; 3 `no_device`, `device_not_ready`, `toolchain_missing`; 4
`no_such_element`, `ambiguous_locator`, `element_not_reachable`,
`no_such_context`, `no_such_alert`; 5 `unsupported`; 6 `timeout`; 7
`not_confirmed`; 1 anything else.

## Commands

| Command | What it does |
| --- | --- |
""" + "\n".join(rows) + "\n")
        extra = json.loads((ROOT / "examples/cli-extra.json").read_text())
        self.no_picture = json.loads((ROOT / "examples/no-picture.json").read_text())
        for name, h in self.cli.items():
            self.cli_page(base, name, h, extra.get(name, []))

    def cli_page(self, base, name, h, extra):
        tool = self.cmd_tool.get(name)
        desc = h["description"]
        first = h.get("short") or desc.partition("\n")[0]
        rest = desc if desc.strip() != first.strip() else ""
        out = [fm(title=f"mobium {name}", sidebar_label=name, sidebar_position=sorted(self.cli).index(name) + 1,
                  description=first), f"# `mobium {name}`\n"]
        if tool:
            out.append(self.elsewhere(tool, "cli"))
        out.append(first + "\n")
        if rest.strip():
            out.append(rest.strip() + "\n")
        out.append("## Usage\n\n```sh\n" + "\n".join(h["usage"]) + "\n```\n")
        if h["aliases"]:
            out.append(f"Aliases: `{h['aliases']}`\n")
        if h["commands"]:
            subs = [c for c in h["commands"] if f"{name} {c}" in self.cli]
            out.append("## Subcommands\n\n" + "\n".join(
                f"- [`mobium {name} {c}`](/reference/cli/{name.replace(' ', '-')}-{c}) — {self.cli[f'{name} {c}'].get('short')}"
                for c in subs) + "\n")
        if h["flags"]:
            out.append("## Flags\n\n| Flag | Type | Default | What it does |\n| --- | --- | --- | --- |\n" + "\n".join(
                f"| `--{f['name']}`{' `-' + f['short'] + '`' if f['short'] else ''} | {f['type']} | {'`' + f['default'] + '`' if f['default'] else ''} | {cell(f['description'])} |"
                for f in h["flags"]) + "\n\nAnd the [global flags](/reference/cli#global-flags).\n")
        out.append("## Examples\n")
        n = 0
        if tool:
            for i, s in enumerate(self.canon[tool]):
                if not s["cli"].startswith(f"mobium {name}"):
                    continue
                n += 1
                out.append(f"### {s['title']}\n\n```sh\n{s['cli']}\n```\n")
                r = self.run_for(tool, i)
                if r:
                    status = "" if r["exit"] == 0 else f" It exited {r['exit']}."
                    out.append(f"Printed on an Android 15 emulator:{status}\n\n```text\n{r['output']}\n```\n")
                out.append(self.pictures(tool, i))
        for e in extra:
            n += 1
            out.append(f"### {e['title']}\n\n```sh\n{e['cli']}\n```\n")
            if e.get("image"):
                alt = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", e["caption"]).replace("`", "")
                out.append(f"\n![{cell(alt)}]({e['image']})\n\n*{e['caption']}*\n")
        if h["examples"]:
            out.append(("### More, from `mobium " + name + " --help`\n\n" if n else "") + "```sh\n" + h["examples"] + "\n```\n")
        elif not n:
            raise SystemExit(f"mobium {name} has no example: add one to examples/cli-extra.json")
        pics = self.other_pictures(tool) if tool else ""
        if pics:
            out.append("## On a device\n" + pics)
        if not pics and not any(o.lstrip().startswith("![") or "\n![" in o or "| ![" in o for o in out):
            why = self.no_picture.get(name.replace(" ", "-"))
            if not why:
                raise SystemExit(f"mobium {name} has no picture and no reason in examples/no-picture.json")
            out.append(f"*No screenshot: {why}*\n")
        if tool:
            out.append(f"## The tool\n\n`{name}` calls [`{tool}`](/reference/mcp/{slug(tool)}); "
                       "its arguments and what every client calls it are there.\n")
        write(base / f"{name.replace(' ', '-')}.md", "\n".join(out))

    # -- MCP -----------------------------------------------------------------

    def mcp_pages(self):
        base = REF / "mcp"
        category(base, "MCP", 3)
        rows = "\n".join(
            f"| [`{t}`](/reference/mcp/{slug(t)}) | {'yes' if self.tools[t].get('annotations', {}).get('readOnlyHint') else ''} | {cell(self.tools[t]['description'].split('. ')[0].rstrip('.'))}. |"
            for t in sorted(self.tools))
        write(base / "index.md", fm(title="MCP", sidebar_position=0, slug="/reference/mcp") + f"""
# The MCP server

`mobium mcp` is an MCP server on stdio with {len(self.tools)} tools. Add it to
a client's configuration — Claude Code, for one:

```sh
claude mcp add mobium -- mobium mcp
```

Or, in any client that reads a JSON configuration:

```json
{{
  "mcpServers": {{
    "mobium": {{ "command": "mobium", "args": ["mcp"] }}
  }}
}}
```

Every tool takes `device` (a serial, when more than one is running) and
`driver` besides its own arguments, and every schema is
`additionalProperties: false`: an argument a tool does not declare is refused,
not ignored. A tool that fails answers with `isError` and a
`structuredContent` carrying its error's `code`, `remedy`, `retryable` and
`details` — never a JSON-RPC error. Read-only tools say so with
`readOnlyHint`. [The MCP guide](/guides/mcp) walks through a session.

## Tools

| Tool | Read-only | What it does |
| --- | --- | --- |
{rows}
""")
        for name in self.tools:
            self.mcp_page(base, name)

    def mcp_page(self, base, name):
        t = self.tools[name]
        props = t["inputSchema"].get("properties", {})
        req = t["inputSchema"].get("required", [])
        ro = t.get("annotations", {}).get("readOnlyHint")
        out = [fm(title=name, sidebar_position=sorted(self.tools).index(name) + 1,
                  description=t["description"].split(". ")[0]), f"# `{name}`\n", self.elsewhere(name, "mcp"),
               t["description"] + "\n",
               f"{'Read-only' if ro else 'Changes the device, the app or the session'}: `readOnlyHint` is `{str(bool(ro)).lower()}`.\n"]
        rows = []
        for k, v in props.items():
            typ = v.get("type", "any")
            if "enum" in v:
                typ += ": " + ", ".join(f"`{e}`" for e in v["enum"])
            if typ.startswith("array") and isinstance(v.get("items"), dict) and v["items"].get("type"):
                typ = f"array of {v['items']['type']}"
            d = v.get("description", "")
            if "default" in v:
                d += f" Default `{json.dumps(v['default'])}`."
            rows.append(f"| `{k}` | {cell(typ)} | {'yes' if k in req else ''} | {cell(d)} |")
        out.append("## Arguments\n\n| Name | Type | Required | What it is |\n| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n")
        out.append("## Examples\n\nEach is the `arguments` of a `tools/call` request; the first is shown whole.\n")
        for i, s in enumerate(self.canon[name]):
            if i == 0:
                req_json = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": name, "arguments": s["args"]}}, indent=2, ensure_ascii=False)
            else:
                req_json = json.dumps(s["args"], indent=2, ensure_ascii=False)
            out.append(f"### {s['title']}\n\n```json\n{req_json}\n```\n")
            r = self.run_for(name, i)
            if r and r["exit"] == 0:
                out.append(f"On an Android 15 emulator the answer's text was:\n\n```text\n{r['output']}\n```\n")
            out.append(self.pictures(name, i))
        pics = self.other_pictures(name)
        if pics:
            out.append("## On a device\n" + pics)
        write(base / f"{slug(name)}.md", "\n".join(out))

    # -- clients -------------------------------------------------------------

    def client_pages(self, lang):
        base = REF / lang
        pos = {"python": 4, "javascript": 5, "go": 6, "java": 7, "dotnet": 8}[lang]
        category(base, LABEL[lang], pos)
        ex = self.ex[lang]
        members = self.members[lang]
        by_tool = {}
        for m in members:
            if m["kind"] in ("method", "func"):
                for t in m["tools"]:
                    by_tool.setdefault(t, []).append(m)
        fence = CODE_FENCE[lang]
        # The index: install, connect, the members that call no tool, the types.
        intro = ex["intro"]
        install, hello, conv = intro["install"], intro["code"], intro["note"]
        ifence = "python" if install.startswith("pip") else "sh"
        # A member that calls a tool is shown on that tool's page instead.
        # Starting and ending a session stay here too: they are how every
        # script begins and ends.
        calls = {m["name"] for m in members if m["tools"] and m["tools"] != ["app_session"]}
        rows = []
        for tool in sorted(self.tools):
            names = sorted({m["name"] for m in by_tool.get(tool, []) if m["owner"] in ("", "Device", "Mobium")})
            rows.append(f"| [{', '.join(f'`{n}`' for n in names) or '—'}](/reference/{lang}/{slug(tool)}) | `{tool}` |")
        general = []
        for name, items in ex.get("members", {}).items():
            if name in calls:
                continue
            ms = [m for m in members if m["name"] == name]
            general.append(f"### `{name}`\n")
            for m in ms[:3]:
                general.append(f"```{fence}\n{m['signature']}\n```\n")
            if ms and ms[0]["doc"]:
                general.append(doc_text(ms[0]["doc"], lang) + "\n")
            for it in items:
                general.append(f"**{it.get('title', 'Example')}**\n\n```{fence}\n{it['code']}\n```\n")
        types = [m for m in members if m["kind"] in ("class", "type") and not m["name"].startswith("_")]
        tlist = "\n".join(f"| `{m['name']}` | {cell(first_sentence(m['doc']))} |" for m in types
                          if m["name"] not in ("Connection", "Json", "Parser"))
        write(base / "index.md", fm(title=LABEL[lang], sidebar_position=0, slug=f"/reference/{lang}") + f"""
# The {LABEL[lang]} client

It speaks to the same tool layer as the CLI and the MCP server, by spawning
`mobium pipe`, so the `mobium` binary has to be on `PATH` or named by
`MOBIUM_BIN_PATH`. The [quick start](/quickstart/{lang}) goes from nothing to a
running script.

## Install

```sh
{install}
```

## Connect

```{fence}
{hello}
```

{conv}

## Every tool, by method

| Method | Tool |
| --- | --- |
{chr(10).join(rows)}

## Connecting, ending, and errors

{chr(10).join(general)}

## Types

| Type | What it is |
| --- | --- |
{tlist}
""")
        # The sidebar sorts by the name a reader sees, the method's.
        first = {t: sorted({m["name"] for m in by_tool.get(t, []) if m["owner"] in ("", "Device", "Mobium", "DeviceBuilder", "Builder")},
                           key=lambda n: [m["line"] for m in by_tool[t] if m["name"] == n][0])[:1] or [t] for t in self.tools}
        self.order = getattr(self, "order", {})
        self.order[lang] = {t: i + 1 for i, t in enumerate(sorted(self.tools, key=lambda t: first[t][0].lower()))}
        for tool in self.tools:
            self.client_page(base, lang, tool, by_tool.get(tool, []))

    def client_page(self, base, lang, tool, ms):
        fence = CODE_FENCE[lang]
        ms = [m for m in ms if m["owner"] in ("", "Device", "Mobium", "DeviceBuilder", "Builder")]
        names = []
        for m in ms:
            if m["name"] not in names:
                names.append(m["name"])
        title = " · ".join(names) or tool
        out = [fm(title=title, sidebar_label=names[0] if names else tool, sidebar_position=self.order[lang].get(tool, 999),
                  description=f"{LABEL[lang]}: {first_sentence(self.tools[tool]['description'])}"),
               f"# {' · '.join(f'`{n}`' for n in names) or tool}\n", self.elsewhere(tool, lang),
               first_sentence(self.tools[tool]["description"]) + f" These call [`{tool}`](/reference/mcp/{slug(tool)}).\n"]
        for name in names:
            group = [m for m in ms if m["name"] == name]
            out.append(f"## `{name}`\n")
            out.append(f"```{fence}\n" + "\n".join(m["signature"] for m in group) + "\n```\n")
            docs = []
            for m in group:
                d = doc_text(m["doc"], lang)
                if d and d not in docs:
                    docs.append(d)
            out.append("\n\n".join(docs) + "\n")
        out.append("## Examples\n")
        for i, s in enumerate(self.canon[tool]):
            e = self.ex[lang]["tools"][tool][i]
            out.append(f"### {s['title']}\n")
            if e.get("code"):
                out.append(f"```{fence}\n{e['code']}\n```\n")
            else:
                out.append(f":::note\n\nNot in this client: {e['unsupported']}\n\n:::\n")
            out.append(self.pictures(tool, i))
        more = [(n, it) for n, items in self.ex[lang].get("members", {}).items() if n in names
                for it in items]
        if more:
            out.append("## More examples\n")
            for n, it in more:
                out.append(f"### {it.get('title', n)}\n\n```{fence}\n{it['code']}\n```\n")
        pics = self.other_pictures(tool)
        if pics:
            out.append("## On a device\n" + pics)
        write(base / f"{slug(tool)}.md", "\n".join(out))

    # -- the overview --------------------------------------------------------

    def overview(self):
        rows = []
        for tool in sorted(self.tools):
            s = self.surface[tool]
            cmd = s["cli"].split(",")[0].strip()
            cells = [f"[`{cmd}`](/reference/cli/{cmd})", f"[`{tool}`](/reference/mcp/{slug(tool)})"]
            for lang in CLIENTS:
                cells.append(f"[`{s['clients'].get(lang, '—')}`](/reference/{lang}/{slug(tool)})")
            rows.append("| " + " | ".join(cells) + " |")
        src = self.data["source"]
        write(REF / "index.md", fm(title="Reference", sidebar_position=0, slug="/reference") + f"""
# Reference

One tool layer, seven front doors. A command, an MCP tool and a client method
with the same row below are the same code: the CLI parses flags and calls the
tool by name, the MCP server hands the tool to an agent, and each client
speaks to it through `mobium pipe`. So a command and a method cannot answer
differently, and each page links the same tool on every other surface.

Every page here is generated from the Mobium source — the commands' own
help, the MCP server's `tools/list`, and each client's doc comments — at
[`{src['commit'][:7]}`]({REPO}/commit/{src['commit']}) (`{src['version']}`).
Every example is checked: the MCP arguments against the tool's schema, the
commands against their flags, and each client's code by compiling or
type-checking it against that client. The output under a command is what it
printed on an Android 15 emulator, and the screenshots are from the same
runs.

| CLI | MCP | Python | JavaScript | Go | Java | .NET |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(rows)}
""")
        category(REF, "Reference", 3)


def first_sentence(doc):
    doc = " ".join(doc.split())
    m = re.match(r"(.+?[.!?])(\s|$)", doc)
    return m.group(1) if m else doc


def doc_text(doc, lang):
    """A doc comment as Markdown. Go's and Python's indented blocks are code."""
    if not doc:
        return ""
    if lang in ("go", "python"):
        out, block = [], []
        for line in doc.splitlines():
            if line.startswith(("    ", "\t")) and (block or not out or out[-1] == ""):
                block.append(line[4:] if line.startswith("    ") else line[1:])
                continue
            if block and line.strip():
                out += ["```" + CODE_FENCE[lang]] + block + ["```", ""]
                block = []
            elif block:
                block.append("")
                continue
            out.append(line)
        if block:
            while block and not block[-1].strip():
                block.pop()
            out += ["```" + CODE_FENCE[lang]] + block + ["```"]
        return "\n".join(out).strip()
    return doc.strip()


# -- the synced pages --------------------------------------------------------

SYNC = {
    "quickstart": ["README.md", "cli.md", "python.md", "javascript.md", "go.md", "java.md", "dotnet.md"],
    "guides": ["README.md", "autowait.md", "test-runner.md", "grid.md", "network.md", "cli.md", "mcp.md"],
}
POSITION = {"README.md": 0, "cli.md": 1, "python.md": 2, "javascript.md": 3, "go.md": 4, "java.md": 5, "dotnet.md": 6,
            "autowait.md": 1, "test-runner.md": 2, "grid.md": 3, "network.md": 4, "mcp.md": 6}


def sync(src):
    for section, files in SYNC.items():
        out = DOCS / section
        if out.exists():
            shutil.rmtree(out)
        img = ROOT / "static/img" / section
        if img.exists():
            shutil.rmtree(img)
        for f in files:
            text = (src / "docs" / section / f).read_text()
            text = rewrite(text, section, src)
            text = re.sub(r"\n## Contents\n\n(?:- .*\n)+", "\n", text)
            text = re.sub(r"<!-- Generated by.*?-->\n", "", text)
            name = "index.md" if f == "README.md" else f
            extra = {"slug": f"/{section}"} if f == "README.md" else {}
            label = {"README.md": "Overview"}.get(f)
            head = fm(sidebar_position=POSITION[f], **({"sidebar_label": label} if label else {}), **extra)
            write(out / name, head + text)
        category(out, {"quickstart": "Quick start", "guides": "Guides"}[section],
                 {"quickstart": 1, "guides": 2}[section])


def rewrite(text, section, src):
    def link(m):
        label, target = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#)", target):
            return m.group(0)
        path, _, anchor = target.partition("#")
        anchor = "#" + anchor if anchor else ""
        full = (src / "docs" / section / path).resolve()
        rel = full.relative_to(src.resolve()) if str(full).startswith(str(src.resolve())) else None
        if rel is None:
            return m.group(0)
        parts = rel.parts
        # A page this site carries.
        if len(parts) == 3 and parts[0] == "docs" and parts[1] in SYNC and parts[2] in SYNC[parts[1]]:
            page = "" if parts[2] == "README.md" else parts[2][:-3]
            return f"[{label}](/{parts[1]}{'/' + page if page else ''}{anchor})"
        # An image: copied beside the site's static files.
        if full.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".svg"):
            dest = ROOT / "static/img" / section / full.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(full, dest)
            return f"[{label}](/img/{section}/{full.name})"
        kind = "tree" if full.is_dir() else "blob"
        return f"[{label}]({REPO}/{kind}/main/{rel}{anchor})"

    return re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", link, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    a = ap.parse_args()
    src = Path(a.src).expanduser()
    data = json.loads((ROOT / "data/mobium.json").read_text())
    canon = {k: v for k, v in json.loads((ROOT / "examples/canonical.json").read_text()).items() if not k.startswith("_")}
    examples = {l: json.loads((ROOT / f"examples/{l}.json").read_text()) for l in CLIENTS}
    runs = json.loads((ROOT / "data/runs.json").read_text()) if (ROOT / "data/runs.json").exists() else {}
    if REF.exists():
        shutil.rmtree(REF)
    site = Site(data, canon, examples, runs)
    site.overview()
    site.cli_pages()
    site.mcp_pages()
    for lang in CLIENTS:
        site.client_pages(lang)
    sync(src)
    pages = len(list(REF.rglob("*.md")))
    print(f"{pages} reference pages, and the quick start and guides from {data['source']['commit'][:7]}")


if __name__ == "__main__":
    main()
