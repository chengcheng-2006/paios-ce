## Summary

Describe the narrow problem and the proposed change.

## Scope

- [ ] Documentation only
- [ ] Tests only
- [ ] Behavior change with tests
- [ ] Security-sensitive change discussed before implementation
- [ ] Live adapter proposal discussed before implementation

## Validation

List the commands and environments used.

```text
python -m pytest -ra -q
paios-ce health
paios-ce demo
```

## Security and privacy checklist

- [ ] No secret, token, cookie, private key, or real credential is included.
- [ ] No personal data, production data, private path, or production log is included.
- [ ] Examples use placeholders only.
- [ ] Support claims do not exceed `SUPPORT_MATRIX.md`.
- [ ] Live Provider, Channel, Speech, Hermes, or OpenClaw support is not implied unless separately accepted.
- [ ] Redaction and deny-by-default behavior are preserved.
- [ ] Generated JSON Schemas (if affected) were regenerated through the official generator: `python -m paios_ce.tools.generate_schemas --out schemas`; no hand-patched generated files.
- [ ] Documentation links and Markdown render correctly.

## Release impact

- [ ] No release required
- [ ] Candidate for a future release after maintainer approval

Do not move an existing tag or publish PyPI/Zenodo as part of this pull request.
