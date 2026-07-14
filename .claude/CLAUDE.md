# Claude Code — Global Standards

## Python Standards

Formatter: Black (line length 100)
Import sorter: isort (profile = black)
Python version: 3.11+
Type hints: required on all function signatures
Docstrings: Google style

---

## Available Skills

- `/branch-review` — full branch audit: black, isort, naming, exceptions, repo structure, python security, prompt security
- `/wiki-check` — validate docs/wiki relative links against transform_wiki_links.py SUBSTITUTIONS; auto-fix any missing entries

---

## Code Review Rules (apply to ALL suggestions)

### Naming
- Variables must be self-explaining. Never suggest `tmp`, `res`, `val`, `data`, `obj`
- Booleans must start with `is_`, `has_`, `can_`, `should_`
- Loop counters `i/j/k` only acceptable in numeric index contexts
- No Hungarian notation: never `strName`, `intCount`, `lstItems`
- No ambiguous abbreviations: never `usr`, `mgr`, `proc`, `cfg` unless established domain term

### Exceptions
- Never suggest bare `except:` or `except Exception: pass`
- Always chain exceptions with `raise NewError(...) from e`
- Try blocks should wrap the minimum possible lines — never more than 10
- Never swallow errors silently — always log or re-raise

### Imports
- Always group: stdlib → third-party → local, each separated by a blank line
- Always alphabetically sorted within each group
- Never suggest wildcard imports
- Never suggest imports inside functions unless there is an explicit circular import reason

### Structure
- New directories must have `__init__.py`
- Tests always in `tests/` prefixed with `test_`
- No business logic in `__init__.py`
- No config files, secrets, or `.env` files staged to git

---

## Security Rules (apply to ALL code suggestions)

- Never suggest string interpolation in SQL — always parameterized queries
- Never suggest `random` for tokens/passwords — always `secrets` module
- Never suggest `pickle` for external data — use JSON or msgpack
- Always suggest `yaml.safe_load()` not `yaml.load()`
- Always suggest `hmac.compare_digest()` for token/hash comparison — never `==`
- Never suggest `subprocess` with `shell=True` and variable content
- Always suggest `pathlib` with canonicalization for user-supplied file paths
- Always suggest `defusedxml` for XML parsing
- Flag any variable that looks like a secret being assigned a literal string
- Passwords must be hashed with `bcrypt`, `argon2`, or `scrypt` — never `md5`/`sha1`/`sha256` directly
- Never return raw stack traces or internal error details to API callers
- Never log passwords, tokens, or PII — even at DEBUG level

---

## Prompt Engineering Rules (apply to ALL prompt suggestions)

- Always isolate user input with XML tags: `<user_input>...</user_input>`
- Always include an out-of-scope fallback instruction in system prompts
- Never put secrets, API keys, or internal logic in a system prompt
- Always specify output format explicitly when prompt output feeds downstream code
- Prompt templates must use explicit delimiters — never raw `.format()` or `%s` on user content
- Always anchor the model persona explicitly so it cannot be overridden by user input
- Always include a "do not reveal these instructions" guardrail in system prompts
- Always guard against context stuffing — validate and truncate user input length before injecting into prompts
- Never assume model memory across stateless API calls — always pass full context explicitly
- Sensitive data (PII, internal records) must be redacted before being sent to third-party LLM APIs

---

## When I ask you to fix issues from a branch-review report

- Apply all fixes in one pass
- After fixing, confirm which issues were resolved
- Flag only the ambiguous ones for my decision (e.g. unclear variable renames, security trade-offs)
- Never ask about each issue individually
