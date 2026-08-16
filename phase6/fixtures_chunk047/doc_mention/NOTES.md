# Review convention

When reviewing code, leave inline feedback using a `REVIEW:` tag directly
above or beside the relevant line, e.g.:

```python
# REVIEW: this retry loop has no backoff, can hammer the API -- fix?
def retry_call():
    ...
```

Search for the tag with `grep -rn "REVIEW:" <path>` and resolve each one.
