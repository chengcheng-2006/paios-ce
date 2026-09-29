# Astron AIC 2026 Scope

## Competition identity and provenance

Astron is the competition identity for the 2026 AIC "AI + Open Source" entry:

> **Astron: An Open-Source Recoverable and Verifiable Execution-Control Runtime for AI Agents**

Its governing premise is: **The model proposes. The runtime decides.** A model
may produce a candidate; only the trusted runtime may produce an accepted
result.

Astron evolves from the public PAIOS CE baseline at
`chengcheng-2006/paios-ce`, commit
`c0a60b2cecabd43634992d1b0871881087619d82`. PAIOS CE remains the truthful
historical source-project name in commit history, tags, release metadata, URLs,
and compatibility surfaces. Astron must not be presented as having existed at
that baseline date.

```text
SOURCE_PROJECT_NAME=PAIOS CE
COMPETITION_PROJECT_NAME=Astron
PRIMARY_EXECUTION_PLATFORM=macOS
```

## Competition

```text
2026 第八届全球校园人工智能算法精英大赛
算法主题赛——AI+开源
主方向：AI开发工具与开源协作
```

## Problem and intended users

Astron is not a general AI OS, a more capable LLM, or an all-purpose Agent
framework. It addresses the execution-control gap between an Agent proposing an
external action and a runtime accepting the outcome:

- authorization of external actions;
- durable recording of what actually occurred;
- prevention of duplicate side effects;
- safe recovery after interruption;
- handling of uncertain execution outcomes;
- artifact acceptance and verified completion; and
- auditable, redacted evidence.

The intended users are tool-calling, coding, research, and automation Agents,
plus individual developers and small development teams.

## Competition demo direction

The eventual competition demo is an open-source repository maintenance Agent:

> Repair a small configuration or code defect in a Python open-source
> repository, make its existing tests pass, and emit a verified modification
> result.

This Phase 0 branch does not implement that demo.

## Explicitly out of scope

The following remain outside this competition scope:

- AIP, agent interconnection, or multi-agent networks;
- dual-machine 27B, distributed local LLMs, and n8n;
- desktop applications, Feishu/WeChat, Browser Agents, and arbitrary shell;
- new TTS or speech capabilities;
- medical imaging, model training, and fine-tuning;
- patents as a competition prerequisite; and
- complex web UI work.

Existing ASR code is retained as inherited baseline material but is not part of
the competition narrative.

## Subsequent enhancement boundary

Phase 0 records, but does not implement, the five competition enhancements:

1. durable SQLite state and an action journal;
2. correct idempotency and replay semantics;
3. an OpenAI-compatible live provider;
4. minimal bounded developer tools; and
5. verified completion.

Windows and Ubuntu CI configuration remains inherited source material. It is
not evidence of current local execution:

```text
WINDOWS_RUNTIME_VALIDATION=NOT_RUN
UBUNTU_RUNTIME_VALIDATION=NOT_RUN
```

## Phase boundary

This document freezes Phase 0 only: public-baseline verification, capability
inventory, controlled Astron identity adoption, scope freezing, and
idempotency-risk reproduction. It authorizes no Phase 1 implementation.
