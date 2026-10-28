from unittest.mock import Mock

from app.services import jobicy_status_scheduler as scheduler_service


def test_scheduled_sync_closes_session_after_success(monkeypatch):
    db = Mock()
    monkeypatch.setattr(
        scheduler_service,
        "SessionLocal",
        lambda: db,
    )
    monkeypatch.setattr(
        scheduler_service,
        "sync_jobicy_statuses",
        lambda session: {
            "checked": 3,
            "active": 2,
            "closed": 1,
            "unknown": 0,
        },
    )

    scheduler_service.run_scheduled_jobicy_status_sync()

    db.close.assert_called_once_with()


def test_scheduled_sync_closes_session_after_failure(
    monkeypatch,
    caplog,
):
    db = Mock()
    monkeypatch.setattr(
        scheduler_service,
        "SessionLocal",
        lambda: db,
    )

    def fail(_session):
        raise RuntimeError("Simulated sync failure")

    monkeypatch.setattr(
        scheduler_service,
        "sync_jobicy_statuses",
        fail,
    )

    scheduler_service.run_scheduled_jobicy_status_sync()

    db.close.assert_called_once_with()
    assert "Scheduled Jobicy status sync failed" in caplog.text

def test_scheduler_uses_configured_interval():
    scheduler = scheduler_service.create_jobicy_status_scheduler(
        interval_hours=12
    )
    scheduler.start(paused=True)

    try:
        job = scheduler.get_job("jobicy_status_sync")

        assert job is not None
        assert job.trigger.interval.total_seconds() == 12 * 60 * 60
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        scheduler.shutdown(wait=False)
