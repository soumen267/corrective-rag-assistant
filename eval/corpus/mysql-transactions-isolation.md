# MySQL Transactions and Isolation Levels

A transaction groups several statements so they succeed or fail together. InnoDB provides ACID guarantees: atomicity, consistency, isolation, and durability.

## Controlling transactions

Start one with `START TRANSACTION`, then finish with `COMMIT` to save the changes or `ROLLBACK` to discard them. By default `autocommit` is on, so each statement outside an explicit transaction commits immediately. `SAVEPOINT` marks a point inside a transaction that can be rolled back to without abandoning everything.

## Isolation levels

Isolation controls what one transaction can see of another's uncommitted or recent work. The four standard levels are:

- `READ UNCOMMITTED` can read uncommitted data (dirty reads).
- `READ COMMITTED` sees only committed data, but repeated reads may return different values.
- `REPEATABLE READ` guarantees the same rows are returned for repeated reads in one transaction. This is the default level for InnoDB unless you configure otherwise.
- `SERIALIZABLE` is the strictest and makes transactions behave as if they ran one after another.

Change the level for the next transaction with `SET TRANSACTION ISOLATION LEVEL READ COMMITTED`. InnoDB implements consistent reads with multi-version concurrency control (MVCC), using undo logs to show each transaction a snapshot.

## Locking reads

To read rows and prevent anyone else from changing them until you commit, use `SELECT ... FOR UPDATE`, which takes exclusive row locks. `SELECT ... FOR SHARE` takes shared locks that allow other readers but block writers. Locks are released at `COMMIT` or `ROLLBACK`.
