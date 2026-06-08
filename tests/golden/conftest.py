"""Keep the frozen golden fixture out of pytest collection.

The fixture under ``fixture/`` is analyzer INPUT DATA, not a test suite. Its
``fixture/tests/test_*.py`` files exist only so the Self-Analysis ``missing_test``
convention can find them — they must NOT be collected and run as real tests (that
would pollute the suite and couple it to fixture content). ``test_golden_analysis.py``
(one directory up) is the real test that consumes this fixture.
"""

collect_ignore_glob = ["fixture/*"]
