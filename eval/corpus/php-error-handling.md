# Error Handling in PHP

Since PHP 7, most failures are reported as exceptions that can be caught.

## Throwable, Error and Exception

Both `Error` and `Exception` implement the `Throwable` interface. Exceptions represent problems in application logic that code may reasonably recover from, such as invalid input or a missing file. Errors represent engine-level problems, for example `TypeError`, `ParseError`, and `DivisionByZeroError`. To catch everything, catch `Throwable`; catching only `Exception` will miss errors.

## try, catch and finally

Wrap risky code in `try`. Add one or more `catch` blocks, ordered from most specific to least specific. A `finally` block always runs, even when an exception is thrown or the function returns, so it is the place to close files and release locks.

## Strict types

Adding `declare(strict_types=1);` at the top of a file turns off automatic scalar type juggling. Passing the string `"5"` to a function that expects an `int` then throws a `TypeError` instead of silently converting.

## The match expression

PHP 8's `match` expression compares strictly and, unlike `switch`, throws an `UnhandledMatchError` when no arm matches and there is no default arm.

## Production configuration

Set `display_errors=Off` and `log_errors=On` in production so visitors never see stack traces or file paths. Register a global handler with `set_exception_handler()` to log anything that was not caught.
