# Eloquent Relationships

Eloquent models describe how database tables relate to each other through relationship methods.

## Common relationship types

- `hasOne` and `belongsTo` model a one-to-one link, such as a user and their profile.
- `hasMany` and `belongsTo` model a one-to-many link, such as a post with many comments.
- `belongsToMany` models a many-to-many link, such as users and roles. It needs an intermediate pivot table. By default the pivot table name is built from the two model names in alphabetical order, singular, joined by an underscore, so users and roles use `role_user`. Extra pivot columns are exposed with `withPivot()` and timestamps with `withTimestamps()`.
- `hasManyThrough` reaches a distant relation through an intermediate model, such as a country's posts through its users.
- Polymorphic relations such as `morphMany` let one model, for example a comment, belong to several other model types.

## The N+1 query problem

Looping over 100 posts and reading `$post->author` for each one runs one query for the posts plus 100 more for the authors. This is the N+1 problem. Eager loading fixes it by fetching all related rows in one extra query: `Post::with('author')->get()`. Nested relations use dot notation, such as `with('author.profile')`.

Calling `Model::preventLazyLoading()` during development throws an exception whenever a relationship is lazy loaded, which helps find N+1 problems before production.

## Counting related rows

`withCount('comments')` adds a `comments_count` attribute to each model without loading the comments themselves, using a single subquery.
