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


def test_time_left_counts_steps_after_transcription():
    from datetime import datetime, timedelta

    from app.core.progress import begin, plan_later, report_detail, reporting

    class J:
        progress, stages, eta_s = 0, [], None
        started_at = datetime.utcnow() - timedelta(seconds=100)

    job = J()
    later = plan_later(job, 100, ["separate_vocals", "game", "melody", "preview"])
    assert later == 50 + 15 + 27 + 8
    with reporting(job):
        report_detail("MuScriptor: section 9 of 10", 0.9, remaining_s=10)
        assert 100 + 10 + later <= job.eta_s <= 100 + 10 + later + 6  # not just MuScriptor's own 10 s
        begin("melody", "Checking the melody…")  # GAME steps skipped or done: only melody + preview left
        assert 100 + 27 + 8 - 1 <= job.eta_s <= 100 + 27 + 8 + 1
        assert job.later_steps == {"preview": 8}
