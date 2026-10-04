from conftest import commit
from thrash import ui
from thrash.extract import sanitize
from thrash.process_image import ProcessImage, ImageMeta, ModelOutput, ContextFile
from thrash.resume import ResumeReport, build_resume_report


def rich_image():
    return ProcessImage(project="alpha", program_counter={"task": "rig jaw", "confidence": .8},
        summary="Finished topology; moved on to jaw rigging.",
        completed=[{"text": "topology cleanup", "source": "notes.md", "explicit": True}],
        decisions=[{"text": "defer engine", "reason": "validate deformation first", "source": "notes.md"}],
        registers={"engine": "undecided"}, stack=["rig jaw", "test pose"],
        open_handles=["notes.md"], unresolved=["hair physics"], blockers=["jaw weights"],
        next_action="Rig the jaw before engine integration.", evidence=["notes.md"],
        purpose="Build an expressive character", failures=["automatic weights distorted jaw"],
        resurrection_hint="Once deformation is stable", meta=ImageMeta(created_at=1, model="fake", context_version=2))


def test_resume_contains_every_piece_and_serializes():
    report = build_resume_report("alpha", rich_image())
    assert report.completed[0].text == "topology cleanup"
    assert report.decision_reasons == ["validate deformation first"]
    assert report.last_execution_point == "rig jaw" and report.blockers == ["jaw weights"]
    assert report.unresolved == ["hair physics"] and report.what_happened
    assert report.next_action.startswith("Rig the jaw")
    assert ResumeReport.model_validate_json(report.model_dump_json()) == report
    output = ui.resume_text(report).plain
    for title in ("WHAT YOU DID", "WHAT YOU FINISHED", "WHAT YOU DECIDED AND WHY", "WHERE YOU LEFT OFF",
                  "WHAT CHANGED SINCE THEN", "WHAT REMAINS UNRESOLVED", "NEXT EXECUTION", "EVIDENCE"):
        assert title in output
    assert "validate deformation first" in output


def test_legacy_image_is_compatible_and_does_not_invent_completion():
    image = ProcessImage(project="alpha", program_counter="pending task", meta=ImageMeta(created_at=1, model="fake"))
    report = build_resume_report("alpha", image)
    assert report.legacy_image and report.completed == [] and report.next_action == "pending task"
    assert "No completed work recorded" in ui.resume_text(report).plain


def test_unknown_reason_is_explicitly_unknown():
    image = rich_image()
    image.decisions[0].reason = ""
    assert "Reason not recorded" in ui.resume_text(build_resume_report("alpha", image)).plain


def test_completed_evidence_is_validated():
    out = ModelOutput(program_counter="x", completed=[{"text":"done", "source":"invented.md", "explicit":True}])
    out, count = sanitize(out, {"notes.md"})
    assert count == 1 and not out.completed[0].explicit and not out.completed[0].source


def test_switch_wake_status_share_saved_semantics_and_live_drift(kernel3, repos):
    k = kernel3
    proc = k.reg.resolve("alpha")
    cf = k.load_context(proc)
    cf.image = rich_image()
    cf.write(k.image_path(proc))
    k.switch("alpha")
    k.suspend("alpha")
    commit(repos["alpha"], "engine scaffold", {"engine.py":"pass"})
    wake = k.wake("alpha").resume
    status = k.restore(proc, reconstruct=False).resume
    assert wake == status
    assert wake.completed[0].text == "topology cleanup"
    assert "engine.py" in wake.changes_since_snapshot.files
    assert wake.possible_drift


def test_status_does_not_call_model_for_missing_image(kernel3):
    k = kernel3
    p = k.reg.resolve("alpha")
    k.image_path(p).unlink()
    k._extractor = lambda *a: (_ for _ in ()).throw(AssertionError("unexpected extraction"))
    report = k.restore(p, reconstruct=False).resume
    assert not report.available and report.completed == []


def test_core_preserves_semantic_exit_state(kernel3):
    k = kernel3
    p = k.reg.resolve("alpha")
    cf = k.load_context(p)
    cf.image = rich_image()
    cf.write(k.image_path(p))
    k.kill(k.kill_plan("alpha"), core=True)
    _, core, _, _ = k.resurrect("alpha")
    assert core.image.purpose == "Build an expressive character"
    assert core.image.failures == ["automatic weights distorted jaw"]
    assert core.image.completed and core.image.decisions[0].reason


def test_resume_renders_literal_brackets_and_hides_paths():
    image = rich_image()
    image.summary = "[type='CNAME'] /synthetic/private/project/notes.md"
    output = ui.resume_text(build_resume_report("alpha", image)).plain
    assert "[type='CNAME']" in output and "/synthetic/private" not in output
