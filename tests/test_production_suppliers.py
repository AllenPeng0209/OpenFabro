"""Supplier handoff must not masquerade as a remote factory submission."""
from copy import deepcopy
import importlib
import json
import socket

import pytest


def adapters():
    return importlib.import_module("wholeboard.production.suppliers")


def package(scope="pcba"):
    return {
        "id": "pkg-1", "scope": scope, "quantity": 5,
        "archive_sha256": "a" * 64,
        "files": [
            {"role": "gerbers", "path": "fab/board-gerbers.zip", "sha256": "b" * 64},
            {"role": "bom", "path": "fab/board-bom.csv", "sha256": "c" * 64},
            {"role": "cpl", "path": "fab/board-cpl.csv", "sha256": "d" * 64},
        ],
    }


def rfq():
    return {"id": "rfq-1", "package_id": "pkg-1", "status": "prepared"}


def test_jlc_handoff_identifies_upload_files_without_claiming_remote_delivery(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A manual handoff tried to open a network connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    result = adapters().prepare_handoff("jlcpcb", rfq(), package())
    assert result["channel"] == "manual_handoff"
    assert result["status"] == "prepared"
    assert result["transmitted"] is False
    assert result["quote_url"] == "https://cart.jlcpcb.com/quote"
    assert result["required_roles"] == ["gerbers", "bom", "cpl"]
    assert result["missing_roles"] == []
    assert [row["role"] for row in result["upload_files"]] == ["gerbers", "bom", "cpl"]
    assert result["upload_files"][1]["name"] == "board-bom.csv"
    assert "LCSC" in json.dumps(result["file_requirements"])


def test_pcbway_handoff_keeps_its_own_bom_requirements_and_ordering_url():
    result = adapters().prepare_handoff("pcbway", rfq(), package())
    assert result["quote_url"] == "https://www.pcbway.com/pcb-assembly.html"
    requirements = json.dumps(result["file_requirements"])
    assert "MPN" in requirements
    assert "polarity" in requirements
    assert result["api_available"] is False
    assert result["package_sha256"] == "a" * 64


def test_missing_assembly_files_are_visible_instead_of_an_upload_ready_claim():
    incomplete = package()
    incomplete["files"] = incomplete["files"][:1]
    result = adapters().prepare_handoff("pcbway", rfq(), incomplete)
    assert result["missing_roles"] == ["bom", "cpl"]
    assert result["files_complete"] is False


def test_device_handoff_requires_an_explicit_supplier_scope_agreement():
    complete = package("device")
    complete["files"] += [
        {"role": "enclosure", "path": "mechanical/case.step"},
        {"role": "test_plan", "path": "docs/functional-test.md"},
    ]
    result = adapters().prepare_handoff("jlcpcb", rfq(), complete)
    assert result["files_complete"] is True
    assert result["needs_scope_confirmation"] is True
    assert result["scope"] == "device"


@pytest.mark.parametrize("quantity", [0, -2, True, 1.2, "5"])
def test_invalid_quantities_cannot_be_handed_to_a_factory(quantity):
    invalid = package()
    invalid["quantity"] = quantity
    with pytest.raises(ValueError, match="quantity"):
        adapters().prepare_handoff("jlcpcb", rfq(), invalid)


def test_wrong_package_cannot_be_substituted_into_an_existing_rfq():
    wrong = package()
    wrong["id"] = "a-different-package"
    with pytest.raises(ValueError, match="package"):
        adapters().prepare_handoff("pcbway", rfq(), wrong)


@pytest.mark.parametrize("path", ["/Users/private/design.csv", "../secret.csv", ".env", "fab/../../secret.csv", "fab\\secret.csv"])
def test_handoff_never_exposes_private_or_escaping_file_paths(path):
    invalid = package()
    invalid["files"][1]["path"] = path
    with pytest.raises(ValueError, match="path"):
        adapters().prepare_handoff("jlcpcb", rfq(), invalid)


def test_unknown_supplier_and_scope_are_rejected_without_guessing():
    with pytest.raises(ValueError, match="supplier"):
        adapters().prepare_handoff("random-factory", rfq(), package())
    invalid = package("anything")
    with pytest.raises(ValueError, match="scope"):
        adapters().prepare_handoff("pcbway", rfq(), invalid)


def test_api_configuration_does_not_make_an_unverified_protocol_appear_connected(monkeypatch):
    monkeypatch.setenv("JLCPCB_ACCESS_KEY", "private-jlc-secret")
    monkeypatch.setenv("PCBWAY_API_KEY", "private-pcbway-secret")
    profiles = adapters().profiles()
    assert profiles and all(row["api_available"] is False for row in profiles)
    assert all(row["mode"] == "manual_handoff" for row in profiles)
    assert "private-" not in json.dumps(profiles)


@pytest.mark.parametrize("supplier_id", ["jlcpcb", "pcbway"])
def test_sync_fails_closed_without_transmitting_or_echoing_credentials(monkeypatch, supplier_id):
    def forbidden(*args, **kwargs):
        pytest.fail("An unconfigured adapter made a network request")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setenv("PCBWAY_API_KEY", "private-api-secret")
    record = {**rfq(), "external_reference": "private-remote-reference"}
    module = adapters()
    with pytest.raises(module.SupplierSetupError) as caught:
        module.sync_order(supplier_id, record)
    assert "supplier portal" in str(caught.value).lower()
    assert "private-" not in str(caught.value)
    assert caught.value.supplier_id == supplier_id


def test_preparing_an_rfq_does_not_mutate_its_frozen_manifest_or_record():
    original_rfq, original_package = rfq(), package()
    before = deepcopy((original_rfq, original_package))
    result = adapters().prepare_handoff("pcbway", original_rfq, original_package)
    result["upload_files"][0]["path"] = "changed.zip"
    assert (original_rfq, original_package) == before
