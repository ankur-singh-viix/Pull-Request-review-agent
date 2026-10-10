# Style guidelines

## STY-1: Use logging, not print
Use the logger instead of `print()` in application code.

## STY-2: No commented-out code
Delete dead code instead of commenting it out. Git keeps the history.

## STY-3: Public functions have type hints
Every public function declares parameter and return type hints.

## STY-4: Loggers come from get_logger
Use `get_logger(__name__)` from `app.logging`. Never call `logging.getLogger` directly, because `get_logger` attaches the request-id formatter.