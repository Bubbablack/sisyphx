"""A module with one genuine, unresolved review marker above a line."""


def retry_call(url: str) -> None:
    # REVIEW: this retry loop has no backoff, can hammer the API -- fix?
    for _ in range(5):
        call(url)


def call(url: str) -> None:
    pass
