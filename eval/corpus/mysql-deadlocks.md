# MySQL Deadlocks

A deadlock happens when two transactions each hold a lock the other needs, so neither can continue. Transaction A locks row 1 and wants row 2, while transaction B locks row 2 and wants row 1.

## How InnoDB responds

InnoDB detects deadlocks automatically (`innodb_deadlock_detect` is on by default). It rolls back one transaction, the victim, usually the one that changed the fewest rows, and lets the other proceed. The victim's client receives error 1213 with SQLSTATE 40001 and the message "Deadlock found when trying to get lock; try restarting transaction".

## What the application should do

A deadlock is not a bug that crashes the database; it is an expected event that the application must handle. Catch the error and retry the whole transaction from the start. Laravel's `DB::transaction($callback, 5)` does this: the second argument is the number of attempts, and the closure is rerun if a deadlock occurs.

## Diagnosing

Run `SHOW ENGINE INNODB STATUS` and read the `LATEST DETECTED DEADLOCK` section to see both transactions, the statements involved, and which locks they held and waited for.

## Prevention

- Access tables and rows in the same order in every transaction.
- Keep transactions short and avoid user interaction while they are open.
- Add proper indexes so queries lock fewer rows.

## Lock wait timeouts

A different error occurs when a transaction simply waits too long for a lock held by another. After `innodb_lock_wait_timeout` seconds (50 by default) it fails with error 1205, "Lock wait timeout exceeded". Unlike a deadlock, only the statement is rolled back by default, not the whole transaction.
