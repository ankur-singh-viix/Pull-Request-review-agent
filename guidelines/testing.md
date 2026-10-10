# Testing guidelines

## TST-1: Every behaviour change ships with tests
New functions and new branches need tests that contain assertions. A test that only calls the function without an `assert` does not count.

## TST-2: Test error paths
Every raised exception needs a test using `pytest.raises`.

## TST-3: No real network or database in unit tests
Mock `requests` and use the `db_session` fixture instead of a real connection.