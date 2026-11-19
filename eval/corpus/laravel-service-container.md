# Laravel Service Container

The service container is Laravel's inversion-of-control container. It is a tool for managing class dependencies and performing dependency injection. Most of the framework, including controllers, event listeners, and middleware, is resolved through it.

## Automatic resolution

When a class has no special binding, the container builds it by reading the type hints on its constructor with reflection. If a controller's constructor asks for a `UserRepository`, the container creates one and injects it, recursively resolving that class's own dependencies as well. No configuration is required for concrete classes.

## Binding

Bindings are registered inside a service provider. `$this->app->bind(Interface::class, Implementation::class)` creates a new instance each time. `$this->app->singleton(...)` creates the object once and reuses it for the whole application lifetime. `$this->app->scoped(...)` reuses it within a single request or queue job, which matters for long-running servers such as Octane.

Binding an interface to an implementation lets code depend on an abstraction while the container decides which concrete class to supply.

## Contextual binding

Sometimes two classes need different implementations of the same interface. Contextual binding handles this: `$this->app->when(PhotoController::class)->needs(Filesystem::class)->give(...)`.

## Service providers

Every provider has two methods. `register()` is only for binding things into the container and must not use other services. `boot()` runs after all providers have registered, so it may safely use any service. Providers are listed in `bootstrap/providers.php`.

## Resolving manually

Outside of constructors, the `app()` and `resolve()` helpers or `App::make()` fetch an instance from the container.
