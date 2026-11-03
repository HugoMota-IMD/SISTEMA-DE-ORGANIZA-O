import uuid
from django.conf import settings
from django.db import models

class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class Membership(models.Model):
    workspace = models.ForeignKey(Workspace, related_name='memberships', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, choices=[('admin','Administrador'),('collaborator','Colaborador'),('reader','Leitor')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace','user'], name='unique_space_member'), models.CheckConstraint(condition=models.Q(role__in=['admin','collaborator','reader']), name='valid_member_role')]

class FinancialState(models.Model):
    workspace = models.OneToOneField(Workspace, primary_key=True, related_name='financial_state', on_delete=models.CASCADE)
    document = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

class AuditEvent(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class Operation(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    request_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace','request_id'], name='unique_finance_request')]

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()

class UserAccessEvent(models.Model):
    """Technical account approvals are separate from financial workspace audit."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='access_changes_made', on_delete=models.PROTECT)
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='access_changes_received', on_delete=models.PROTECT)
    before_active = models.BooleanField()
    after_active = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
