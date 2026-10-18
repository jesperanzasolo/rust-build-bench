# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub's
[private vulnerability reporting](https://github.com/jesperanzasolo/rust-build-bench/security/advisories/new),
not in a public issue.

Relevant reports include anything that lets untrusted input run code or write to
the repository, for example through the benchmark workflow, the publish script,
or a crafted corpus or tool configuration.

You will get an acknowledgement within a week. Fixes go to `main`; there are no
maintained release branches.

## Scope

The harness downloads and runs third-party build tools and corpora at pinned
versions (`tools/versions.toml`, `corpora/*.toml`). Vulnerabilities in those
projects belong with their maintainers; a pin that should be updated because of
one is in scope here.
