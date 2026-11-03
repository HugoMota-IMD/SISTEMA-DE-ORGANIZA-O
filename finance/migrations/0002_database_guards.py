from django.db import migrations

SQL = """
CREATE TRIGGER finance_state_insert BEFORE INSERT ON finance_financialstate BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=NEW.workspace_id AND user_id=finance_actor() AND role IN ('admin','collaborator')) THEN RAISE(ABORT,'unauthorized financial write') END;
 SELECT CASE WHEN NEW.revision != 0 THEN RAISE(ABORT,'initial revision must be zero') END;
END;
CREATE TRIGGER finance_state_update BEFORE UPDATE ON finance_financialstate BEGIN
 SELECT CASE WHEN NEW.workspace_id != OLD.workspace_id OR NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=OLD.workspace_id AND user_id=finance_actor() AND role IN ('admin','collaborator')) THEN RAISE(ABORT,'unauthorized financial write') END;
 SELECT CASE WHEN NEW.revision != OLD.revision+1 THEN RAISE(ABORT,'revision must advance exactly once') END;
END;
CREATE TRIGGER finance_state_delete BEFORE DELETE ON finance_financialstate BEGIN SELECT RAISE(ABORT,'financial history cannot be deleted'); END;
CREATE TRIGGER finance_workspace_insert BEFORE INSERT ON finance_workspace BEGIN
 SELECT CASE WHEN NEW.created_by_id != finance_actor() OR finance_actor()=0 THEN RAISE(ABORT,'invalid workspace creator') END;
END;
CREATE TRIGGER finance_workspace_update BEFORE UPDATE ON finance_workspace BEGIN
 SELECT CASE WHEN NEW.id != OLD.id OR NEW.created_by_id != OLD.created_by_id OR NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=OLD.id AND user_id=finance_actor() AND role='admin') THEN RAISE(ABORT,'unauthorized workspace change') END;
END;
CREATE TRIGGER finance_member_insert BEFORE INSERT ON finance_membership BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=NEW.workspace_id AND user_id=finance_actor() AND role='admin') AND NOT (NEW.user_id=finance_actor() AND NEW.role='admin' AND NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=NEW.workspace_id) AND EXISTS(SELECT 1 FROM finance_workspace WHERE id=NEW.workspace_id AND created_by_id=finance_actor())) THEN RAISE(ABORT,'administrator required') END;
END;
CREATE TRIGGER finance_member_update BEFORE UPDATE ON finance_membership BEGIN
 SELECT CASE WHEN NEW.workspace_id != OLD.workspace_id OR NEW.user_id != OLD.user_id OR NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=OLD.workspace_id AND user_id=finance_actor() AND role='admin') THEN RAISE(ABORT,'administrator required') END;
 SELECT CASE WHEN OLD.role='admin' AND NEW.role!='admin' AND (SELECT COUNT(*) FROM finance_membership WHERE workspace_id=OLD.workspace_id AND role='admin')<=1 THEN RAISE(ABORT,'last administrator cannot be removed') END;
END;
CREATE TRIGGER finance_member_delete BEFORE DELETE ON finance_membership BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=OLD.workspace_id AND user_id=finance_actor() AND role='admin') THEN RAISE(ABORT,'administrator required') END;
 SELECT CASE WHEN OLD.role='admin' AND (SELECT COUNT(*) FROM finance_membership WHERE workspace_id=OLD.workspace_id AND role='admin')<=1 THEN RAISE(ABORT,'last administrator cannot be removed') END;
END;
CREATE TRIGGER finance_audit_insert BEFORE INSERT ON finance_auditevent BEGIN
 SELECT CASE WHEN NEW.actor_id != finance_actor() OR NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=NEW.workspace_id AND user_id=finance_actor() AND role IN ('admin','collaborator')) THEN RAISE(ABORT,'unauthorized audit') END;
END;
CREATE TRIGGER finance_audit_update BEFORE UPDATE ON finance_auditevent BEGIN SELECT RAISE(ABORT,'audit is append only'); END;
CREATE TRIGGER finance_audit_delete BEFORE DELETE ON finance_auditevent BEGIN SELECT RAISE(ABORT,'audit is append only'); END;
CREATE TRIGGER finance_operation_insert BEFORE INSERT ON finance_operation BEGIN
 SELECT CASE WHEN NEW.actor_id != finance_actor() OR NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=NEW.workspace_id AND user_id=finance_actor() AND role IN ('admin','collaborator')) THEN RAISE(ABORT,'unauthorized operation') END;
END;
CREATE TRIGGER finance_operation_update BEFORE UPDATE ON finance_operation BEGIN SELECT RAISE(ABORT,'operations are immutable'); END;
CREATE TRIGGER finance_operation_delete BEFORE DELETE ON finance_operation BEGIN SELECT RAISE(ABORT,'operations are immutable'); END;
"""

NAMES = ['state_insert','state_update','state_delete','workspace_insert','workspace_update','member_insert','member_update','member_delete','audit_insert','audit_update','audit_delete','operation_insert','operation_update','operation_delete']


def create_sqlite_guards(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        for statement in schema_editor.connection.ops.prepare_sql_script(SQL):
            schema_editor.execute(statement)


def remove_sqlite_guards(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        for name in NAMES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS finance_{name};')

class Migration(migrations.Migration):
    dependencies = [('finance', '0001_initial')]
    operations = [migrations.RunPython(create_sqlite_guards, remove_sqlite_guards)]
