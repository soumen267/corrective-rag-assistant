# Laravel Request Validation

Laravel validates incoming data before it reaches business logic.

## Inline validation

Call `$request->validate()` inside a controller with an array of rules:

```php
$validated = $request->validate([
    'title' => 'required|unique:posts|max:255',
    'body'  => 'required',
]);
```

Rules are separated by a pipe character. Common rules include `required`, `email`, `max:255`, and `unique:users,email`, which checks that the value does not already exist in the `email` column of the `users` table. The method returns only the validated fields.

## What happens on failure

For an ordinary web form, a failed validation redirects the user back to the previous page, flashes the error messages to the session, and keeps the old input. In a view the errors are available in the `$errors` variable and the `@error('title')` Blade directive. When the request is an AJAX or JSON API call (it expects JSON), Laravel does not redirect. It returns an HTTP 422 Unprocessable Content response containing the validation messages as JSON.

## Form requests

Complex validation belongs in a dedicated class created with `php artisan make:request StorePostRequest`. It has a `rules()` method that returns the rule array and an `authorize()` method that returns a boolean deciding whether the user may make the request at all. Type-hint the class in the controller method and Laravel validates automatically before the method runs.

## Custom messages

Override the default wording by returning an array from a `messages()` method on the form request.
