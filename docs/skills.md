# Skills

Skills are Markdown-based prompt extensions that inject additional context into an agent's system prompt based on triggers.

## Skill File Format

Each skill is a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: code-review
description: Guidelines for reviewing code
version: "1.0"
trigger: keyword
keywords:
  - review
  - code review
  - PR
tools:
  - bash
  - file_read
priority: 10
enabled: true
---

You are an expert code reviewer. When reviewing code:

1. Check for security vulnerabilities
2. Verify error handling
3. Ensure consistent style
4. Look for performance issues
...
```

## Frontmatter Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | filename | Unique skill name |
| `description` | string | — | Human-readable description |
| `version` | string | `"1.0"` | Skill version |
| `trigger` | string | `"keyword"` | Trigger type: `keyword`, `always`, `never` |
| `keywords` | list | `[]` | Keywords that activate this skill (for `keyword` trigger) |
| `tools` | list | `[]` | Tools this skill recommends (informational) |
| `priority` | int | `0` | Higher priority skills are injected first |
| `enabled` | bool | `true` | Whether the skill is active |

## Trigger Types

### `keyword`
The skill activates when any of its keywords appear in the user's message (case-insensitive match).

### `always`
The skill is always injected into the system prompt for every message.

### `never`
The skill is loaded but never automatically triggered. Useful for skills that are only enabled manually.

## Skill Directories

Skills are loaded from:
1. **User skills** — `skills/` directory in the project root
2. **Built-in skills** — `src/aegis/skills/builtin/` (when `SKILLS__BUILTIN_SKILLS=true`)

## Hot Reload

When `SKILLS__HOT_RELOAD=true` (default), the skills loader watches for file changes and automatically reloads modified skills without restarting the server.

## Examples

### Always-on skill

```markdown
---
name: safety
trigger: always
priority: 100
---

Always follow these safety guidelines:
- Never execute destructive commands without confirmation
- Sanitize all user inputs
- Do not expose secrets or credentials
```

### Keyword-triggered skill

```markdown
---
name: data-analysis
trigger: keyword
keywords:
  - analyze
  - chart
  - plot
  - dataset
  - csv
tools:
  - python_interpreter
  - file_read
---

When performing data analysis:
- Use pandas for data manipulation
- Create clear visualizations with matplotlib or seaborn
- Always show summary statistics first
- Save plots to the sandbox directory
```

## Skill Directory Structure

```
skills/
├── examples/           # Example skill files
├── code-review/
│   └── SKILL.md
├── data-analysis/
│   └── SKILL.md
└── writing/
    └── SKILL.md
```

Each skill can be in a subdirectory or directly in the skills root — the loader scans recursively for `SKILL.md` files.
