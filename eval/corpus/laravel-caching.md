# Laravel Caching

Caching stores the result of expensive operations so later requests are faster.

## The Cache facade

`Cache::remember('users', 600, function () { return User::all(); })` returns the cached value if it exists. Otherwise it runs the closure, stores the result for 600 seconds (ten minutes), and returns it. `Cache::forever()` stores a value with no expiry and `Cache::forget('users')` deletes one key.

## Cache stores

The default store is selected with the `CACHE_STORE` variable in `.env`. Older Laravel versions used `CACHE_DRIVER`. Available stores include `file`, `database`, `redis`, `memcached`, and `array`, which only lasts for the current request and is used in tests. When Redis is the store, its connection is configured with `REDIS_HOST`, `REDIS_PASSWORD`, and `REDIS_PORT` in `.env`.

## Cache tags and locks

Cache tags group related items so they can be flushed together, but tags are not supported by the `file` or `database` stores. Atomic locks, created with `Cache::lock('report', 10)`, stop two processes from running the same critical section at once.

## Clearing and framework caches

`php artisan cache:clear` empties the application cache. Separate commands cache framework internals for production: `php artisan config:cache` merges all configuration files into one, and `php artisan route:cache` compiles the route list. Both must be re-run after configuration or route changes.
