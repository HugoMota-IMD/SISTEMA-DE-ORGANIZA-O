from django.apps import AppConfig
from django.db.backends.signals import connection_created

class FinanceConfig(AppConfig):
    name = 'finance'

    def ready(self):
        from .security import register_connection
        connection_created.connect(register_connection, dispatch_uid='finance_sqlite_actor')
