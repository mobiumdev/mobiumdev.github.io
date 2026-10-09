# mobiumdev.github.io

The documentation site for [Mobium](https://github.com/mobiumdev/mobium),
published at **https://mobiumdev.github.io/**. Built with
[Docusaurus](https://docusaurus.io/).

## What is written here, and what is generated

| | Where it comes from |
| --- | --- |
| `docs/intro.md` | written here |
| `docs/quickstart/`, `docs/guides/` | copied from the Mobium repository's `docs/`, links pointed at this site or at GitHub |
| `docs/reference/` | generated: a page per command, per MCP tool, and per tool in each of the five clients |
| `examples/` | written here: one scenario per example in `canonical.json`, and its translation into each client |
| `data/runs.json`, `static/img/shots/` | what the CLI examples printed and showed on an Android 15 emulator |

The reference is never written by hand. `scripts/extract.py` reads the
commands' own `--help`, the MCP server's `tools/list` and each client's doc
comments into `data/mobium.json`; `scripts/generate.py` writes the pages from
that, the examples and the runs. So a page cannot describe a flag or a
method that no longer exists — the next build drops it.

## Every example is checked

`scripts/check_examples.py` holds each example to its surface:

- the MCP arguments against the tool's schema, the command against its flags;
- every client's code by compiling or type-checking it against that client —
  Python against an autospec of `Device`, JavaScript with `tsc --strict`
  against `index.d.ts`, Go with `go vet`, Java with `javac`, .NET with
  `dotnet build`.

A missing toolchain fails the check rather than skipping it. CI runs all of it
before building.

`scripts/capture.py` runs the CLI examples on an emulator and records their
output and screenshots. It changes device settings and puts them back, and it
refuses anything but an emulator. Output is shown only under an example whose
command it ran verbatim; a screenshot from any other command says which one in
its caption.

## Building it

Needs Node 20+, Python 3.10+, Go, and a checkout of `mobiumdev/mobium`.

```sh
npm ci
git clone https://github.com/mobiumdev/mobium.git ../mobium
go build -C ../mobium -o "$PWD/mobium" ./cmd/mobium
MOBIUM_SRC=../mobium MOBIUM_BIN=./mobium npm run gen
MOBIUM_SRC=../mobium npm run check    # also needs javac and dotnet
npm start
```

`mobium.ref` names the Mobium branch or commit the site is built from; CI
builds on every push, and daily, so the reference follows it.

## License

This site is MIT licensed. Mobium itself is under the Apache License 2.0.
