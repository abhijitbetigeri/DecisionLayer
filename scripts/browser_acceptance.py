"""Real Chrome acceptance for the two-hour demo enhancements.

Run: uv run --with playwright python scripts/browser_acceptance.py
Uses temporary data, port 8021, installed Chrome, and no model calls.
"""
import json
import argparse
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8021"
parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true", help="Capture a labeled real walkthrough video and screenshots")
parser.add_argument("--output", type=Path, default=ROOT / "proofpath/demo/recordings")
args = parser.parse_args()
if args.record:
    args.output.mkdir(parents=True, exist_ok=True)


def capture(page, name):
    if args.record:
        page.wait_for_timeout(2000)
        page.screenshot(path=str(args.output / (name + ".png")), full_page=True)

with tempfile.TemporaryDirectory(prefix="decision-layer-browser-") as temp:
    env = {**os.environ, "PROOFPATH_DATA_DIR": temp, "PROOFPATH_ENABLE_LLM": "0",
           "PROOFPATH_DEMO_MODE": "local", "PROOFPATH_OPERATOR_TOKEN": "browser-local-token"}
    env.pop("PROOFPATH_DISABLE_WORKER", None)
    with open(Path(temp) / "server.log", "w") as log:
        server = subprocess.Popen(["uv", "run", "python", "-m", "uvicorn", "sv.proofpath.app:app",
                                   "--host", "127.0.0.1", "--port", "8021"], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for attempt in range(100):
                try:
                    urllib.request.urlopen(BASE + "/health", timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError((Path(temp) / "server.log").read_text())
                    time.sleep(.1)
            else:
                raise RuntimeError("Browser server did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                video_options = {"record_video_dir": str(args.output), "record_video_size": {"width": 1280, "height": 900}} if args.record else {}
                context = browser.new_context(viewport={"width": 1280, "height": 900}, **video_options)
                if args.record:
                    context.add_init_script("""document.addEventListener('DOMContentLoaded', () => {
                        const label = document.createElement('div');
                        label.textContent = 'Recorded walkthrough · real mock POC · rule-based evaluation';
                        label.style.cssText = 'position:fixed;bottom:12px;left:12px;z-index:9999;padding:8px 12px;background:#182238;color:white;font:12px system-ui;border-radius:6px;pointer-events:none';
                        document.body.append(label);
                    });""")
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(BASE)
                assert page.title().startswith("Decision Layer")
                page.locator('[data-stage="1"]').click()
                assert "Test the claim" in page.locator("#stage-title").inner_text()
                for width in (1280, 375):
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.wait_for_timeout(250)
                    page.screenshot(path=f"/tmp/decision-layer-landing-{width}.png")
                page.emulate_media(color_scheme="dark", reduced_motion="reduce")
                assert page.locator(".dl-button").first.is_visible()
                page.emulate_media(color_scheme="light", reduced_motion="no-preference")
                for preset in ("us_operations", "eu_technical"):
                    page.set_viewport_size({"width": 1280, "height": 900})
                    page.goto(BASE + "/demo")
                    capture(page, "homepage-" + preset)
                    page.locator(f'[data-preset="{preset}"]').click()
                    page.locator("#eval-submit").click()
                    page.wait_for_url("**/evaluations/*")
                    capture(page, "brief-" + preset)
                    page.get_by_role("button", name="Confirm requirements", exact=True).click()
                    page.locator("#btn-prove").wait_for()
                    page.wait_for_function("!document.getElementById('btn-prove').disabled")
                    before_poc_url = page.url
                    page.get_by_role("link", name="View adaptive homepage", exact=True).click()
                    page.wait_for_function("document.getElementById('experience-status').innerText.includes('Adapted to your evaluation')")
                    assert page.locator("#adaptive-cta").inner_text() == "Test recovery without duplicates"
                    assert "recovery needs verification" in page.locator("#experience-status").inner_text()
                    page.goto(before_poc_url)
                    page.wait_for_function("!document.getElementById('btn-prove').disabled")
                    page.locator("#btn-prove").click()
                    page.wait_for_function("document.querySelectorAll('#assertions .status-met').length === 4", timeout=30000)
                    expected = "Fit" if preset == "us_operations" else "Needs verification"
                    page.wait_for_function("([text]) => document.getElementById('hdr-decision').innerText.includes(text)", arg=[expected])
                    page.wait_for_function("document.getElementById('decision-timeline').innerText.includes('POC evidence evaluated')", timeout=15000)
                    page.locator("#p-insights").scroll_into_view_if_needed()
                    capture(page, "decision-" + preset)
                    if preset == "eu_technical":
                        page.wait_for_function("document.getElementById('decision-next-steps').innerText.includes('Verify Single sign-on')", timeout=15000)
                    workspace_url = page.url
                    page.get_by_role("link", name="View adaptive homepage", exact=True).click()
                    page.wait_for_function("document.getElementById('experience-status').innerText.includes('recovery demonstrated')")
                    assert page.locator("#adaptive-cta").inner_text() == ("Create evaluation report" if preset == "us_operations" else "Review remaining gaps")
                    assert "Your current evaluation" in page.locator("#preview-context").inner_text()
                    assert "EU hosting" in page.locator("#adaptive-headline").inner_text() if preset == "eu_technical" else "reliable" in page.locator("#adaptive-headline").inner_text()
                    capture(page, "adaptive-homepage-" + preset)
                    page.goto(workspace_url)
                    page.locator("#btn-report").wait_for()
                    page.locator("#btn-report").click()
                    page.locator("#report-body a").first.wait_for()
                    eid = page.url.rsplit("/", 1)[1]
                    request = context.request
                    before_view = request.get(BASE + f"/api/v1/evaluations/{eid}/workspace").json()["data"]["comparison"]
                    page.locator('[data-persona-btn="finance"]').click()
                    assert page.locator("#ws").get_attribute("data-persona") == "finance"
                    after_view = request.get(BASE + f"/api/v1/evaluations/{eid}/workspace").json()["data"]["comparison"]
                    assert before_view == after_view
                    page.locator('[data-persona-btn="technical"]').click()
                    print("PASS persona switching preserves findings and scores")
                    if preset == "eu_technical":
                        request = context.request
                        ws = request.get(BASE + f"/api/v1/evaluations/{eid}/workspace").json()["data"]
                        report_id = ws["reports"][0]
                        frozen = request.get(BASE + f"/api/v1/reports/{report_id}").json()
                        headers = {"x-operator-token": "browser-local-token"}
                        update = request.post(BASE + "/api/v1/demo/source-update", data={}, headers=headers).json()["data"]
                        approved = request.post(BASE + f"/api/v1/sources/{update['source_version']['id']}/review", data={"decision": "approved"}, headers=headers)
                        assert approved.ok
                        page.wait_for_function("document.getElementById('decision-timeline').innerText.includes('Approved evidence evaluated')", timeout=15000)
                        assert request.get(BASE + f"/api/v1/reports/{report_id}").json() == frozen
                        capture(page, "approved-evidence-update")
                        print("PASS browser evidence update and frozen report")
                        page.get_by_role("button", name="Edit requirements", exact=True).click()
                        page.get_by_role("button", name="Save edits", exact=True).click()
                        page.get_by_role("button", name="Confirm to re-evaluate", exact=True).wait_for()
                        assert page.locator("#btn-prove").is_disabled()
                        assert request.get(BASE + f"/api/v1/reports/{report_id}").json() == frozen
                        page.get_by_role("button", name="Confirm to re-evaluate", exact=True).click()
                        page.wait_for_function("!document.getElementById('btn-prove').disabled")
                        assert request.get(BASE + f"/api/v1/reports/{report_id}").json() == frozen
                        print("PASS brief edits require reconfirmation and preserve historical reports")
                    for width in (1280, 375):
                        page.set_viewport_size({"width": width, "height": 900})
                        for theme in ("light", "dark"):
                            page.emulate_media(color_scheme=theme)
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Workspace overflow at {width}/{theme}"
                    print(f"PASS browser {preset}: live POC, timeline, next steps, report, mobile")
                page.goto(BASE + "/visitor-lab")
                page.get_by_role("heading", name="Can agents reach the right buying decision?").wait_for()
                assert page.locator(".lab-arms article").count() == 2
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                print("PASS Visitor Lab actual results and mobile")
                page.set_viewport_size({"width": 1280, "height": 900})
                capture(page, "visitor-lab")
                assert not errors, json.dumps(errors)
                print("PASS no page JavaScript errors")
                video = page.video
                context.close()
                if args.record and video:
                    video.save_as(str(args.output / "decision-layer-walkthrough.webm"))
                    original = Path(video.path())
                    if original.name != "decision-layer-walkthrough.webm":
                        original.unlink(missing_ok=True)
                    print("Recorded walkthrough:", args.output / "decision-layer-walkthrough.webm")
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
