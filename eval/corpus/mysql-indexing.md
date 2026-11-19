# MySQL Indexing

An index lets MySQL find rows without reading the whole table, in the same way a book index avoids reading every page. InnoDB indexes are B-trees.

## Clustered and secondary indexes

In InnoDB the primary key is the clustered index: the table rows themselves are stored in primary key order. Every secondary index stores the primary key value alongside its own columns, so a very wide primary key makes all secondary indexes larger.

## Composite indexes and the leftmost prefix rule

An index on several columns, such as `(first_name, last_name)`, can be used for queries that filter on `first_name`, or on `first_name` and `last_name` together. It cannot be used efficiently for a query that filters only on `last_name`, because the index is sorted by the leftmost column first. Put the most frequently filtered, most selective column first.

## Covering indexes

When an index contains every column a query needs, MySQL answers it from the index alone without touching the table. `EXPLAIN` shows this as `Using index` in the Extra column.

## Things that prevent index use

A leading wildcard, as in `LIKE '%son'`, cannot use a B-tree index, while `LIKE 'son%'` can. Wrapping an indexed column in a function, such as `WHERE YEAR(created_at) = 2024`, also prevents its use; rewrite the condition as a date range instead.

## The cost of indexes

Indexes make reads faster but every `INSERT`, `UPDATE`, and `DELETE` must also maintain each index, and indexes consume disk and memory. Create them for columns used in `WHERE`, `JOIN`, and `ORDER BY`, and drop ones that are never used. Create one with `CREATE INDEX idx_email ON users(email)`.
