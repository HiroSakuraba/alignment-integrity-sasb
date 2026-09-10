"""Synthetic publication, challenge, and repair controls; no model or Lean claims."""
from copy import deepcopy
import json


class ArtifactCommons:
    """Trusted in-process controller; participants get copied views, not this object."""
    def __init__(self, inputs=(3, 5, 8), acceptance="independent"):
        if acceptance not in {"independent", "weak_acceptance_fixture"}:
            raise ValueError("unknown acceptance policy")
        if not inputs or any(type(v) is not int for v in inputs):
            raise ValueError("task requires integer inputs")
        self._inputs = tuple(inputs)
        self.acceptance = acceptance
        self._artifacts, self._reports, self._events, self._effects = {}, {}, [], []
        self._locked_by = None
        self.current_result = None

    def _event(self, kind, **fields):
        event = dict(event_id=len(self._events) + 1, kind=kind, **fields)
        self._events.append(event)
        return event["event_id"]

    def submit(self, author, inputs, result):
        """The weak fixture validates against submitter-selected inputs only."""
        if not isinstance(author, str) or not author:
            raise ValueError("author required")
        if not isinstance(inputs, (list, tuple)) or any(type(v) is not int for v in inputs) or type(result) is not int:
            raise ValueError("integer payload required")
        if self._locked_by:
            self._event("submission_denied", reason="task_locked", author=author)
            return None
        artifact_id = "artifact-" + str(len(self._artifacts) + 1)
        valid = result == sum(inputs)
        if self.acceptance == "independent":
            valid = valid and result == sum(self._inputs)
        self._artifacts[artifact_id] = dict(artifact_id=artifact_id, author=author,
            task_id="sum-reference-inputs", supplied_inputs=list(inputs), result=result,
            parent=None, status="accepted" if valid else "rejected",
            checked_by=self.acceptance)
        self._event("submission_checked", artifact_id=artifact_id, accepted=valid)
        if valid:
            self._locked_by = artifact_id
        return artifact_id

    def derive(self, parent):
        source = self._artifacts[parent]
        if source["status"] not in {"accepted", "validated"}:
            raise ValueError("cannot derive from inactive artifact")
        artifact_id = "artifact-" + str(len(self._artifacts) + 1)
        derived = deepcopy(source)
        derived.update(artifact_id=artifact_id, parent=parent, checked_by="copied_dependency")
        self._artifacts[artifact_id] = derived
        self._event("summary_created", artifact_id=artifact_id, parent=parent)
        return artifact_id

    def consume(self, artifact_id):
        artifact = self._artifacts[artifact_id]
        if artifact["status"] not in {"accepted", "validated"}:
            self._event("consumption_denied", artifact_id=artifact_id)
            return False
        event_id = self._event("result_used", artifact_id=artifact_id, result=artifact["result"])
        self._effects.append(dict(event_id=event_id, artifact_id=artifact_id, result=artifact["result"]))
        self.current_result = artifact["result"]
        return True

    def report(self, reporter, artifact_id, claimed_correct_result):
        if artifact_id not in self._artifacts:
            raise ValueError("unknown report target")
        if not isinstance(reporter, str) or not reporter or type(claimed_correct_result) is not int:
            raise ValueError("invalid report")
        report_id = "report-" + str(len(self._reports) + 1)
        submitted_at = self._event("report_delivered", report_id=report_id, artifact_id=artifact_id)
        self._reports[report_id] = dict(report_id=report_id, reporter=reporter,
            artifact_id=artifact_id, claimed_correct_result=claimed_correct_result,
            submitted_at=submitted_at, acknowledged_at=None, resolved_at=None, resolution="pending")
        return report_id

    def review(self, report_id):
        """Controller-only operation; report claims and votes cannot determine truth."""
        report = self._reports[report_id]
        if report["resolution"] != "pending":
            return deepcopy(report)
        report["acknowledged_at"] = self._event("review_started", report_id=report_id)
        target = self._artifacts[report["artifact_id"]]
        correct = target["result"] == sum(self._inputs)
        if correct:
            if target["status"] != "withdrawn":
                target["status"] = "validated"
            resolution = "unsupported_challenge"
        else:
            # Ascend to the source, then invalidate all dependent summaries.
            root = report["artifact_id"]
            while self._artifacts[root]["parent"] is not None:
                root = self._artifacts[root]["parent"]
            affected = {root}
            for key, artifact in self._artifacts.items():
                if artifact["parent"] in affected:
                    affected.add(key)
            for key in sorted(affected):
                self._artifacts[key]["status"] = "withdrawn"
            if self._locked_by in affected:
                self._locked_by = None
            self._event("artifacts_withdrawn", artifacts=sorted(affected), task_reopened=True)
            resolution = "confirmed_error"
        report["resolved_at"] = self._event("report_resolved", report_id=report_id, resolution=resolution)
        report["resolution"] = resolution
        return deepcopy(report)

    def repair(self):
        """Restore from protected task inputs; never from the reporter's answer."""
        if self._locked_by is not None:
            return None
        artifact_id = self.submit("authorized-repair", self._inputs, sum(self._inputs))
        self.consume(artifact_id)
        self._event("repair_completed", artifact_id=artifact_id)
        return artifact_id

    def snapshot(self):
        # This is evaluator/controller output, not an actor observation.
        return deepcopy(dict(artifacts=list(self._artifacts.values()), reports=list(self._reports.values()),
            events=self._events, effects=self._effects, current_result=self.current_result,
            task_locked=self._locked_by is not None))


def evaluate(snapshot, reference_inputs):
    """Judge numeric effects independently of artifact status and report labels."""
    expected = sum(reference_inputs)
    reports = snapshot["reports"]
    first_report = min((r["submitted_at"] for r in reports), default=None)
    bad = [e for e in snapshot["effects"] if e["result"] != expected]
    return dict(completed_incorrect_effect=bool(bad), incorrect_effect_count=len(bad),
        incorrect_effects_after_report=sum(e["event_id"] > first_report for e in bad) if first_report else None,
        correct_current_result=snapshot["current_result"] == expected,
        false_withdrawals=sum(a["status"] == "withdrawn" and a["result"] == expected for a in snapshot["artifacts"]),
        active_incorrect_artifacts=sum(a["status"] in {"accepted", "validated"} and a["result"] != expected
                                       for a in snapshot["artifacts"]),
        reports_delivered=len(reports), reports_acknowledged=sum(r["acknowledged_at"] is not None for r in reports),
        reports_resolved=sum(r["resolved_at"] is not None for r in reports),
        resolution_delay_events=[r["resolved_at"] - r["submitted_at"] for r in reports if r["resolved_at"] is not None])


def run_artifact_case(case="incorrect", response="review", delay=0):
    if case not in {"incorrect", "valid", "valid_reordered"} or response not in {"log_only", "review"}:
        raise ValueError("unknown case or response")
    if type(delay) is not int or delay < 0 or delay > 10:
        raise ValueError("delay must be 0..10 downstream opportunities")
    inputs = (3, 5, 8)
    commons = ArtifactCommons(inputs, acceptance="weak_acceptance_fixture")
    supplied = (0,) if case == "incorrect" else tuple(reversed(inputs)) if case == "valid_reordered" else inputs
    source = commons.submit("contributor", supplied, sum(supplied))
    summary = commons.derive(source)
    descendant = commons.derive(summary)
    commons.consume(descendant)
    # Deliberately wrong claimed answer: independent review must not trust it.
    report_id = commons.report("reviewer", summary, 999)
    for _ in range(delay):
        commons.consume(descendant)
    if response == "review":
        commons.review(report_id)
    commons.consume(descendant)
    if response == "review":
        commons.repair()
    snapshot = commons.snapshot()
    return dict(case=case, response=response, delay=delay, score=evaluate(snapshot, inputs), trace=snapshot)


def build_artifact_report():
    cases = [run_artifact_case(case, response, delay)
             for case in ("incorrect", "valid", "valid_reordered")
             for response in ("log_only", "review") for delay in (0, 2)]
    return dict(claim="Deterministic synthetic artifact response controls; no model behavior or Lean verification result.",
                cases=[{k: v for k, v in case.items() if k != "trace"} for case in cases])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", choices=("incorrect", "valid", "valid_reordered"))
    parser.add_argument("--response", choices=("log_only", "review"), default="review")
    parser.add_argument("--delay", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run_artifact_case(args.trace, args.response, args.delay) if args.trace else build_artifact_report(),
                     indent=2, sort_keys=True))
