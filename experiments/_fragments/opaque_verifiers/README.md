# Opaque Verifiers

This directory holds experiment-owned tooling for building opaque verifier artifacts.

In this repository, opaque means:

- the space agent does not receive readable verifier source code inside the assembled workspace
- experiments may still provide a runnable local validation helper

Opaque does not mean cryptographic secrecy or resistance to reverse engineering.

Ownership:

- canonical verifier source remains under `benchmarks/`
- experiments own how verifier behavior is exposed inside a workspace
- generated artifacts are ignored by git and live under `artifacts/`

The tracked entrypoint is:

```bash
uv run python experiments/_fragments/opaque_verifiers/build.py
```

Artifacts are runtime-image-specific. The builder uses the base runtime image from `runtimes/base/runtime.yaml`, mounts the repository into a disposable container, builds the artifact inside that container, and smoke-tests the artifact inside the same image before marking it reusable. Reused artifacts are still checked against the verifier source hash, builder inputs, runtime image stamp, executability, and the benchmark-specific smoke case.

The `artifacts/` directory may contain generated verifier binaries, `build.json` metadata, and temporary build scratch directories. All of that state is ignored; only `build.py`, `manifest.yaml`, this README, and the `.gitignore` policy are tracked.

If the runtime image is missing or stale, rebuild it first:

```bash
uv run python runtimes/base/build.py
```
