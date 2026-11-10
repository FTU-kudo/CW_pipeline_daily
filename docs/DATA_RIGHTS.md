# Data rights and publication policy

## Default mode: private/local

This repository contains analysis code, not a license to redistribute market data. The pipeline, cache files, Excel export, legacy JSON, and dashboard series may contain raw, normalized, or derived source data. Vnstock's library license and the provider/exchange data license are separate.

The Vnstock G6 source guidance says domestic broker Open APIs (`ssi`, `dnse`, `tcbs`, `fhsc`) are for the account holder's personal research and prohibits redistributing raw, normalized, or derived data to third parties without written approval from both the provider and the relevant exchange. Other providers have their own terms. The source's current original terms prevail over a summary:

- [Vnstock G6 source scope and terms](https://vnstocks.com/docs/vnstock/v6/tham-khao/nguon-du-lieu)
- [Vnstock package/version history](https://vnstocks.com/docs/goi-quyen-su-dung/lich-su-phien-ban)

Because this project has no recorded redistribution approval and still has no selected G6 provider, it now:

- keeps downloaded caches, Excel, JSON, and dashboard build output under ignored `output/private-data/`;
- blocks `cwintel.build --out docs/...` unless an unexpired, source-matched written-authorization record is provided;
- does not fetch provider data, upload datasets, or commit generated artifacts in GitHub Actions;
- removes generated market-data files from the current source tree and excludes future ones from Git.

Previously published data may remain in Git history, forks, caches, or existing Pages/CDN copies. This code change cannot purge those copies or alter deployments on the default branch by itself. Review GitHub Pages and repository history separately if takedown is needed.

## Authorization record for a later public release

First obtain permission that explicitly covers public display, redistribution of raw/normalized/derived data, retention, caching, and the relevant exchanges. Review the live original terms, as authorization may be limited by source, market, fields, audience, and dates. A provider key or paid Vnstock tier is not that permission.

After a human verifies the signed permissions, store a local JSON record outside Git, default path `output/legal/data-redistribution-authorization.json`:

```json
{
  "source": "<selected-source>",
  "data_owner": "<provider>",
  "exchange": "<exchange>",
  "written_approval_reference": "<non-secret reference to signed approval held privately>",
  "terms_url": "<current original provider terms>",
  "public_display": true,
  "public_redistribution": true,
  "derived_data_redistribution": true,
  "valid_until": "YYYY-MM-DD"
}
```

Validate it without making any provider request:

```bash
python scripts/check_publication_rights.py --source <selected-source>
```

A passing check only verifies the record's required fields, source match, and expiry. It is **not** legal verification. `cwintel.build --out docs/data` also requires `VNSTOCK_SOURCE` and that same current record. Never put provider API keys, OTPs, credentials, or signed confidential contracts in Git.

## Vnstock package notes from the linked history

The 06-11-2026 section is dated **two days after the current date in this work session (04-11-2026)**; treat it as a future-dated changelog entry until that date/version is actually released. It describes `vnstock_quant` 1.0.0rc1, which depends on `vnstock` 6 and has its own release/entitlement conditions. This project does not add that release candidate: its stated scope is not a drop-in covered-warrant pricing model, and replacing the project's formulas without contract-level validation would invent equivalence.

The project's `vnstock` package remains pinned to generation 6 from Vnstock's own package feed in `requirements.txt`; the analytics code stays local and explicit. Do not install the package from PyPI alone or infer data rights from a library tier.
