# Laravel Database Migrations

Migrations are version control for the database schema. Each migration is a PHP class with an `up` method that applies a change and a `down` method that reverses it.

## Creating and running

Create a migration with `php artisan make:migration create_flights_table`. Apply every pending migration with `php artisan migrate`. See which have run with `php artisan migrate:status`.

## Rolling back

To undo the most recent batch of migrations, run `php artisan migrate:rollback`. Add `--step=1` to undo only the last migration. The command `php artisan migrate:fresh` is more drastic: it drops every table and then runs all migrations from the beginning, which is convenient in development but destroys all data.

## Defining columns

Inside `Schema::create('flights', function (Blueprint $table) { ... })` columns are declared with methods such as `$table->string('name')`, `$table->integer('seats')`, and `$table->timestamps()`.

## Indexes and foreign keys

Add an index with `->index()` or enforce uniqueness with `->unique()`. A foreign key is declared with `$table->foreignId('user_id')->constrained()`, which links the column to the `id` of the `users` table. Add `->cascadeOnDelete()` to remove child rows when the parent is deleted. MySQL requires an index on foreign key columns, and InnoDB creates one automatically if none exists.

## Good practice

Never edit a migration that has already run in production. Write a new migration that changes the table instead. Seeders and factories fill the tables with test data after migrating.
