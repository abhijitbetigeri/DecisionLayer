"""Seed fixtures for the Evaluation Workspace (all products and evidence are fictional).

Facts follow proofpath/plan/shared-truth.md §3 exactly. Claim value conventions:

- capability keys (eu_hosting, us_hosting, sso, idempotent_delivery): `value` is the list of plans
  the capability is documented on; `False` means the source documents that it is NOT available.
  No claim at all means the evidence does not establish the answer (unknown).
- idempotent_delivery also carries the documented recovery/retry claim; documentation alone can
  never satisfy `recovery_demonstrated` (only a passing crm_warehouse_sync/v1 run can).
- budget_monthly_usd: one claim per plan; `value` is the monthly USD price, `None` = quote only.

Ids are fixed so seeding is idempotent and citations are stable across restarts.
"""
from __future__ import annotations

from datetime import datetime, timezone

PUBLISHED = datetime(2026, 9, 1, tzinfo=timezone.utc)

PRODUCTS = {
    "flowbridge": {"name": "FlowBridge", "plans": ["team", "business", "enterprise"]},
    "relayworks": {"name": "RelayWorks", "plans": ["business"]},
    "pipestack": {"name": "PipeStack", "plans": ["business"]},
}

PLAN_LABELS = {"team": "Team", "business": "Business", "enterprise": "Enterprise"}

# Rubric inputs that are not requirement keys: connectors documented in each source (systems are
# matched by name against the brief). Cited by source id in the comparison gaps.
CONNECTORS = {
    "flowbridge": ["Salesforce", "Snowflake"],
    "relayworks": ["Salesforce", "Snowflake"],
    "pipestack": ["Salesforce"],
}

# ------------------------------------------------------------------ approved at seed time
SOURCES = [
    {
        "id": "src-flowbridge-v1", "source_id": "flowbridge-docs", "product_id": "flowbridge",
        "origin": "FlowBridge pricing and security pages (fixture)",
        "content": ("FlowBridge (fictional) pricing and security.\n"
                    "Plans: Team $299/month. Business $999/month. Enterprise: contact sales for a quote.\n"
                    "Deployment: US region on all plans. EU region available on Business and Enterprise.\n"
                    "Reliability: automatic retries with idempotency keys on Business and Enterprise, so a "
                    "retried delivery does not create duplicate records.\n"
                    "Connectors: Salesforce (source), Snowflake (destination).\n"
                    "This page does not describe single sign-on."),
    },
    {
        "id": "src-relayworks-v1", "source_id": "relayworks-docs", "product_id": "relayworks",
        "origin": "RelayWorks pricing page (fixture)",
        "content": ("RelayWorks (fictional) pricing.\n"
                    "Business $899/month: EU and US deployment, SAML single sign-on, retries with "
                    "deduplication.\n"
                    "Connectors: Salesforce, Snowflake.\n"
                    "No independent test results are published."),
    },
    {
        "id": "src-pipestack-v1", "source_id": "pipestack-docs", "product_id": "pipestack",
        "origin": "PipeStack pricing page (fixture)",
        "content": ("PipeStack (fictional) pricing.\n"
                    "Business $699/month. Hosted in the US only; no EU region.\n"
                    "SAML single sign-on included on Business.\n"
                    "Connectors: Salesforce."),
    },
]

CLAIMS = [
    # FlowBridge: SSO deliberately has no claim (unknown).
    {"id": "clm-fb-eu", "source_version_id": "src-flowbridge-v1", "requirement_key": "eu_hosting",
     "value": ["business", "enterprise"], "plan": "business"},
    {"id": "clm-fb-us", "source_version_id": "src-flowbridge-v1", "requirement_key": "us_hosting",
     "value": ["team", "business", "enterprise"], "plan": "team"},
    {"id": "clm-fb-idem", "source_version_id": "src-flowbridge-v1", "requirement_key": "idempotent_delivery",
     "value": ["business", "enterprise"], "plan": "business"},
    {"id": "clm-fb-price-team", "source_version_id": "src-flowbridge-v1", "requirement_key": "budget_monthly_usd",
     "value": 299, "plan": "team"},
    {"id": "clm-fb-price-business", "source_version_id": "src-flowbridge-v1", "requirement_key": "budget_monthly_usd",
     "value": 999, "plan": "business"},
    {"id": "clm-fb-price-enterprise", "source_version_id": "src-flowbridge-v1", "requirement_key": "budget_monthly_usd",
     "value": None, "plan": "enterprise"},
    # RelayWorks v1
    {"id": "clm-rw-eu", "source_version_id": "src-relayworks-v1", "requirement_key": "eu_hosting",
     "value": ["business"], "plan": "business"},
    {"id": "clm-rw-us", "source_version_id": "src-relayworks-v1", "requirement_key": "us_hosting",
     "value": ["business"], "plan": "business"},
    {"id": "clm-rw-sso", "source_version_id": "src-relayworks-v1", "requirement_key": "sso",
     "value": ["business"], "plan": "business"},
    {"id": "clm-rw-idem", "source_version_id": "src-relayworks-v1", "requirement_key": "idempotent_delivery",
     "value": ["business"], "plan": "business"},
    {"id": "clm-rw-price-business", "source_version_id": "src-relayworks-v1", "requirement_key": "budget_monthly_usd",
     "value": 899, "plan": "business"},
    # PipeStack: recovery has no claim (unknown); EU documented as unavailable.
    {"id": "clm-ps-eu", "source_version_id": "src-pipestack-v1", "requirement_key": "eu_hosting",
     "value": False, "plan": None},
    {"id": "clm-ps-us", "source_version_id": "src-pipestack-v1", "requirement_key": "us_hosting",
     "value": ["business"], "plan": "business"},
    {"id": "clm-ps-sso", "source_version_id": "src-pipestack-v1", "requirement_key": "sso",
     "value": ["business"], "plan": "business"},
    {"id": "clm-ps-price-business", "source_version_id": "src-pipestack-v1", "requirement_key": "budget_monthly_usd",
     "value": 699, "plan": "business"},
]

# ------------------------------------------------------------------ controlled update (pending until reviewed)
UPDATES = {
    "relayworks_v2": {
        "source": {
            "id": "src-relayworks-v2", "source_id": "relayworks-docs", "product_id": "relayworks",
            "origin": "RelayWorks pricing page, updated (fixture)",
            "content": ("RelayWorks (fictional) pricing, updated.\n"
                        "Business $899/month: US deployment, SAML single sign-on, retries with "
                        "deduplication.\n"
                        "Enterprise: contact sales for a quote. EU deployment is now available on "
                        "Enterprise only.\n"
                        "Connectors: Salesforce, Snowflake.\n"
                        "No independent test results are published."),
        },
        "plans": ["business", "enterprise"],
        "claims": [
            {"id": "clm-rw2-eu", "requirement_key": "eu_hosting", "value": ["enterprise"], "plan": "enterprise"},
            {"id": "clm-rw2-us", "requirement_key": "us_hosting", "value": ["business", "enterprise"], "plan": "business"},
            {"id": "clm-rw2-sso", "requirement_key": "sso", "value": ["business", "enterprise"], "plan": "business"},
            {"id": "clm-rw2-idem", "requirement_key": "idempotent_delivery", "value": ["business", "enterprise"],
             "plan": "business"},
            {"id": "clm-rw2-price-business", "requirement_key": "budget_monthly_usd", "value": 899, "plan": "business"},
            {"id": "clm-rw2-price-enterprise", "requirement_key": "budget_monthly_usd", "value": None,
             "plan": "enterprise"},
        ],
    },
}

# Plans offered per source version (a newer approved version can add plans).
SOURCE_PLANS = {
    "src-flowbridge-v1": ["team", "business", "enterprise"],
    "src-relayworks-v1": ["business"],
    "src-relayworks-v2": ["business", "enterprise"],
    "src-pipestack-v1": ["business"],
}

# ------------------------------------------------------------------ presets (shared-truth §4)
DEMO_BRIEF = ("We need to sync Salesforce opportunities into Snowflake, require EU hosting and SSO, "
              "and need failed syncs to recover without duplicate records.")

SYSTEMS = ["Salesforce (CRM)", "Snowflake (warehouse)"]

PRESETS = {
    "eu_technical": {
        "label": "EU technical",
        "brief_text": DEMO_BRIEF,
        "goal": "Sync Salesforce opportunities into Snowflake with EU hosting, SSO and duplicate-free recovery",
        "systems": SYSTEMS,
        "requirements": [
            {"key": "eu_hosting", "hard": True},
            {"key": "sso", "hard": True},
            {"key": "recovery_demonstrated", "hard": True},
        ],
        "rubric_weights": {"implementation_effort": 2.0, "connector_coverage": 1.0},
    },
    "us_operations": {
        "label": "US operations",
        "brief_text": ("We sync Salesforce opportunities into Snowflake from the US and need failed syncs "
                       "to recover without duplicates. SSO would be nice to have."),
        "goal": "Sync Salesforce opportunities into Snowflake in the US with demonstrated duplicate-free recovery",
        "systems": SYSTEMS,
        "requirements": [
            {"key": "us_hosting", "hard": True},
            {"key": "recovery_demonstrated", "hard": True},
            {"key": "sso", "hard": False, "weight": 1.0},
        ],
        "rubric_weights": {},
    },
    "strict_budget": {
        "label": "Strict budget",
        "brief_text": ("We need EU-hosted Salesforce to Snowflake sync for at most $900 per month, and "
                       "failed syncs must recover without duplicates."),
        "goal": "EU-hosted Salesforce to Snowflake sync under $900/month with demonstrated recovery",
        "systems": SYSTEMS,
        "requirements": [
            {"key": "eu_hosting", "hard": True},
            {"key": "budget_monthly_usd", "hard": True, "expected": 900},
            {"key": "recovery_demonstrated", "hard": True},
        ],
        "rubric_weights": {"cost_clarity": 1.0},
    },
}
