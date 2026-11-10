"""Compact nested diagnostics without losing the actual failure type."""


def error_details(exc):
    if isinstance(exc, BaseExceptionGroup):
        return [entry for child in exc.exceptions for entry in error_details(child)]
    return [{"type": type(exc).__name__, "message": str(exc)[:2000]}]
