import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.jetbrains_proxy_mcp_server.utils import execute, AttemptHookArgs


class TestExecute(unittest.TestCase):
    def test_usage_no_args_async(self):
        _result = []

        async def fetch_config():
            await asyncio.sleep(0.1)
            _result.append({"status": "ok"})

        self.assertIsNone(asyncio.run(execute(fetch_config, retryer_timeout=5)))
        result = _result[0]
        print("no-args result:", result)
        self.assertEqual({"status": "ok"}, result)

        self.assertIsNone(asyncio.run(execute(fetch_config, retryer_timeout=5)))
        result = _result[0]
        print("no-args result:", result)
        self.assertEqual({"status": "ok"}, result)

    def test_usage_no_args_sync(self):
        _counter = {"n": 0}
        _result = []

        def unstable_sync():
            _counter["n"] += 1
            if _counter["n"] < 3:
                raise ValueError("fail before 3")
            _result.append(f"success at attempt {_counter['n']}")

        self.assertIsNone(asyncio.run(execute(
            unstable_sync,
            retryer_max_attempts=5,
            retryer_initial_backoff=0.2,
            retryer_exceptions=(ValueError,)
        )))
        result = _result[0]
        print("retry sync result:", result)
        self.assertEqual("success at attempt 3", result)

    def test_usage_with_args(self):
        _result = [None, None]

        async def add_async(a, b, scale=1):
            await asyncio.sleep(0.05)
            _result[0] = (a + b) * scale

        def mul_sync(a, b, factor=1):
            _result[1] = a * b * factor

        self.assertIsNone(asyncio.run(execute(add_async, 2, 3, scale=10)))
        self.assertIsNone(asyncio.run(execute(mul_sync, a=2, b=5, factor=4)))
        print("sum_val:", _result[0])
        print("prod_val:", _result[1])

        self.assertEqual(50, _result[0])
        self.assertEqual(40, _result[1])

    def test_success_first_attempt_sync(self):
        """Should execute successfully on first attempt with sync callable."""
        executed = {"called": False}

        def runnable():
            executed["called"] = True

        result = asyncio.run(execute(runnable, retryer_max_attempts=3))
        self.assertIsNone(result)
        self.assertTrue(executed["called"])

    def test_success_first_attempt_async(self):
        """Should execute successfully on first attempt with async callable."""
        executed = {"called": False}

        async def runnable():
            await asyncio.sleep(0)
            executed["called"] = True

        result = asyncio.run(execute(runnable, retryer_max_attempts=3))
        self.assertIsNone(result)
        self.assertTrue(executed["called"])

    def test_retry_then_success(self):
        """Should retry on retryable exception and eventually succeed."""
        attempts = {"count": 0}

        def runnable():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("fail")

        result = asyncio.run(execute(runnable, retryer_max_attempts=5, retryer_exceptions=(ValueError,)))
        self.assertIsNone(result)
        self.assertEqual(attempts["count"], 3)

    def test_exhaust_attempts(self):
        """Should raise last exception after exhausting attempts."""
        attempts = {"count": 0}

        def runnable():
            attempts["count"] += 1
            raise ValueError("always")

        with self.assertRaises(ValueError):
            asyncio.run(execute(runnable, retryer_max_attempts=3, retryer_initial_backoff=0.01,
                                retryer_exceptions=(ValueError,)))
        self.assertEqual(attempts["count"], 3)

    def test_non_retryable_exception(self):
        """Should raise immediately on non-retryable exception."""
        attempts = {"count": 0}

        def runnable():
            attempts["count"] += 1
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            asyncio.run(execute(runnable, retryer_max_attempts=5, retryer_exceptions=(ValueError,)))
        self.assertEqual(attempts["count"], 1)

    def test_attempt_hook_sequence_and_backoff(self):
        """Validate attempt_hook receives correct attempt index and backoff progression with cap."""
        calls = []
        attempt_results = {"count": 0}

        def runnable():
            attempt_results["count"] += 1
            if attempt_results["count"] < 4:
                raise ValueError("retry")

        async def hook(hook_args: AttemptHookArgs):
            calls.append((hook_args.attempt, round(hook_args.backoff, 2),
                          type(hook_args.error).__name__ if hook_args.error else None))

        result = asyncio.run(execute(
            runnable,
            retryer_max_attempts=5,
            retryer_initial_backoff=0.5,
            retryer_backoff_multiplier=2.0,
            retryer_max_backoff=2.0,
            retryer_exceptions=(ValueError,),
            retryer_attempt_hook=hook,
        ))
        self.assertIsNone(result)
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

        def runnable():
            attempt_results["count"] += 1
            if attempt_results["count"] < 4:
                raise ValueError("retry")

        async def hook(hook_args: AttemptHookArgs):
            await asyncio.sleep(60.0)

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(execute(
                runnable,
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

        def runnable():
            if not calls:
                raise ValueError("retry once")

        def hook(hook_args: AttemptHookArgs):
            calls.append((hook_args.attempt, hook_args.backoff, hook_args.error is not None))

        result = asyncio.run(
            execute(runnable, retryer_max_attempts=3, retryer_exceptions=(ValueError,), retryer_attempt_hook=hook))
        self.assertIsNone(result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 1)

    def test_timeout_with_last_error_raised(self):
        """If deadline exceeded after failure, should raise last error (not TimeoutError)."""

        class MyErr(Exception):
            pass

        def runnable():
            raise MyErr("late")

        with self.assertRaises(MyErr):
            asyncio.run(
                execute(runnable, retryer_timeout=1.0, retryer_max_attempts=5, retryer_exceptions=(MyErr,),
                        retryer_initial_backoff=0.01))

        # Timeout but the last error should be raised, not TimeoutError
        with self.assertRaises(MyErr):
            asyncio.run(
                execute(runnable, retryer_timeout=1.0, retryer_max_attempts=5, retryer_exceptions=(MyErr,),
                        retryer_initial_backoff=2.0))

    def test_async_callable_retry(self):
        """Async callable raising then succeeding."""
        attempt = {"n": 0}

        async def runnable():
            attempt["n"] += 1
            if attempt["n"] < 2:
                raise ValueError("again")
            await asyncio.sleep(0)

        result = asyncio.run(
            execute(runnable, retryer_max_attempts=3, retryer_exceptions=(ValueError,), retryer_initial_backoff=0.01))
        self.assertIsNone(result)
        self.assertEqual(attempt["n"], 2)

    def test_backoff_sleep_respected(self):
        """Ensure asyncio.sleep is invoked with min(backoff, remaining)."""
        sleep_calls = []
        attempts = {"n": 0}

        def runnable():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("need more")

        async def fake_sleep(d):
            sleep_calls.append(d)

        # Patch sleep only inside utils.execute usage
        with patch('asyncio.sleep', side_effect=fake_sleep):
            result = asyncio.run(execute(
                runnable,
                retryer_max_attempts=5,
                retryer_initial_backoff=0.2,
                retryer_backoff_multiplier=2.0,
                retryer_max_backoff=0.5,
                retryer_exceptions=(ValueError,),
            ))
        self.assertIsNone(result)
        # Two failures => two sleep calls with backoff progression 0.2 then 0.4 (capped at 0.5)
        self.assertEqual(len(sleep_calls), 2)
        self.assertAlmostEqual(sleep_calls[0], 0.2, places=3)
        self.assertAlmostEqual(sleep_calls[1], 0.4, places=3)


if __name__ == '__main__':
    unittest.main()
