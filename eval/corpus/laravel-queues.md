# Laravel Queues

Queues let an application defer slow work, such as sending email or resizing images, so web requests return quickly.

## Jobs and dispatching

Create a job class with `php artisan make:job ProcessPodcast`. A job that implements the `ShouldQueue` interface is pushed onto a queue instead of running immediately. Dispatch it with `ProcessPodcast::dispatch($podcast)`.

## Connections and drivers

The queue backend is chosen with the `QUEUE_CONNECTION` variable in the `.env` file. Supported drivers include `database`, `redis`, `sqs`, and `sync`, which runs jobs immediately and is useful for local testing. The database driver needs a jobs table created by a migration. The Redis driver reads its server settings from `REDIS_HOST` and `REDIS_PORT` in `.env`, the same values the cache uses.

## Running workers

A worker is a long-running process started with `php artisan queue:work`. Add options such as `--tries=3` to attempt each job up to three times and `--backoff=10` to wait ten seconds between attempts. A production server should run the worker under a process monitor such as Supervisor so it restarts automatically if it stops.

## Deploying new code

Workers keep the application in memory, so they do not see new code on their own. After every deployment run `php artisan queue:restart`. It tells workers to exit gracefully once their current job finishes, and the process monitor starts fresh ones.

## Failed jobs

Jobs that exhaust their attempts are stored in the `failed_jobs` table. List them with `php artisan queue:failed` and put them back on the queue with `php artisan queue:retry all`. Laravel Horizon provides a dashboard for Redis queues.
