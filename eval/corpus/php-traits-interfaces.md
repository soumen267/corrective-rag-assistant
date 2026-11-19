# Traits and Interfaces in PHP

PHP classes can extend only one parent class, so the language provides other tools for sharing and standardising behaviour.

## Interfaces

An interface is a contract. It declares method signatures that implementing classes must provide, but it holds no instance state. A class may implement many interfaces: `class Report implements Printable, Exportable`. Interfaces let code depend on behaviour instead of a concrete class.

## Abstract classes

An abstract class can contain both implemented methods and abstract methods that subclasses must supply. Unlike an interface it can hold properties and state, but a class can extend only one of them.

## Traits

A trait is a bundle of methods and properties for horizontal code reuse, added to a class with `use LoggerTrait;`. A trait cannot be instantiated directly. It only works once a class uses it.

If two traits define a method with the same name, PHP raises a conflict. Resolve it inside the `use` block:

```php
class Report {
    use A, B {
        A::hello insteadof B;
        B::hello as helloFromB;
    }
}
```

The `insteadof` keyword picks which trait's method wins, and `as` gives the other method an alias so both remain available.

## Choosing between them

Use an interface to describe what an object can do, an abstract class for a shared base with state, and a trait to reuse concrete code across unrelated classes.
