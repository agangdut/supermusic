from app.core.progress import estimate_seconds, friendly_error, report, reporting
from app.models.job import Job, JobType


def test_report_records_stages_only_inside_a_job():
    report("nobody listening")  # no job bound: must not raise
    job = Job(job_type=JobType.MIDI_CONVERSION)
    with reporting(job):
        report("Step one")
        report("Step two")
    assert job.stage == "Step two"
    assert [s["label"] for s in job.stages] == ["Step one", "Step two"]
    assert job.stages[0]["ended_at"] and job.stages[1]["ended_at"] is None


def test_failed_job_gets_a_hint():
    job = Job(job_type=JobType.MIDI_CONVERSION)
    job.mark_failed("The YourMT3+ service isn't running. Start it with: docker compose up -d yourmt3")
    assert "docker compose up -d yourmt3" in job.error_hint


def test_friendly_error_fallback_and_estimate():
    assert friendly_error("weird") .startswith("Something went wrong")
    assert estimate_seconds("stems", 100) > estimate_seconds("multi", 100)
    assert estimate_seconds("basic", None) is None
