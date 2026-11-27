import sqlite3
import tempfile
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import connection,connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.test import TransactionTestCase

from .db import write_transaction
from .models import Food


@skipUnless(connection.vendor=='sqlite','SQLite transaction locking regression.')
class SQLiteConcurrencyTests(TransactionTestCase):
    def test_concurrent_read_then_write_waits_before_reading_and_keeps_both_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'concurrent.sqlite3')
            with closing(sqlite3.connect(path)) as setup:
                setup.execute('CREATE TABLE counter (value INTEGER NOT NULL)')
                setup.execute('INSERT INTO counter VALUES (0)')
                setup.commit()
            writer_ready=Event();second_started=Event();second_read=Event();release=Event()

            def increment(alias,first=False):
                settings=dict(connection.settings_dict)
                settings.update(NAME=path,OPTIONS={'timeout':5})
                database=DatabaseWrapper(settings,alias=alias)
                connections[alias]=database
                try:
                    if not first:
                        if not writer_ready.wait(5): raise AssertionError('First writer never acquired the transaction.')
                        second_started.set()
                    with write_transaction(using=alias):
                        with database.cursor() as cursor:
                            cursor.execute('SELECT value FROM counter')
                            value=cursor.fetchone()[0]
                            if first:
                                writer_ready.set()
                                if not release.wait(5): raise AssertionError('First writer was never released.')
                            else:
                                second_read.set()
                            cursor.execute('UPDATE counter SET value=%s',[value+1])
                    return value
                finally:
                    database.close()
                    del connections[alias]

            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(increment,'first_writer',True)
                second=pool.submit(increment,'second_writer')
                try:
                    self.assertTrue(second_started.wait(5))
                    # A deferred BEGIN would let this read through immediately,
                    # leaving the second transaction with a stale snapshot.
                    self.assertFalse(second_read.wait(.2))
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=5),0)
                self.assertEqual(second.result(timeout=5),1)
            with closing(sqlite3.connect(path)) as check:
                self.assertEqual(check.execute('SELECT value FROM counter').fetchone()[0],2)

    def test_detail_get_does_not_start_transaction_and_post_reserves_writer_first(self):
        user=User.objects.create_superuser('concurrent-detail-editor')
        food=Food.objects.create(name='Concurrent detail',stage='launch',owner=user)
        self.client.force_login(user)
        statements=[]
        connection.ensure_connection()
        connection.connection.set_trace_callback(statements.append)
        try:
            self.assertEqual(self.client.get('/food/%s/'%food.pk).status_code,200)
            self.assertFalse(any(sql.startswith('BEGIN') for sql in statements))
            statements.clear()
            self.assertEqual(self.client.post('/food/%s/'%food.pk,{'action':'comment','comment':'Saved once'}).status_code,302)
        finally:
            connection.connection.set_trace_callback(None)
        begin=statements.index('BEGIN IMMEDIATE')
        read=next(index for index,sql in enumerate(statements) if sql.startswith('SELECT') and 'FROM "development_food"' in sql)
        self.assertLess(begin,read)
        self.assertEqual(food.activities.filter(text='Saved once').count(),1)

    def test_failed_write_rolls_back_all_changes(self):
        user=User.objects.create_superuser('rollback-detail-editor')
        food=Food.objects.create(name='Before rollback',owner=user)
        with self.assertRaisesRegex(ValueError,'rollback'):
            with write_transaction():
                Food.objects.filter(pk=food.pk).update(name='After rollback')
                raise ValueError('rollback')
        food.refresh_from_db();self.assertEqual(food.name,'Before rollback')
