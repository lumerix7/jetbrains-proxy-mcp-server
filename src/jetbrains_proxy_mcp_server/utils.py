"""utils.py: This file contains utility functions."""

import asyncio
import time
from typing import Callable, Awaitable, TypeVar, Optional, Union, ParamSpec

from pydantic import BaseModel

from .logger import get_logger

P = ParamSpec("P")
T = TypeVar("T")


class AttemptHookArgs(BaseModel):
    """Arguments passed to the attempt hook callback."""

    # BaseException type is not compatible with Pydantic by default, we # need to allow arbitrary types in the model.
    model_config = {"arbitrary_types_allowed": True}

    attempt: int | None = None
    backoff: float | None = None
    error: BaseException | None = None
    deadline: float | None = None


def get_str_property(props: dict, prop_name: str, env_var_name: str | None = None, default_value: str | None = None,
                     ) -> str | None:
    """Gets a string property from the property dictionary, environment variable, or default value.

    This function first tries to get the property from the property dictionary.
    If not found or blank, it tries to get it from an environment variable.
    If still not found or blank, it returns the default value.

    Args:
        :param props:         Dictionary containing properties.
        :param prop_name:     Name of the property to retrieve.
        :param env_var_name:  Environment variable name to check if the property isn't found in the dictionary.
        :param default_value: Default value to return if the property isn't found in the dictionary or environment.

    Returns:
        String property value, or None if not found and no default value provided.
    """

    value = props.get(prop_name, None)

    if value is not None:
        value_str = value if isinstance(value, str) else str(value)
        if value_str.strip():
            return value_str

    if env_var_name and env_var_name.strip():
        import os
        value = os.getenv(env_var_name)

        if value and value.strip():
            return value

    return default_value


def get_int_property(props: dict, prop_name: str, env_var_name: str | None = None, default_value: int | None = None,
                     ) -> int | None:
    """Gets an integer property from the property dictionary, environment variable, or default value.

    This function first tries to get the property from the property dictionary.
    If not found or invalid, it tries to get it from an environment variable.
    If still not found or invalid, it returns the default value.

    Args:
        :param props:         Dictionary containing properties.
        :param prop_name:     Name of the property to retrieve.
        :param env_var_name:  Environment variable name to check if the property isn't found in the dictionary.
        :param default_value: Default value to return if the property isn't found in the dictionary or environment.

    Returns:
        Integer property value, or None if not found and no default value provided.
    """

    value = props.get(prop_name, None)

    if isinstance(value, int):
        return value

    if value is not None:
        value_str = (value if isinstance(value, str) else str(value)).strip()
        if value_str:
            try:
                return int(value_str)
            except ValueError:
                pass

    if env_var_name and env_var_name.strip():
        import os
        value_str = os.getenv(env_var_name)

        if value_str and value_str.strip():
            try:
                return int(value_str.strip())
            except ValueError:
                pass

    return default_value


def get_float_property(props: dict, prop_name: str, env_var_name: str | None = None, default_value: float | None = None,
                       ) -> float | None:
    """Gets a float property from the property dictionary, environment variable, or default value.

    This function first tries to get the property from the property dictionary.
    If not found or invalid, it tries to get it from an environment variable.
    If still not found or invalid, it returns the default value.

    Args:
        :param props:         Dictionary containing properties.
        :param prop_name:     Name of the property to retrieve.
        :param env_var_name:  Environment variable name to check if the property isn't found in the dictionary.
        :param default_value: Default value to return if the property isn't found in the dictionary or environment.

    Returns:
        Float property value, or None if not found and no default value provided.
    """

    value = props.get(prop_name, None)

    if isinstance(value, float):
        return value

    if value is not None:
        value_str = (value if isinstance(value, str) else str(value)).strip()
        if value_str:
            try:
                return float(value_str)
            except ValueError:
                pass

    if env_var_name and env_var_name.strip():
        import os
        value_str = os.getenv(env_var_name)

        if value_str and value_str.strip():
            try:
                return float(value_str.strip())
            except ValueError:
                pass

    return default_value


def get_bool_property(props: dict, prop_name: str, env_var_name: str | None = None, default_value: bool | None = None,
                      ) -> bool | None:
    """Gets a boolean property from the property dictionary, environment variable, or default value.

    This function first tries to get the property from the property dictionary.
    If not found or invalid, it tries to get it from an environment variable.
    If still not found or invalid, it returns the default value.

    Args:
        :param props:         Dictionary containing properties.
        :param prop_name:     Name of the property to retrieve.
        :param env_var_name:  Environment variable name to check if the property isn't found in the dictionary.
        :param default_value: Default value to return if the property isn't found in the dictionary or environment.

    Returns:
        Boolean property value, or None if not found and no default value provided.
    """

    value = props.get(prop_name, None)

    if isinstance(value, bool):
        return value

    if value is not None:
        if isinstance(value, str):
            value_str = value.strip().lower()
            if value_str in ['true', 'yes', '1', 'y', 'on']:
                return True
            elif value_str in ['false', 'no', '0', 'n', 'off']:
                return False
        elif isinstance(value, (int, float)):
            return bool(value)

    if env_var_name and env_var_name.strip():
        import os
        env_value = os.getenv(env_var_name)

        if env_value is not None:
            env_value = env_value.strip().lower()
            if env_value in ['true', 'yes', '1', 'y', 'on']:
                return True
            elif env_value in ['false', 'no', '0', 'n', 'off']:
                return False

    return default_value


# @overload
# async def get(
#        func: Callable[P, Awaitable[T]],
#        *args: P.args,
#        timeout: float = ...,
#        max_attempts: int = ...,
#        initial_backoff: float = ...,
#        max_backoff: float = ...,
#        backoff_multiplier: float = ...,
#        retryable_exceptions: tuple[type[BaseException], ...] = ...,
#        attempt_hook: Optional[Callable[[HookArgs], Awaitable[None] | None]] = None,
#        **kwargs: P.kwargs
# ) -> T: ...
#
#
# @overload
# async def get(
#        func: Callable[P, T],
#        *args: P.args,
#        timeout: float = ...,
#        max_attempts: int = ...,
#        initial_backoff: float = ...,
#        max_backoff: float = ...,
#        backoff_multiplier: float = ...,
#        retryable_exceptions: tuple[type[BaseException], ...] = ...,
#        attempt_hook: Optional[Callable[[HookArgs], Awaitable[None] | None]] = None,
#        **kwargs: P.kwargs
# ) -> T: ...


async def get(
        func: Callable[P, Union[None, T, Awaitable[T]]],
        /,
        *args: P.args,
        retryer_timeout: float = 120.0,
        retryer_max_attempts: int = 5,
        retryer_initial_backoff: float = 1.0, retryer_max_backoff: float = 60.0,
        retryer_backoff_multiplier: float = 3.0,
        retryer_exceptions: tuple[type[BaseException], ...] = (BaseException,),
        retryer_attempt_hook: Optional[Callable[[AttemptHookArgs], Awaitable[None] | None]] = None,
        **kwargs: P.kwargs,
) -> T:
    """Generic no-args executor with retries and exponential backoff.

    Args:
        func:                         Sync or async callable returning a value.
        *args:                        Positional args passed to `call`.
        retryer_timeout:              Timeout in seconds.
        retryer_max_attempts:         Maximum number of attempts.
        retryer_initial_backoff:      Initial backoff in seconds.
        retryer_max_backoff:          Maximum backoff in seconds.
        retryer_backoff_multiplier:   Backoff multiplier.
        retryer_exceptions: Exception types that trigger a retry.
        retryer_attempt_hook:         Optional async/sync callback invoked after each attempt.
                                      Receives a HookArgs object with attempt, backoff, and error information.
        **kwargs:                     Keyword args passed to `call`.

    Returns:
        Successful result of operation.

    Raises:
        Last exception if all attempts fail or the deadline is exceeded.
    """

    log = get_logger()

    deadline = time.monotonic() + retryer_timeout
    retryer_max_attempts = max(1, retryer_max_attempts)
    backoff = max(0.1, retryer_initial_backoff)
    retryer_max_backoff = max(1.0, retryer_max_backoff)
    multiplier = max(1.0, retryer_backoff_multiplier)

    last_err: BaseException | None = None

    for attempt in range(1, retryer_max_attempts + 1):
        try:
            log.debug(f"Executing on attempt {attempt}/{retryer_max_attempts}...")
            result = func(*args, **kwargs)

            if asyncio.iscoroutine(result):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Timeout before executing attempt {attempt}/{retryer_max_attempts}")
                result = await asyncio.wait_for(result, timeout=remaining)

            log.debug(f"Successfully executed on attempt {attempt}/{retryer_max_attempts}.")
            return result
        except retryer_exceptions as e:
            last_err = e
        except BaseException as e:
            import traceback
            log.error(
                f"Non-retryable exception on attempt {attempt}/{retryer_max_attempts}: {e}.\n{traceback.format_exc()}")
            raise

        if attempt >= retryer_max_attempts:
            log.error(f"Exhausted {retryer_max_attempts} attempts: {last_err}")
            raise last_err

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.error(f"Timeout after {attempt}/{retryer_max_attempts} attempts: {last_err}.")
            if last_err:
                raise last_err
            raise TimeoutError(f"Timeout after {attempt}/{retryer_max_attempts} attempts: {last_err}")

        log.warning(f"Exception on attempt {attempt}/{retryer_max_attempts}: {last_err}. Backing off {backoff:.2f}s.")

        if retryer_attempt_hook:
            maybe_await = retryer_attempt_hook(
                AttemptHookArgs(attempt=attempt, backoff=backoff, error=last_err, deadline=deadline))
            if asyncio.iscoroutine(maybe_await):
                await asyncio.wait_for(maybe_await, timeout=remaining)
            remaining = deadline - time.monotonic()

        sleep_timeout = min(backoff, remaining)
        if sleep_timeout <= 0:
            log.error(f"Timeout during backoff after {attempt}/{retryer_max_attempts} attempts: {last_err}.")
            if last_err:
                raise last_err
            raise TimeoutError(f"Timeout during backoff after {attempt}/{retryer_max_attempts} attempts: {last_err}")

        log.debug(f"Sleeping for {sleep_timeout:.2f}s before next attempt {attempt + 1}/{retryer_max_attempts}...")
        await asyncio.sleep(sleep_timeout)
        backoff = min(retryer_max_backoff, backoff * multiplier)

    if last_err:
        log.error(f"Exhausted {retryer_max_attempts} attempts: {last_err}")
        raise last_err
    raise TimeoutError(f"Exceeded deadline without any attempt executing")


async def execute(
        func: Callable[P, Union[None, Awaitable[None]]],
        /,
        *args: P.args,
        retryer_timeout: float = 120.0,
        retryer_max_attempts: int = 5,
        retryer_initial_backoff: float = 1.0, retryer_max_backoff: float = 60.0,
        retryer_backoff_multiplier: float = 3.0,
        retryer_exceptions: tuple[type[BaseException], ...] = (BaseException,),
        retryer_attempt_hook: Optional[Callable[[AttemptHookArgs], Awaitable[None] | None]] = None,
        **kwargs: P.kwargs,
):
    """Generic no-args executor with retries and exponential backoff for functions that return None.

    Args:
        func:                         Async callable returning None.
        *args:                        Positional args passed to `func`.
        retryer_timeout:              Timeout in seconds.
        retryer_max_attempts:         Maximum number of attempts.
        retryer_initial_backoff:      Initial backoff in seconds.
        retryer_max_backoff:          Maximum backoff in seconds.
        retryer_backoff_multiplier:   Backoff multiplier.
        retryer_exceptions: Exception types that trigger a retry.
        retryer_attempt_hook:         Optional async/sync callback invoked after each attempt.
                                      Receives a HookArgs object with attempt, backoff, and error information.
        **kwargs:                     Keyword args passed to `func`.

    Returns:
        None

    Raises:
        Last exception if all attempts fail or the deadline is exceeded.
    """
    await get(
        func,
        *args,
        retryer_timeout=retryer_timeout,
        retryer_max_attempts=retryer_max_attempts,
        retryer_initial_backoff=retryer_initial_backoff,
        retryer_max_backoff=retryer_max_backoff,
        retryer_backoff_multiplier=retryer_backoff_multiplier,
        retryer_exceptions=retryer_exceptions,
        retryer_attempt_hook=retryer_attempt_hook,
        **kwargs,
    )
