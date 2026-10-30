"""Create or restore a database backup for the configured Django backend."""

import logging
import os
import sqlite3
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

logger = logging.getLogger("sams.database")


class Command(BaseCommand):
    help = "Safely create or restore a SQLite or MySQL database backup."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("backup", "restore"))
        parser.add_argument(
            "--output",
            help="Destination backup file for backup action.",
        )
        parser.add_argument(
            "--input",
            dest="input_path",
            help="Source backup file for restore action.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow replacing an existing backup or restoring the live database.",
        )
        parser.add_argument(
            "--confirm-restore",
            action="store_true",
            help="Required explicit confirmation before changing the live database.",
        )

    def handle(self, *args, **options):
        action = options["action"]
        if action == "backup":
            self._backup(options)
        else:
            self._restore(options)

    def _backup(self, options):
        output = self._required_path(options["output"], "--output")
        self._validate_destination(output, options["force"])
        self._validate_parent(output)

        try:
            if connection.vendor == "sqlite":
                self._sqlite_backup(Path(connection.settings_dict["NAME"]), output)
            elif connection.vendor == "mysql":
                self._mysql_backup(output)
            else:
                raise CommandError(
                    f"Unsupported database backend: {connection.vendor}. "
                    "Only SQLite and MySQL are supported."
                )
        except (OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
            logger.exception("Database backup failed backend=%s path=%s", connection.vendor, output)
            raise CommandError(f"Database backup failed: {exc}") from exc

        logger.info("Database backup created backend=%s path=%s", connection.vendor, output)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {output}"))

    def _restore(self, options):
        source = self._required_path(options["input_path"], "--input")
        if not source.is_file():
            raise CommandError(f"Backup file does not exist: {source}")
        if not options["confirm_restore"]:
            raise CommandError(
                "Restore changes the configured live database. Re-run with --confirm-restore."
            )

        try:
            if connection.vendor == "sqlite":
                target = Path(connection.settings_dict["NAME"])
                if source.resolve() == target.resolve():
                    raise CommandError("The restore input must not be the live SQLite database.")
                self._sqlite_restore(source, target)
            elif connection.vendor == "mysql":
                self._mysql_restore(source)
            else:
                raise CommandError(
                    f"Unsupported database backend: {connection.vendor}. "
                    "Only SQLite and MySQL are supported."
                )
        except CommandError:
            raise
        except (OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
            logger.exception("Database restore failed backend=%s path=%s", connection.vendor, source)
            raise CommandError(f"Database restore failed: {exc}") from exc

        logger.info("Database restored backend=%s path=%s", connection.vendor, source)
        self.stdout.write(self.style.SUCCESS(f"Database restored from: {source}"))

    @staticmethod
    def _required_path(value, option):
        if not value:
            raise CommandError(f"{option} is required.")
        return Path(value).expanduser().resolve()

    @staticmethod
    def _validate_parent(path):
        if not path.parent.is_dir():
            raise CommandError(f"Backup directory does not exist: {path.parent}")

    @staticmethod
    def _validate_destination(path, force):
        if path.exists() and not force:
            raise CommandError(
                f"Backup already exists: {path}. Use --force to replace it explicitly."
            )

    @staticmethod
    def _sqlite_backup(source, destination):
        source_connection = sqlite3.connect(source)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()

    @staticmethod
    def _sqlite_restore(source, target):
        connection.close()
        source_connection = sqlite3.connect(source)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()

    def _mysql_environment(self):
        environment = os.environ.copy()
        password = connection.settings_dict.get("PASSWORD")
        if password:
            environment["MYSQL_PWD"] = password
        return environment

    def _mysql_arguments(self):
        config = connection.settings_dict
        return [
            "--host",
            str(config.get("HOST") or "localhost"),
            "--port",
            str(config.get("PORT") or "3306"),
            "--user",
            str(config.get("USER") or ""),
            str(config["NAME"]),
        ]

    def _mysql_backup(self, destination):
        command = [
            "mysqldump",
            "--single-transaction",
            "--routines",
            "--triggers",
            *self._mysql_arguments(),
            "--result-file",
            str(destination),
        ]
        subprocess.run(
            command,
            check=True,
            env=self._mysql_environment(),
            capture_output=True,
            text=True,
        )

    def _mysql_restore(self, source):
        command = ["mysql", *self._mysql_arguments()]
        with source.open("rb") as backup:
            subprocess.run(
                command,
                check=True,
                env=self._mysql_environment(),
                stdin=backup,
                capture_output=True,
            )
