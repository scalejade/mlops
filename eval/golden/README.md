# Golden set

Verified ground truth. Client documents do NOT go in git.

```
golden/
  <task>/
    README.md        # documents included, who verified them, when
    manifest.yaml    # document IDs + HF dataset repo/revision holding the real files
    expected/        # verified outputs, if non-sensitive
```

Every entry needs a named human verifier and a date. An unverified "golden" set
is just more model output.
