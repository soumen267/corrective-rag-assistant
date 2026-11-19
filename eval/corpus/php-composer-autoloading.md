# Composer Autoloading in PHP

Composer is PHP's dependency manager. Besides downloading packages, it generates an autoloader so classes are loaded on demand without manual `require` statements.

## Using the autoloader

Include `vendor/autoload.php` once at the start of the application. After that, referencing a class triggers Composer to find and load its file.

## PSR-4 mapping

PSR-4 maps a namespace prefix to a directory. In `composer.json`:

```json
"autoload": {
    "psr-4": { "App\\": "app/" }
}
```

With this mapping, the class `App\Models\User` is expected in `app/Models/User.php`. The remainder of the namespace after the prefix becomes the folder path, and the class name becomes the file name.

## Regenerating the autoloader

After changing the `autoload` section or adding classes to a classmap, run `composer dump-autoload`. Adding `-o` produces an optimized classmap, which makes production lookups faster because PHP no longer has to search directories. Composer also supports `classmap` entries and `files` entries, which are always included on every request.

## install versus update

`composer install` installs the exact versions recorded in `composer.lock`, giving every environment identical dependencies. `composer update` resolves the newest versions allowed by `composer.json` and rewrites the lock file. Commit `composer.lock` for applications so deployments are reproducible.
