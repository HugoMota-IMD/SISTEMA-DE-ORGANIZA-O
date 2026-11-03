"""Do not send SQL details, request bodies, secrets or financial rows to logs."""
import logging


class SafeErrorFilter(logging.Filter):
    def filter(self, record):
        status = getattr(record, 'status_code', None)
        record.msg = 'Falha operacional; detalhes sensíveis omitidos.' + (f' HTTP {status}.' if isinstance(status, int) else '')
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True
