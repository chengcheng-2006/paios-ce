# AIC 2026 repository-maintenance fixture

This is a deliberately small, trusted fixture for Astron Phase 3. Its
`tests/` directory fails on an untouched fresh copy. A task must make one
permitted source correction, produce `.astron-artifacts/change_summary.json`,
and pass the trusted verifier. It is not an arbitrary-code sandbox and must
not be pointed at an Owner repository.
