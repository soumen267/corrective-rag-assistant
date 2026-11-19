# MySQL Replication

Replication copies data from one MySQL server, the source, to one or more replicas. Before MySQL 8.0.22 these were called master and slave.

## How it works

The source records every data change in its binary log. Each replica runs two threads. The receiver (I/O) thread copies binary log events from the source into a local relay log. The applier (SQL) thread then reads the relay log and executes the changes, so the replica stays in sync. The default `binlog_format` is `ROW`, which logs the changed rows themselves.

## Checking health

Run `SHOW REPLICA STATUS` on a replica (older versions use `SHOW SLAVE STATUS`). Important fields are whether the I/O and SQL threads are running and `Seconds_Behind_Source`, which estimates replication lag. A growing lag means the replica cannot apply changes as fast as the source produces them.

## Synchronous behaviour

Replication is asynchronous by default: the source commits without waiting for any replica, so a crash can lose the most recent transactions. Semi-synchronous replication makes the source wait until at least one replica acknowledges receiving each transaction, reducing that risk at the cost of some latency.

## GTIDs

Global transaction identifiers give every transaction a unique ID, which makes it much easier to point a replica at a new source or recover after a failover.

## Typical uses

Replicas scale reads: the application sends writes to the source and spreads read-only queries across replicas. They are also convenient for taking backups without loading the primary. Replication does not scale writes, because every replica must still apply every change. Set `read_only=ON` on replicas to prevent accidental writes.
