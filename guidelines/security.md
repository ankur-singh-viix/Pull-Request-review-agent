# Security guidelines

## SEC-1: Never build SQL with string formatting
Queries must be parameterized. Do not build SQL with f-strings, `+` concatenation, `.format()` or `%` interpolation of user input. Pass values as bound parameters, for example `cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))`.

## SEC-2: No hardcoded secrets
API keys, passwords, tokens and connection strings must come from environment variables or the secret manager, never from source code. Rotate any secret that was ever committed.

## SEC-3: No shell=True, eval or exec
Do not use `subprocess` with `shell=True`, or `eval()` / `exec()` on dynamic input. Pass argument lists to `subprocess.run` and parse data with `json` or `ast.literal_eval`.

## SEC-4: Never deserialize untrusted data with pickle or unsafe yaml
Use `json` or `yaml.safe_load`. Never call `pickle.loads` or `yaml.load` on request bodies, uploaded files or cache entries that users can influence.

## SEC-5: Passwords use bcrypt or argon2
Never store or compare passwords hashed with md5 or sha1. Use `bcrypt` or `argon2` with a per-user salt.

## SEC-6: Internal services are called through internal_client
Calls to internal hosts such as `billing.internal` must go through `internal_client`, which adds service authentication and timeouts. Never call internal URLs with raw `requests.get` or `httpx.get`.