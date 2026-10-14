"""Offline deployment failure drills; never connect to the production server."""

import hashlib
import importlib.util
import io
import json
import os
import pwd
import sqlite3
import tarfile
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = load("update")
server = load("update_server")


@contextmanager
def database(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        yield connection


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def make_release(self, name):
        root = self.root / "releases" / name
        for relative in [
            "backend/app/db.py",
            "backend/migrations/env.py",
            "backend/migrations/versions/0001_initial.py",
            "backend/alembic.ini",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "scripts/run.py",
            "config/fixture.json",
            "frontend/dist/index.html",
            "deploy/update.sh",
            "README.md",
        ]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        return root

    def make_db(self):
        db = self.root / "stock-panel.sqlite3"
        with database(db) as connection:
            connection.execute("CREATE TABLE quotes (price INTEGER)")
            connection.execute("INSERT INTO quotes VALUES (100)")
        return db

    def archive_with(self, name, kind=tarfile.REGTYPE):
        archive = self.root / "app.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = 3 if kind == tarfile.REGTYPE else 0
            member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
            output.addfile(member, io.BytesIO(b"abc") if member.size else None)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_package_excludes_local_secrets_and_database(self):
        root = self.make_release("candidate")
        for relative in [
            ".env",
            "data/local.sqlite3",
            ".ssh/id_ed25519",
            "backend/app/.env",
            "backend/.venv/token",
        ]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("secret")
        archive = self.root / "app.tar.gz"
        digest = client.package(root, archive)
        target = self.root / "unpacked"
        server.extract(archive, target, digest)
        self.assertEqual((target / "frontend/dist/index.html").read_text(), "fixture\n")
        self.assertFalse((target / ".env").exists())
        self.assertFalse((target / "data").exists())
        self.assertFalse((target / "backend/app/.env").exists())

    def test_rejects_unexpected_secret_and_symlink(self):
        root = self.make_release("candidate")
        secret = root / "config/private.key"
        secret.write_text("secret")
        with self.assertRaises(RuntimeError):
            client.package(root, self.root / "app.tar.gz")
        secret.unlink()
        (root / "config/external").symlink_to(self.root)
        with self.assertRaises(RuntimeError):
            client.package(root, self.root / "app.tar.gz")

    def test_archive_rejects_traversal_symlinks_and_secrets(self):
        for name, kind in [
            ("backend/../../escape", tarfile.REGTYPE),
            ("/etc/escape", tarfile.REGTYPE),
            ("backend/link", tarfile.SYMTYPE),
            ("backend/.env", tarfile.REGTYPE),
            ("config/live.sqlite3", tarfile.REGTYPE),
        ]:
            with self.subTest(name=name):
                archive, digest = self.archive_with(name, kind)
                with self.assertRaises(RuntimeError):
                    server.extract(archive, self.root / "unpacked", digest)
                self.assertFalse((self.root / "unpacked").exists())

    def test_rejects_corrupt_upload_before_extraction(self):
        archive, _ = self.archive_with("backend/app/example.py")
        with self.assertRaises(RuntimeError):
            server.extract(archive, self.root / "unpacked", "0" * 64)
        self.assertFalse((self.root / "unpacked").exists())

    def test_schema_guard_allows_code_change_but_rejects_migrations(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (candidate / "backend/app/api.py").write_text("new business logic")
        server.guard_schema(previous, candidate)
        (candidate / "backend/migrations/versions/0002_new.py").write_text("new schema")
        with self.assertRaisesRegex(RuntimeError, "迁移"):
            server.guard_schema(previous, candidate)

    def test_backup_is_consistent_and_never_overwrites(self):
        db = self.make_db()
        backup = self.root / "backup.sqlite3"
        server.backup_database(db, backup)
        with database(backup) as connection:
            self.assertEqual(connection.execute("SELECT price FROM quotes").fetchall(), [(100,)])
        with self.assertRaises(FileExistsError):
            server.backup_database(db, backup)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_lock_rejects_concurrent_deploy(self):
        lock = self.root / "update.lock"
        with server.exclusive(lock), self.assertRaisesRegex(RuntimeError, "任务正在运行"):
            with server.exclusive(lock):
                self.fail("concurrent update acquired lock")

    def test_successful_activation_switches_only_code(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        db = self.make_db()
        before = db.read_bytes()
        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "systemctl") as service,
            patch.object(server, "health") as health,
        ):
            server.activate(previous, candidate)
        self.assertEqual((self.root / "current").resolve(), candidate)
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(service.call_args_list[0].args, ("stop", server.SERVICE))
        health.assert_called_once_with(candidate)

    def test_failed_health_restores_and_validates_old_code_without_db_restore(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        db = self.make_db()
        before = db.read_bytes()
        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "systemctl"),
            patch.object(
                server, "health", side_effect=[RuntimeError("bad new version"), None]
            ) as health,
        ):
            with self.assertRaisesRegex(RuntimeError, "bad new version"):
                server.activate(previous, candidate)
        self.assertEqual((self.root / "current").resolve(), previous)
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual([call.args[0] for call in health.call_args_list], [candidate, previous])

    def test_failed_service_start_also_restores_previous(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        results = [None, RuntimeError("start failed"), None, None, None]
        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "systemctl", side_effect=results),
            patch.object(server, "health"),
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                server.activate(previous, candidate)
        self.assertEqual((self.root / "current").resolve(), previous)

    def test_actual_db_revision_must_match_code_head(self):
        db = self.make_db()
        with database(db) as connection:
            connection.execute("CREATE TABLE alembic_version (version_num TEXT)")
            connection.execute("INSERT INTO alembic_version VALUES ('old')")
        result = type("Result", (), {"stdout": json.dumps(["new"])})()
        with (
            patch.object(server, "run", return_value=result),
            self.assertRaisesRegex(RuntimeError, "数据库版本"),
        ):
            server.guard_database(self.root, db)

    def exercise_deploy(self, sync_state, activate_error=None, migrate=False):
        previous = self.make_release("previous")
        self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        self.make_db()
        (self.root / "backups").mkdir()
        (self.root / "stock-panel.sync.lock").touch()
        env_file = self.root / "server.env"
        env_file.write_text(f"STOCK_DB_PATH={self.root / 'stock-panel.sqlite3'}\n")
        archive, digest = self.archive_with("backend/app/example.py")
        states = {
            server.SERVICE: "active",
            server.TIMER: "active",
            "stock-panel-sync.service": sync_state,
        }
        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "DATA", self.root),
            patch.object(server, "ENV_FILE", env_file),
            patch.object(server.os, "geteuid", return_value=0),
            patch.object(server, "active", side_effect=states.__getitem__),
            patch.object(server, "extract"),
            patch.object(server, "run"),
            patch.object(server, "configure_cache"),
            patch.object(server, "guard_database"),
            patch.object(server, "migration_plan", return_value=["new"]),
            patch.object(server, "rehearse_migration"),
            patch.object(server, "systemctl") as service,
            patch.object(server, "activate", side_effect=activate_error) as activate,
            patch.object(
                server, "activate_with_migration", side_effect=activate_error
            ) as migration,
        ):
            try:
                server.deploy("candidate", archive, digest, migrate=migrate)
            except RuntimeError as error:
                return service, migration if migrate else activate, str(error)
        return service, migration if migrate else activate, None

    def test_running_sync_aborts_without_switch_and_restores_timer(self):
        service, activate, error = self.exercise_deploy("activating")
        self.assertIn("行情同步正在运行", error)
        activate.assert_not_called()
        self.assertEqual(
            [call.args for call in service.call_args_list],
            [("stop", server.TIMER), ("start", server.TIMER)],
        )
        self.assertFalse(list((self.root / "backups").iterdir()))

    def test_activation_failure_keeps_backup_and_restores_timer(self):
        service, activate, error = self.exercise_deploy(
            "inactive", RuntimeError("activation failed")
        )
        self.assertEqual(error, "activation failed")
        activate.assert_called_once()
        self.assertEqual(service.call_args_list[-1].args, ("start", server.TIMER))
        self.assertTrue((self.root / "backups/before-update-candidate.sqlite3").exists())

    def test_success_records_previous_version_and_backup(self):
        service, activate, error = self.exercise_deploy("failed")
        self.assertIsNone(error)
        activate.assert_called_once()
        result = json.loads((self.root / "releases/candidate/deployment.json").read_text())
        self.assertEqual(result["previous"], str(self.root / "releases/previous"))
        self.assertTrue(Path(result["backup"]).exists())
        self.assertEqual(service.call_args_list[-1].args, ("start", server.TIMER))

    def test_client_detaches_and_waits_for_server_result(self):
        archive, digest = self.archive_with("backend/app/example.py")
        states = iter(
            [
                "ActiveState=inactive\nSubState=dead\nResult=success\n",
                "ActiveState=activating\nSubState=start\nResult=success\n",
                "ActiveState=active\nSubState=exited\nResult=success\n",
            ]
        )
        commands = []

        def command(args, **kwargs):
            commands.append(args)
            output = next(states) if "show" in args else ""
            return SimpleNamespace(stdout=output)

        with patch.object(client.time, "sleep"):
            client.publish(
                SimpleNamespace(command=command),
                archive.parent,
                "20261013-150000-12345678",
                digest,
                migrate=True,
            )
        launched = next(args for args in commands if "systemd-run" in args)
        self.assertIn("--no-block", launched)
        self.assertIn("--property=RemainAfterExit=yes", launched)
        self.assertEqual(launched[-1], "--migrate")
        self.assertEqual(sum("show" in args for args in commands), 3)

    def test_explicit_migration_allows_new_revisions_and_metadata(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (candidate / "backend/migrations/versions/0002_new.py").write_text("new schema")
        (candidate / "backend/migrations/env.py").write_text("new metadata")
        server.guard_schema(previous, candidate, migrate=True)
        (candidate / "backend/migrations/versions/0001_initial.py").write_text("rewrite history")
        with self.assertRaisesRegex(RuntimeError, "重写"):
            server.guard_schema(previous, candidate, migrate=True)

    def test_migration_failure_does_not_resume_sync(self):
        service, migration, error = self.exercise_deploy(
            "inactive", RuntimeError("migration failed"), migrate=True
        )
        self.assertEqual(error, "migration failed")
        migration.assert_called_once()
        self.assertNotIn(("start", server.TIMER), [call.args for call in service.call_args_list])

    def test_successful_migration_resumes_sync(self):
        service, migration, error = self.exercise_deploy("inactive", migrate=True)
        self.assertIsNone(error)
        migration.assert_called_once()
        self.assertEqual(service.call_args_list[-1].args, ("start", server.TIMER))

    def test_partial_migration_keeps_backup_and_does_not_start_old_code(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        db = self.make_db()
        backup = self.root / "before.sqlite3"

        def broken_migration(*args):
            with database(db) as connection:
                connection.execute("CREATE TABLE partial_migration (id INTEGER)")
            raise RuntimeError("DDL failed")

        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "systemctl") as service,
            patch.object(server, "run_migration", side_effect=broken_migration),
        ):
            with self.assertRaisesRegex(RuntimeError, "DDL failed"):
                server.activate_with_migration(previous, candidate, db, backup)
        self.assertEqual((self.root / "current").resolve(), previous)
        self.assertFalse(any(call.args[0] == "start" for call in service.call_args_list))
        with database(backup) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='partial_migration'"
                ).fetchone()
            )
        with database(db) as connection:
            self.assertIsNotNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='partial_migration'"
                ).fetchone()
            )

    def test_new_service_failure_after_migration_keeps_new_database(self):
        previous, candidate = self.make_release("previous"), self.make_release("candidate")
        (self.root / "current").symlink_to(previous)
        db = self.make_db()

        def migrate(*args):
            with database(db) as connection:
                connection.execute("UPDATE quotes SET price=200")

        with (
            patch.object(server, "BASE", self.root),
            patch.object(server, "systemctl") as service,
            patch.object(server, "run_migration", side_effect=migrate),
            patch.object(server, "guard_database"),
            patch.object(server, "check_integrity"),
            patch.object(server, "health", side_effect=RuntimeError("bad new app")),
        ):
            with self.assertRaisesRegex(RuntimeError, "bad new app"):
                server.activate_with_migration(
                    previous, candidate, db, self.root / "before.sqlite3"
                )
        self.assertEqual((self.root / "current").resolve(), candidate)
        self.assertEqual(service.call_args_list[-1].args, ("stop", server.SERVICE))
        with database(db) as connection:
            self.assertEqual(connection.execute("SELECT price FROM quotes").fetchone()[0], 200)

    def test_rehearsal_failure_only_modifies_disposable_copy(self):
        db = self.make_db()
        before = db.read_bytes()
        account = pwd.getpwuid(os.getuid())

        def broken_migration(candidate, snapshot):
            self.assertNotEqual(snapshot, db)
            with database(snapshot) as connection:
                connection.execute("UPDATE quotes SET price=300")
            raise RuntimeError("rehearsal failed")

        with (
            patch.object(server, "DATA", self.root),
            patch.object(server.pwd, "getpwnam", return_value=account),
            patch.object(server, "run_migration", side_effect=broken_migration),
            patch.object(server, "systemctl") as service,
        ):
            with self.assertRaisesRegex(RuntimeError, "rehearsal failed"):
                server.rehearse_migration(self.root, db)
        service.assert_not_called()
        self.assertEqual(db.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".migration-*")))


if __name__ == "__main__":
    unittest.main()
