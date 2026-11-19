# Dependency Injection in PHP

Dependency injection (DI) means a class receives the objects it needs from the outside instead of creating them itself. A class that writes `new MySqlDatabase()` inside its own methods is tightly coupled to that implementation. A class that receives a database object through its constructor is not.

## Why it matters

Hard-coded collaborators make unit testing difficult, because a test cannot replace the real database or mailer with a fake one. With injection, a test passes in a mock object and verifies behaviour without touching real services. DI also lowers coupling: the class depends on an interface, so the implementation can change without editing the class.

## Constructor injection

Constructor injection is the preferred form. Dependencies are listed as typed constructor parameters, which makes them explicit and guarantees the object is never half-built:

```php
class OrderService
{
    public function __construct(private PaymentGateway $gateway) {}
}
```

Setter injection and method injection also exist, but they allow objects in an incomplete state.

## Containers and PSR-11

Wiring many objects by hand becomes tedious, so frameworks provide a dependency injection container. The PSR-11 standard defines `Psr\Container\ContainerInterface` with two methods, `get($id)` and `has($id)`, so libraries can work with any compliant container.

## The service locator anti-pattern

Passing the container itself into a class and calling `get()` inside it hides what the class really depends on. This is the service locator anti-pattern. Prefer declaring explicit constructor parameters.
