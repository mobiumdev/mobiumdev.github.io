---
title: Introduction
slug: /
sidebar_position: 0
description: Mobile app automation for AI agents and humans — Android emulators and phones, iOS simulators and iPhones, from one Go binary.
---

# Mobium

*Mutatis mutandis.*

**Mobile app automation for AI agents and humans.** Android emulators,
Android phones, iOS simulators and iPhones, driven through one tool layer
from a single Go binary with no runtime dependencies.

```sh
mobium launch com.example.shop && mobium map && mobium tap @e5 && mobium map
```

Mobium is for letting a coding agent check its own work on mobile. An agent
that changed a login screen should be able to open the app, read what is
actually on screen, tap through the flow and look at the result — without a
person driving an emulator for it. People get the same commands.

It drives native, hybrid and cross-platform apps, and pages in a mobile browser
or installed as a PWA, the way [Vibium](https://github.com/VibiumDev/vibium)
drives browsers: a `map` → `@ref` → act loop that an agent can follow
without learning a new model.

What each app type needs, and which apps of each type were driven, is in
[APP-TYPES](https://github.com/mobiumdev/mobium/blob/main/docs/APP-TYPES.md).

## The loop

`map` reads the screen and gives everything a person could act on a ref:

```text
$ mobium map
@e1 Navigate up (button)
@e2 Email address (input)
@e3 password (password)
@e4 Remember me (checkbox, unchecked)
@e5 Sign In (button)
@e6 Forgot password? (link)

$ mobium type @e2 "someone@example.com"
$ mobium tap @e5
tapped @e5 at (540, 930)
```

A ref stands for the most durable locator that picks out that one element —
a resource id, then an accessibility label, then visible text. `tap @e5`
**reads the screen again and re-resolves** the locator before it touches
anything; it never replays the coordinates `map` saw, because the screen moves
between commands. A locator that has become ambiguous is refused, not
guessed.

The same locators work on both platforms:

| Locator | Android | iOS |
| --- | --- | --- |
| `text=Sign In` | `text` | `value`, or the label of a control with no text of its own |
| `label=Email` | `content-desc` | accessibility label |
| `testid=submit` | `resource-id` | `accessibilityIdentifier` |
| `role=button` | `android.widget.Button` and kin | `XCUIElementTypeButton` |

Coordinates are device pixels on both, so a point read off a screenshot can
be tapped directly.

## Actions wait, and refuse what they cannot do

Before it acts, every action waits for its target to exist, be on screen,
stop moving and be enabled, and scrolls to it if it is off screen. It refuses
— rather than taps — a target under a dialog or the keyboard, and `type`
refuses what is certainly not a text field. A refusal carries a code that is
the same in every client and on the wire, and a remedy that works.
[Auto-wait](/guides/autowait) goes through each check.

## Seven front doors, one tool layer

| Surface | For |
| --- | --- |
| [CLI](/reference/cli) | people, shell scripts, and agents with a shell |
| [MCP](/reference/mcp) | agents: `mobium mcp` is an MCP server on stdio |
| [Python](/reference/python), [JavaScript](/reference/javascript), [Go](/reference/go), [Java](/reference/java), [.NET](/reference/dotnet) | test code and tools |
| [`mobium test`](/guides/test-runner) | JSON test files, run on the devices a config names |

Every command, MCP tool and client method is the same code underneath: the
CLI parses flags and calls a tool by name, the MCP server hands the tool to an
agent, and each client speaks to it through `mobium pipe`. So they cannot
answer differently, and [the reference](/reference) links each tool across
all seven.

## Where it runs

| | Android emulator or phone | iOS simulator or iPhone |
| --- | --- | --- |
| **macOS** | Yes | Yes — needs Xcode |
| **Linux** | Yes | No — iOS needs Xcode, which runs only on macOS |
| **Windows** | Not yet | No |

Verified on devices, not only compiled: a Pixel 7 emulator on Android 15 and
17, a Pixel 8 Pro on Android 17, an iPhone 17 Pro simulator on iOS 26.5, and
an iPhone 15 Plus on iOS 26.6.2.

## Next

- [Quick start](/quickstart) — from nothing to a script that starts a
  session, taps, takes a screenshot and quits, in the language you use.
- [Guides](/guides) — auto-wait, the test runner, a grid of devices, network
  conditions, the CLI and MCP in depth.
- [Reference](/reference) — every command, tool and method, each with
  examples.
