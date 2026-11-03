"""Equivalent application write guards for PostgreSQL, without rewriting rows.

The trusted application supplies transaction-local actor state. This is not RLS
against a database operator who can change functions or application settings.
Historical imports may insert through an explicit management transaction only.
"""
from django.db import migrations


FUNCTIONS = [
    """
    CREATE OR REPLACE FUNCTION finance_actor() RETURNS bigint
    LANGUAGE sql STABLE AS $$
        SELECT COALESCE(NULLIF(current_setting('organiza.actor_id', true), ''), '0')::bigint;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_import_mode() RETURNS boolean
    LANGUAGE sql STABLE AS $$
        SELECT COALESCE(current_setting('organiza.import_mode', true) = 'on', false);
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_has_role(space_id uuid, allowed text[]) RETURNS boolean
    LANGUAGE sql STABLE AS $$
        SELECT EXISTS(SELECT 1 FROM finance_membership
                      WHERE workspace_id=space_id AND user_id=finance_actor() AND role=ANY(allowed));
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_guard_state() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP='INSERT' AND finance_import_mode() THEN RETURN NEW; END IF;
        IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'financial history cannot be deleted' USING ERRCODE='23514';
        ELSIF TG_OP='INSERT' THEN
            IF NOT finance_has_role(NEW.workspace_id, ARRAY['admin','collaborator']) THEN
                RAISE EXCEPTION 'unauthorized financial write' USING ERRCODE='23514';
            END IF;
            IF NEW.revision != 0 THEN
                RAISE EXCEPTION 'initial revision must be zero' USING ERRCODE='23514';
            END IF;
        ELSE
            IF NEW.workspace_id != OLD.workspace_id OR
               NOT finance_has_role(OLD.workspace_id, ARRAY['admin','collaborator']) THEN
                RAISE EXCEPTION 'unauthorized financial write' USING ERRCODE='23514';
            END IF;
            IF NEW.revision != OLD.revision+1 THEN
                RAISE EXCEPTION 'revision must advance exactly once' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_guard_workspace() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP='INSERT' AND finance_import_mode() THEN RETURN NEW; END IF;
        IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'financial history cannot be deleted' USING ERRCODE='23514';
        ELSIF TG_OP='INSERT' THEN
            IF NEW.created_by_id != finance_actor() OR finance_actor()=0 THEN
                RAISE EXCEPTION 'invalid workspace creator' USING ERRCODE='23514';
            END IF;
        ELSE
            IF NEW.id != OLD.id OR NEW.created_by_id != OLD.created_by_id OR
               NOT finance_has_role(OLD.id, ARRAY['admin']) THEN
                RAISE EXCEPTION 'unauthorized workspace change' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_guard_member() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE target_space uuid;
    BEGIN
        IF TG_OP='INSERT' AND finance_import_mode() THEN RETURN NEW; END IF;
        IF TG_OP='DELETE' THEN target_space:=OLD.workspace_id;
        ELSE target_space:=NEW.workspace_id; END IF;
        -- Serialize changes to different membership rows in the same space:
        -- two concurrent administrators cannot both demote the last pair.
        PERFORM 1 FROM finance_workspace WHERE id=target_space FOR UPDATE;
        IF TG_OP='INSERT' THEN
            IF NOT finance_has_role(target_space, ARRAY['admin']) AND NOT (
                NEW.user_id=finance_actor() AND NEW.role='admin' AND
                NOT EXISTS(SELECT 1 FROM finance_membership WHERE workspace_id=target_space) AND
                EXISTS(SELECT 1 FROM finance_workspace WHERE id=target_space AND created_by_id=finance_actor())
            ) THEN
                RAISE EXCEPTION 'administrator required' USING ERRCODE='23514';
            END IF;
        ELSE
            IF NOT finance_has_role(OLD.workspace_id, ARRAY['admin']) THEN
                RAISE EXCEPTION 'administrator required' USING ERRCODE='23514';
            END IF;
            IF TG_OP='UPDATE' THEN
                IF NEW.workspace_id != OLD.workspace_id OR NEW.user_id != OLD.user_id THEN
                    RAISE EXCEPTION 'administrator required' USING ERRCODE='23514';
                END IF;
            END IF;
            IF OLD.role='admin' AND
               (SELECT COUNT(*) FROM finance_membership WHERE workspace_id=OLD.workspace_id AND role='admin')<=1 THEN
                IF TG_OP='DELETE' THEN
                    RAISE EXCEPTION 'last administrator cannot be removed' USING ERRCODE='23514';
                ELSIF NEW.role!='admin' THEN
                    RAISE EXCEPTION 'last administrator cannot be removed' USING ERRCODE='23514';
                END IF;
            END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION finance_guard_record() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP='INSERT' THEN
            IF finance_import_mode() THEN RETURN NEW; END IF;
            IF NEW.actor_id != finance_actor() OR
               NOT finance_has_role(NEW.workspace_id, ARRAY['admin','collaborator']) THEN
                RAISE EXCEPTION 'unauthorized history write' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'financial history is append only' USING ERRCODE='23514';
    END;
    $$
    """,
]

TRIGGERS = [
    ('finance_state_guard', 'finance_financialstate', 'finance_guard_state'),
    ('finance_workspace_guard', 'finance_workspace', 'finance_guard_workspace'),
    ('finance_member_guard', 'finance_membership', 'finance_guard_member'),
    ('finance_audit_guard', 'finance_auditevent', 'finance_guard_record'),
    ('finance_operation_guard', 'finance_operation', 'finance_guard_record'),
]


def create_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for statement in FUNCTIONS:
        schema_editor.execute(statement)
    for name, table, function in TRIGGERS:
        schema_editor.execute(
            f'CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OR DELETE ON {table} '
            f'FOR EACH ROW EXECUTE FUNCTION {function}();'
        )


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for name, table, function in TRIGGERS:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {name} ON {table};')
    for name in ('finance_guard_record()', 'finance_guard_member()', 'finance_guard_workspace()',
                 'finance_guard_state()', 'finance_has_role(uuid, text[])', 'finance_import_mode()', 'finance_actor()'):
        schema_editor.execute(f'DROP FUNCTION IF EXISTS {name};')


class Migration(migrations.Migration):
    dependencies = [('finance', '0002_database_guards')]
    operations = [migrations.RunPython(create_postgres_guards, remove_postgres_guards)]
