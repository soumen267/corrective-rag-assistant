# Laravel Middleware

Middleware filters the HTTP requests that enter a Laravel application. Each middleware can inspect the request, reject it, modify it, or pass it deeper into the application. The built-in `auth` middleware, for example, redirects unauthenticated users to the login page, while `throttle` limits how many requests a client may send per minute.

## Creating middleware

Generate a middleware class with `php artisan make:middleware EnsureTokenIsValid`. The class contains a `handle($request, Closure $next)` method. Calling `$next($request)` passes the request to the next layer; returning a redirect or response early stops the request from reaching the controller.

## Registering middleware

In Laravel 11 and later, middleware is configured in `bootstrap/app.php` through the `withMiddleware` callback. Use `$middleware->append()` for global middleware that runs on every request, `$middleware->alias()` to give a middleware a short name, and group middleware such as `web` and `api` for related routes. A route can opt in with `Route::get('/profile', ...)->middleware('auth')`.

## Middleware parameters

Extra values can be passed after a colon, for example `->middleware('role:editor')`. The value arrives as the third argument of `handle`, so a middleware can check that the user has the editor role.

## Terminable middleware

Sometimes work must happen after the HTTP response has already been sent to the browser, such as writing session data or logging. Define a `terminate($request, $response)` method on the middleware. Laravel calls it once the response has been sent, so slow follow-up work does not delay the user.
