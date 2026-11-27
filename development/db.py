"""Transactions for request handlers that read state before writing."""
from contextlib import contextmanager

from django.db import DEFAULT_DB_ALIAS, connections, transaction


@contextmanager
def write_transaction(using=DEFAULT_DB_ALIAS):
    database=connections[using]

    def begin_immediate(execute,sql,params,many,context):
        # SQLite ignores select_for_update(). Reserve its writer before reading,
        # so another writer cannot make a deferred transaction's upgrade fail.
        if database.vendor=='sqlite' and sql=='BEGIN':
            sql='BEGIN IMMEDIATE'
        return execute(sql,params,many,context)

    with database.execute_wrapper(begin_immediate):
        with transaction.atomic(using=using):
            yield
