"""Production estimates must preserve unknown costs and never trust model arithmetic."""
import copy
import importlib
import json
import time

import pytest


def module():
    try:
        return importlib.import_module("wholeboard.production.estimate")
    except ModuleNotFoundError:
        pytest.fail("The production estimate implementation is missing")


def board():
    return {"name": "sample", "board": {"width_mm": 40, "height_mm": 30,
            "layers": 2, "thickness_mm": 1.6}, "components": [], "nets": []}


def options(**changes):
    return {"quantity": 5, "assembly": False, "base_version": 3,
            "shipping_country": "US", **changes}


def cached_quote(**changes):
    return {"quantity": 5, "currency": "USD", "source_version": 3,
            "quoted_at": time.time(), "assembly": {"boards": 5, "type": "economic", "subtotal": 9.52,
                "lines": [{"item": "Setup and assembly", "amount": 9.52}]},
            "components": {"lines": [{"refs": ["R1"], "lcsc": "C25804",
                "value": "100k", "footprint": "R_0603_1608Metric", "per_board": 1,
                "unit": .1, "order_qty": 5, "total": .5, "status": "ok",
                "library_type": "basic", "stock": 1000}]}, **changes}


def with_resistor():
    spec = board()
    spec["components"] = [{"ref": "R1", "value": "100k", "lcsc": "C25804",
                           "footprint": "Resistor_SMD:R_0603_1608Metric"}]
    return spec


def test_bare_board_estimate_has_a_sourced_cost_and_does_not_mutate_the_design():
    estimate = module()
    spec = board()
    original = copy.deepcopy(spec)
    result = estimate.build_estimate(spec, options(), ai=False)
    # 5 small 2-layer boards: $2 table price + $2.50 first-kg shipping model.
    assert result["known_total"] == 4.5
    assert result["total"] == 4.5
    assert result["complete"] is True
    assert result["ai"]["status"] == "disabled"
    assert all(line["source"] for line in result["line_items"])
    assert spec == original


def test_unpriced_component_is_an_unknown_instead_of_a_free_part():
    result = module().build_estimate(with_resistor(), options(assembly=True), ai=False)
    assert result["known_total"] > 4.5
    assert result["total"] is None and result["complete"] is False
    assert any("R1" in value for value in result["unknowns"])
    assert any(line["amount"] is None and "R1" in line["item"] for line in result["line_items"])


def test_current_quantity_matched_quote_prices_components_and_assembly():
    result = module().build_estimate(with_resistor(), options(assembly=True),
                                     current_quote=cached_quote(), ai=False)
    assert result["known_total"] == 14.52
    assert result["total"] == 14.52
    assert result["complete"] is True


@pytest.mark.parametrize("patch", [
    {"source_version": 2}, {"quantity": 100}, {"quoted_at": 0},
    {"quoted_at": time.time() - 90000}, {"spec_sha256": "0" * 64},
    {"assembly": {"boards": 2, "subtotal": 9.52, "lines": []}},
])
def test_stale_or_wrong_quantity_quotes_cannot_be_reused(patch):
    result = module().build_estimate(with_resistor(), options(assembly=True),
                                     current_quote=cached_quote(**patch), ai=False)
    assert result["total"] is None
    assert any("R1" in value for value in result["unknowns"])


def test_legacy_missing_component_zero_is_not_accepted_as_a_price():
    quote = cached_quote()
    quote["components"]["lines"][0].update(unit=None, total=0, status="missing")
    result = module().build_estimate(with_resistor(), options(assembly=True),
                                     current_quote=quote, ai=False)
    assert result["total"] is None
    assert any("R1" in value for value in result["unknowns"])


def test_choosing_standard_assembly_does_not_reuse_an_economic_service_fee():
    result = module().build_estimate(with_resistor(), options(assembly=True, pcba_type="standard"),
                                     current_quote=cached_quote(), ai=False)
    setup = next(line for line in result["line_items"] if "setup" in line["item"].lower())
    assert setup["amount"] == 25
    assert result["known_total"] > 30


def test_a_one_board_batch_uses_a_service_whose_minimum_is_one_board():
    result = module().build_estimate(with_resistor(), options(quantity=1, assembly=True), ai=False)
    setup = next(line for line in result["line_items"] if "setup" in line["item"].lower())
    assert result["quantity"] == 1
    assert setup["amount"] == 25
    assert any("minimum" in value.lower() for value in result["assumptions"])


@pytest.mark.parametrize("corrupt", [
    {"assembly": []}, {"components": {"lines": "garbage"}},
    {"components": {"lines": [None, {"refs": [None]}]}},
])
def test_malformed_cached_evidence_is_ignored_without_losing_the_estimate(corrupt):
    result = module().build_estimate(with_resistor(), options(assembly=True),
                                     current_quote=cached_quote(**corrupt), ai=False)
    assert result["known_total"] > 0
    assert result["total"] is None


def test_unsupported_layer_count_is_not_priced_using_two_layer_rates():
    spec = board()
    spec["board"]["layers"] = 8
    result = module().build_estimate(spec, options(), ai=False)
    assert result["total"] is None
    assert result["known_total"] == 2.5
    assert any("8" in value and "layer" in value.lower() for value in result["unknowns"])


@pytest.mark.parametrize("quantity", [0, -1, True, 2.5, float("inf"), "five"])
def test_invalid_batch_quantities_are_rejected_before_any_model_call(quantity):
    with pytest.raises(ValueError, match="quantity|Quantit"):
        module().build_estimate(board(), options(quantity=quantity), ai=False)


def fake_codex(tmp_path, monkeypatch, *, fail=False):
    from wholeboard import codex_bridge
    executable = tmp_path / "codex-test"
    response = {"summary": "Consider panelization for the next batch.",
                "risks": ["Freight is a model estimate."],
                "suggestions": ["Ask the factory for a panel quote."],
                "total": 0, "unknowns": []}
    executable.write_text("#!/usr/bin/env python3\nimport json,pathlib,sys\n"
        "if sys.argv[1] == 'login': sys.exit(0)\n"
        + ("sys.stderr.write('secret-test-value'); sys.exit(1)\n" if fail else
           "out=pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])\n"
           f"out.write_text({json.dumps(json.dumps(response))})\n"))
    executable.chmod(0o700)
    monkeypatch.setattr(codex_bridge, "find_cli", lambda: str(executable))
    monkeypatch.setattr(codex_bridge, "_status_cache", (0, {}))


def test_actual_cli_boundary_returns_analysis_without_overriding_arithmetic(tmp_path, monkeypatch):
    estimate = module()
    fake_codex(tmp_path, monkeypatch)
    result = estimate.build_estimate(board(), options(), ai=True)
    assert result["total"] == 4.5
    assert result["ai"]["status"] == "complete"
    assert result["ai"]["provider"] == "codex"
    assert result["ai"]["summary"] == "Consider panelization for the next batch."
    assert result["ai"]["suggestions"] == ["Ask the factory for a panel quote."]


def test_cli_failure_retains_cost_evidence_and_does_not_expose_stderr(tmp_path, monkeypatch):
    estimate = module()
    fake_codex(tmp_path, monkeypatch, fail=True)
    result = estimate.build_estimate(board(), options(), ai=True)
    assert result["total"] == 4.5
    assert result["ai"]["status"] == "error"
    assert "secret-test-value" not in json.dumps(result)


def test_codex_timeout_preserves_the_cost_estimate(tmp_path, monkeypatch):
    estimate = module()
    fake_codex(tmp_path, monkeypatch)
    from wholeboard import codex_bridge
    executable = tmp_path / "codex-test"
    executable.write_text("#!/usr/bin/env python3\nimport sys,time\n"
                          "if sys.argv[1] == 'login': sys.exit(0)\n"
                          "time.sleep(5)\n")
    monkeypatch.setattr(estimate, "_AI_TIMEOUT", .05)
    started = time.monotonic()
    result = estimate.build_estimate(board(), options(), ai=True)
    assert time.monotonic() - started < 2
    assert result["total"] == 4.5
    assert result["ai"]["status"] == "error"
    assert "timed out" in result["ai"]["summary"]


def test_timed_out_cli_does_not_leave_a_child_model_process_running(tmp_path, monkeypatch):
    import os
    if os.name == "nt":
        pytest.skip("POSIX process-group cleanup")
    estimate = module()
    fake_codex(tmp_path, monkeypatch)
    marker = tmp_path / "orphan-ran.txt"
    child = "import time,pathlib; time.sleep(.4); pathlib.Path(" + repr(str(marker)) + ").write_text('orphan')"
    (tmp_path / "codex-test").write_text("#!/usr/bin/env python3\nimport sys,time,subprocess\n"
        "if sys.argv[1] == 'login': sys.exit(0)\n"
        f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "time.sleep(5)\n")
    monkeypatch.setattr(estimate, "_AI_TIMEOUT", .1)
    result = estimate.build_estimate(board(), options(), ai=True)
    time.sleep(.5)
    assert result["ai"]["status"] == "error"
    assert not marker.exists(), "A timed-out Codex wrapper left its model child alive"
