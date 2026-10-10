"""The demo vendor site, "Pulse", served in several variants side by side.

  /A/...  control: a typical human-optimized SaaS site (JS pricing, "contact sales", trust portal)
  /C/...  fixed: same facts, agent-legible (static prices, feature matrix, JSON-LD, llms.txt)
  /D/...  C plus marketing claims the facts do not support (the guard must block this one)

Every variant renders from data/facts.yaml. Variants differ in presentation, plus the
`extra_claims` a variant injects, which is exactly what the guard inspects.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sv.facts import load_facts

TEMPLATES = Path(__file__).parent / "templates"

# Variant registry: which template set to render and which unsupported claims it injects.
VARIANTS: dict[str, dict] = {
    "A": {"templates": "A", "extra_claims": []},
    "C": {"templates": "C", "extra_claims": []},
    # D is what an unguarded optimizer produces: it edits the content itself, consistently,
    # so every surface tells the same (false) story. The oracle and guard still use real facts.
    "D": {"templates": "C", "extra_claims": [
        "SAML single sign-on (SSO) included on every plan",
        "SOC 2 Type II certified",
    ], "fact_overrides": {
        "compliance.soc2_type2": {"status": "certified", "date": "2026-09-01"},
        "plans.*.features+": "saml_sso",
    }},
}


def apply_overrides(facts: dict, overrides: dict) -> dict:
    """Tiny patch language: 'a.b' sets a value, 'plans.*.features+' appends to every plan."""
    facts = copy.deepcopy(facts)
    for path, value in overrides.items():
        if path.startswith("plans.*.") and path.endswith("+"):
            key = path[len("plans.*."):-1]
            for p in facts["plans"]:
                if value not in p[key]:
                    p[key].append(value)
            continue
        *parents, leaf = path.split(".")
        node = facts
        for k in parents:
            node = node[k]
        node[leaf] = value
    return facts


def site_facts(variant: str) -> dict:
    """The facts a variant renders from (not necessarily the true facts)."""
    return apply_overrides(load_facts(), VARIANTS[variant].get("fact_overrides", {}))


def plans_with(facts: dict, feature: str) -> str:
    names = [p["name"] for p in facts["plans"] if feature in p["features"]]
    if len(names) == len(facts["plans"]):
        return "all plans"
    return " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)

PAGES = {"": "home.html", "pricing": "pricing.html", "security": "security.html",
         "docs/faq": "faq.html", "trust": "trust.html"}

app = FastAPI(title="Pulse demo site")


def _env(template_set: str) -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES / template_set),
                       autoescape=select_autoescape(["html"]))


def _json_ld(facts: dict, base: str) -> str:
    offers = []
    for p in facts["plans"]:
        if p["price_per_seat_monthly"] is None:
            continue
        offers.append({
            "@type": "Offer", "name": p["name"], "priceCurrency": "USD",
            "price": p["price_per_seat_monthly"], "url": f"{base}/pricing",
            "description": f"Per seat per month, billed monthly (${p['price_per_seat_annual']} billed annually). "
                           f"Up to {p['max_seats']} seats. Includes: "
                           + ", ".join(facts["feature_labels"][f] for f in p["features"]),
        })
    return json.dumps({"@context": "https://schema.org", "@type": "SoftwareApplication",
                       "name": facts["company"]["name"], "applicationCategory": "BusinessApplication",
                       "offers": offers}, indent=2)


def render(variant: str, page: str, base: str) -> str:
    cfg = VARIANTS.get(variant)
    if cfg is None or page not in PAGES:
        raise HTTPException(404)
    facts = site_facts(variant)
    try:
        tpl = _env(cfg["templates"]).get_template(PAGES[page])
    except Exception:
        raise HTTPException(404)
    return tpl.render(facts=facts, base=base, extra_claims=cfg["extra_claims"],
                      plans_with=lambda feature: plans_with(facts, feature),
                      json_ld=_json_ld(facts, base), pricing_json=json.dumps(facts["plans"]))


def _soc2_type2(c: dict) -> str:
    t2 = c["soc2_type2"]
    return f"certified ({t2['date']})" if t2["status"] == "certified" else f"audit in progress, expected {t2['expected']}"


def llms_txt(variant: str, base: str) -> str:
    cfg = VARIANTS.get(variant)
    if cfg is None or cfg["templates"] == "A":
        raise HTTPException(404)        # the control site never shipped one
    f = site_facts(variant)
    lines = [f"# {f['company']['name']}", f"> {f['company']['tagline']}", "",
             f"Facts as of {f['as_of']}.", "", "## Plans (USD per seat per month)"]
    for p in f["plans"]:
        if p["price_per_seat_monthly"] is None:
            price = "custom pricing, contact sales"
        else:
            price = (f"${p['price_per_seat_monthly']} billed monthly, ${p['price_per_seat_annual']} billed annually,"
                     f" up to {p['max_seats']} seats")
        feats = ", ".join(f["feature_labels"][x] for x in p["features"])
        lines.append(f"- {p['name']}: {price}. Includes: {feats}.")
    c = f["compliance"]
    lines += ["", "## Security and compliance",
              f"- SOC 2 Type I: certified ({c['soc2_type1']['date']})",
              f"- SOC 2 Type II: {_soc2_type2(c)}",
              "- GDPR: compliant", f"- HIPAA: {c['hipaa']['note']}",
              f"- Data regions: US (default), EU ({plans_with(f, 'eu_data_residency')})",
              f"- SAML SSO: {plans_with(f, 'saml_sso')}"]
    lines += [f"- {claim}" for claim in cfg["extra_claims"]]
    lines += ["", "## Pages", f"- [Pricing]({base}/pricing)", f"- [Security]({base}/security)",
              f"- [FAQ]({base}/docs/faq)"]
    return "\n".join(lines) + "\n"


@app.get("/{variant}/llms.txt", response_class=PlainTextResponse)
def get_llms(variant: str):
    return llms_txt(variant, f"/{variant}")


@app.get("/{variant}/{page:path}", response_class=HTMLResponse)
def get_page(variant: str, page: str = ""):
    return render(variant, page.strip("/"), f"/{variant}")
