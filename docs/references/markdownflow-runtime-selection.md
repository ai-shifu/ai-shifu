---
title: MarkdownFlow Runtime Selection
status: implemented
owner_surface: learner
last_reviewed: 2026-10-07
canonical: true
---

# MarkdownFlow Runtime Selection

`FLOW_ENGINE_V2_ENABLED` selects the lesson runtime for the entire API deployment.
It defaults to `false`: every course uses MarkdownFlow 1.0. Set it to `true` to
teach every identified course with 2.0, including newly created courses. There is
no course ID restriction. The retired `FLOW_ENGINE_V2_SHIFU_BIDS` variable is
ignored, even if populated. Blank course identifiers are not routed to 2.0.

The environment registry accepts `true`, `1`, `yes`, and `on`, ignoring case and
surrounding whitespace. Unset, empty, false, and malformed strings retain 1.0.
Routing handles raw startup strings and initialized booleans consistently.

Simulation and Chinese production share their database. Routing therefore reads
`flaskr.common.config.get_config`, which does not consult `sys_configs`; no
course row or database configuration can opt production into 2.0. Set the flag
explicitly on the sim Deployment, outside shared ConfigMaps and Secrets. Keep
production unset or explicitly false. Each API deployment must carry its own
choice; changing sim does not change production.

The flag covers normal lessons, reading/listening, regeneration, and the
existing 2.0 editor-preview dispatch. Follow-up Ask requests retain their
existing 1.0 side path even when the lesson uses 2.0. This switch introduces no
schema migration, memory reset, or conversation conversion; each runtime keeps
its existing session handling. Existing 1.0 sessions are not migrated into 2.0.

## Rollout and rollback

The application and deployment manifests live in separate repositories. For a
rolling upgrade from the allowlist version, first add the new flag while
retaining the old list on sim. Old binaries ignore the new flag. Deploy the new
image, verify all API replicas use the flag, then remove the obsolete list.
Deploy code and environment together when provisioning a new environment.

Before changing live sim, compare the configuration repository to the current
Deployment. Preserve pipeline-managed images and unrelated configuration drift;
apply only the reviewed environment override. Verify Chinese and US production
remain disabled. Roll back all sim courses to 1.0 by setting the flag to `false`
through the deployment configuration workflow. A binary rollback to the old
allowlist implementation also requires restoring its previous allowlist.

Use fresh temporary learners in an internal test course for live acceptance.
Evaluate arbitrary course identifiers without database writes to verify that
admission is deployment-wide.
