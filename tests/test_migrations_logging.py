"""Alembic must not take over the application's logging (stage 3/§11, stage 5/§19).

`migrations/env.py` calls `logging.config.fileConfig(alembic.ini)`. The web and
worker processes run `init_db()` from inside an already-configured process, so
that call used to destroy the application's logging in two ways at once:

- `disable_existing_loggers=True` (the default) set `.disabled = True` on every
  existing application logger (sync_service, sync_scheduler, sync_worker, api);
- it also replaced the ROOT configuration with alembic.ini's, i.e. level WARNING
  and a stderr handler, dropping the application's INFO records.

The visible symptom was a container whose `docker logs` held the alembic lines
and nothing else — no "Sync ok ... google_requests=... duration=...", no errors.
A stuck sync claim then went unnoticed for an hour. These tests pin the
contract: inside a configured process alembic.ini is not applied at all.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_env_py_applies_alembic_ini_only_when_root_is_unconfigured():
    """The guard in migrations/env.py must actually key off root handlers."""
    source = (PROJECT_DIR / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "not logging.getLogger().handlers" in source, (
        "env.py must skip fileConfig() when the application already configured "
        "logging, otherwise init_db() silences every application logger"
    )


def test_app_logging_survives_a_fileconfig_call():
    """A configured root must keep its level and handler after env.py runs.

    Executed in a subprocess: the guard is about process-wide logging state, and
    re-configuring the root inside the test session would leak into every other
    test (and into pytest's own reporting).
    """
    script = """
import logging, logging.config, sys
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(levelname)s %(name)s: %(message)s")
# Exactly the guard migrations/env.py uses.
if not logging.getLogger().handlers:
    logging.config.fileConfig("alembic.ini")
logging.getLogger("sync_worker").info("APP-LINE-VISIBLE")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "APP-LINE-VISIBLE" in result.stdout, (
        "application INFO records must survive init_db(); stdout was: "
        f"{result.stdout!r}, stderr: {result.stderr!r}"
    )


def test_alembic_still_configures_itself_for_a_bare_cli_run():
    """Without an application in front, alembic.ini must still be applied.

    The fix is a guard, not a removal: `alembic upgrade head` run by hand (and
    by the documented `docker compose run --rm web alembic ...` step) relies on
    alembic.ini for its own [logger_alembic] level.
    """
    script = """
import logging, logging.config
logging.config.fileConfig("alembic.ini")
print("alembic_level=" + logging.getLevelName(logging.getLogger("alembic").level))
print("root_handlers=" + str(len(logging.getLogger().handlers)))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "alembic_level=INFO" in result.stdout, result.stdout
    assert "root_handlers=1" in result.stdout, result.stdout


@pytest.mark.parametrize("logger_name", ["sync_service", "sync_scheduler", "api"])
def test_application_loggers_stay_enabled_after_init(logger_name):
    """A named application logger must be enabled and report INFO afterwards.

    Run in a subprocess with the application's own configuration, because the
    property under test is process-wide logging state: pytest configures the
    root logger for its own reporting, so asserting `isEnabledFor(INFO)` in
    this process would test pytest, not the application.
    """
    script = f"""
import logging, sys
from pathlib import Path
sys.path.insert(0, str(Path({str(PROJECT_DIR / "backend")!r})))
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(levelname)s %(name)s: %(message)s")
import sync_service, sync_scheduler  # noqa: F401 - registers the loggers
for name in ("sync_service", "sync_scheduler", "api"):
    logger = logging.getLogger(name)
    print(name, "disabled=" + str(logger.disabled),
          "info=" + str(logger.isEnabledFor(logging.INFO)))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"{logger_name} disabled=False info=True" in result.stdout, result.stdout


def test_sync_service_logger_reports_at_info():
    """Guard the specific record the diagnosis depends on.

    `sync_service` logs "Sync ok user=... google_requests=... duration=..." at
    INFO; if that logger is ever disabled again the whole incident becomes
    invisible, so the level is asserted explicitly.
    """
    script = f"""
import logging, sys
from pathlib import Path
sys.path.insert(0, str(Path({str(PROJECT_DIR / "backend")!r})))
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(levelname)s %(name)s: %(message)s")
import sync_service  # noqa: F401 - registers the logger
print("sync_service_info=" + str(
    logging.getLogger("sync_service").isEnabledFor(logging.INFO)))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "sync_service_info=True" in result.stdout, result.stdout
