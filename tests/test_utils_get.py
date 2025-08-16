import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.jetbrains_proxy_mcp_server.utils import get, AttemptHookArgs


class TestGet(unittest.TestCase):
    def test_usage_no_args_async(self):
        async def fetch_config():
            await asyncio.sleep(0.1)
            return {"status": "ok"}

        result = asyncio.run(get(fetch_config, retryer_timeout=5))
        print("no-args result:", result)
        self.assertEqual({"status": "ok"}, result)

    def test_usage_no_args_sync(self):
        _counter = {"n": 0}

        def unstable_sync():
            _counter["n"] += 1
            if _counter["n"] < 3:
                raise ValueError("fail before 3")
            return f"success at attempt {_counter['n']}"

        result = asyncio.run(get(
            unstable_sync,
            retryer_max_attempts=5,
            retryer_initial_backoff=0.2,
            retryer_exceptions=(ValueError,)
        ))
        print("retry sync result:", result)
        self.assertEqual("success at attempt 3", result)

    def test_usage_with_args(self):
        async def add_async(a, b, scale=1):
            await asyncio.sleep(0.05)
            return (a + b) * scale

        def mul_sync(a, b, factor=1):
            return a * b * factor

        sum_val = asyncio.run(get(add_async, 2, 3, scale=10))
        prod_val = asyncio.run(get(mul_sync, a=2, b=5, factor=4))
        print("sum_val:", sum_val)
        print("prod_val:", prod_val)

        self.assertEqual(50, sum_val)
        self.assertEqual(40, prod_val)

    def test_success_first_attempt_sync(self):
        """Should return value on first attempt with sync callable."""

        def call():
            return 42

        result = asyncio.run(get(call, retryer_max_attempts=3))
        self.assertEqual(result, 42)

    def test_success_first_attempt_async(self):
        """Should return value on first attempt with async callable."""

        async def call():
            await asyncio.sleep(0)
            return "ok"

        result = asyncio.run(get(call, retryer_max_attempts=3))
        self.assertEqual(result, "ok")

    def test_retry_then_success(self):
        """Should retry on retryable exception and eventually succeed."""
        attempts = {"count": 0}

        def call():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("fail")
            return "done"

        result = asyncio.run(get(call, retryer_max_attempts=5, retryer_exceptions=(ValueError,)))
        self.assertEqual(result, "done")
        self.assertEqual(attempts["count"], 3)

    def test_exhaust_attempts(self):
        """Should raise last exception after exhausting attempts."""
        attempts = {"count": 0}

        def call():
            attempts["count"] += 1
            raise ValueError("always")

        with self.assertRaises(ValueError):
            asyncio.run(
                get(call, retryer_max_attempts=3, retryer_initial_backoff=0.01, retryer_exceptions=(ValueError,)))
        self.assertEqual(attempts["count"], 3)

    def test_non_retryable_exception(self):
        """Should raise immediately on non-retryable exception."""
        attempts = {"count": 0}

        def call():
            attempts["count"] += 1
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            asyncio.run(get(call, retryer_max_attempts=5, retryer_exceptions=(ValueError,)))
        self.assertEqual(attempts["count"], 1)

    def test_attempt_hook_sequence_and_backoff(self):
        """Validate attempt_hook receives correct attempt index and backoff progression with cap."""
        calls = []
        attempt_results = {"count": 0}

        def call():
            attempt_results["count"] += 1
            if attempt_results["count"] < 4:
                raise ValueError("retry")
            return "ok"

        async def hook(hook_args: AttemptHookArgs):
            calls.append((hook_args.attempt, round(hook_args.backoff, 2),
                          type(hook_args.error).__name__ if hook_args.error else None))

        result = asyncio.run(get(
            call,
            retryer_max_attempts=5,
            retryer_initial_backoff=0.5,
            retryer_backoff_multiplier=2.0,
            retryer_max_backoff=2.0,
            retryer_exceptions=(ValueError,),
            retryer_attempt_hook=hook,
        ))
        self.assertEqual(result, "ok")
        # Expect 3 failing attempts => 3 hook calls with backoff: 0.5,1.0,2.0
        expected = [
            (1, 0.5, 'ValueError'),
            (2, 1.0, 'ValueError'),
            (3, 2.0, 'ValueError'),
        ]
        self.assertEqual(calls, expected)

    def test_attempt_hook_timeout(self):
        """Validate attempt_hook is called on timeout."""

        attempt_results = {"count": 0}

        def call():
            attempt_results["count"] += 1
            if attempt_results["count"] < 4:
                raise ValueError("retry")
            return "ok"

        async def hook(hook_args: AttemptHookArgs):
            await asyncio.sleep(60.0)

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(get(
                call,
                retryer_timeout=5.0,
                retryer_max_attempts=5,
                retryer_initial_backoff=0.5,
                retryer_backoff_multiplier=2.0,
                retryer_max_backoff=2.0,
                retryer_exceptions=(ValueError,),
                retryer_attempt_hook=hook,
            ))

    def test_attempt_hook_sync(self):
        """Validate sync attempt_hook is supported."""
        calls = []

        def call():
            if not calls:
                raise ValueError("retry once")
            return 1

        def hook(hook_args: AttemptHookArgs):
            calls.append((hook_args.attempt, hook_args.backoff, hook_args.error is not None))

        result = asyncio.run(
            get(call, retryer_max_attempts=3, retryer_exceptions=(ValueError,), retryer_attempt_hook=hook))
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 1)

    def test_timeout_with_last_error_raised(self):
        """If deadline exceeded after failure, should raise last error (not TimeoutError)."""

        class MyErr(Exception):
            pass

        def call():
            raise MyErr("late")

        with self.assertRaises(MyErr):
            asyncio.run(
                get(call, retryer_timeout=1.0, retryer_max_attempts=5, retryer_exceptions=(MyErr,),
                    retryer_initial_backoff=0.01))

        # Timeout but the last error should be raised, not TimeoutError
        with self.assertRaises(MyErr):
            asyncio.run(
                get(call, retryer_timeout=1.0, retryer_max_attempts=5, retryer_exceptions=(MyErr,),
                    retryer_initial_backoff=2.0))

    def test_async_callable_retry(self):
        """Async callable raising then succeeding."""
        attempt = {"n": 0}

        async def call():
            attempt["n"] += 1
            if attempt["n"] < 2:
                raise ValueError("again")
            await asyncio.sleep(0)
            return "async-ok"

        result = asyncio.run(
            get(call, retryer_max_attempts=3, retryer_exceptions=(ValueError,), retryer_initial_backoff=0.01))
        self.assertEqual(result, "async-ok")
        self.assertEqual(attempt["n"], 2)

    def test_backoff_sleep_respected(self):
        """Ensure asyncio.sleep is invoked with min(backoff, remaining)."""
        sleep_calls = []
        attempts = {"n": 0}

        def call():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("need more")
            return 7

        async def fake_sleep(d):
            sleep_calls.append(d)

        # Patch sleep only inside utils.get usage
        with patch('asyncio.sleep', side_effect=fake_sleep):
            result = asyncio.run(get(
                call,
                retryer_max_attempts=5,
                retryer_initial_backoff=0.2,
                retryer_backoff_multiplier=2.0,
                retryer_max_backoff=0.5,
                retryer_exceptions=(ValueError,),
            ))
        self.assertEqual(result, 7)
        # Two failures => two sleep calls with backoff progression 0.2 then 0.4 (capped at 0.5)
        self.assertEqual(len(sleep_calls), 2)
        self.assertAlmostEqual(sleep_calls[0], 0.2, places=3)
        self.assertAlmostEqual(sleep_calls[1], 0.4, places=3)


if __name__ == '__main__':
    unittest.main()
