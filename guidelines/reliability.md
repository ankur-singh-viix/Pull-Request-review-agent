# Reliability and API guidelines

## REL-1: Never swallow exceptions
Do not use a bare `except:` or `except Exception: pass`. Catch the narrowest exception type, then log it or re-raise.

## REL-2: Always release resources
Open files, sockets and database connections with `with` blocks. Never leave `open()` without a matching close.

## REL-3: Await every coroutine
Calling an `async def` function without `await` returns a coroutine object, not a result. Always `await` it or schedule it with `asyncio.create_task`.

## REL-4: Every outbound HTTP call sets a timeout
`requests.get(url)` without `timeout=` can hang forever. Always pass an explicit `timeout`.

## REL-5: Validate request bodies with Pydantic models
Endpoints must declare a Pydantic model for the request body. Never read `request.get_json()` or `request.json` and index into the dict directly.

## REL-6: Never return raw exception text to clients
Do not return `str(e)` or `repr(e)` in API responses because it leaks internals. Log the exception and return a generic message with an error code.