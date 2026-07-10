# RF-CEM Literature Semantics Audit Workflow

Last updated: 2026-07-07

## Workflow

MVP 使用人工上传包，不做论文下载器或完整 RAG。

```text
1. Human prepares uploaded package
2. validate literature_semantics.v0.json
3. generate expert_prior.draft.v0.yaml
4. write audit HTML
5. expert reviews each patch item
6. merge reviewed draft into expert_prior.v0.yaml override
7. run existing no-CST geometry path
```

## CLI

```powershell
python -m rf_cem.literature_semantics validate --package <dir-or-json>
python -m rf_cem.literature_semantics draft-prior --package <path> --base-prior <path> --out <yaml>
python -m rf_cem.literature_semantics audit --package <path> --draft-prior <path> --out <html>
python -m rf_cem.literature_semantics merge-prior --base-prior <path> --draft-prior <path> --out <yaml> --require-reviewed
```

## Audit HTML

Audit report sections:

- Corpus summary: source, year, venue, operating regime, family, license/version.
- Evidence cards: short excerpt, figure caption, page, figure id, bbox/crop provenance.
- Prior diff: every proposed patch item with evidence refs and review status.
- Candidate gallery: 2-3 candidate shape priors and no-CST validation status.
- Review controls: `accept`, `accept_as_soft_only`, `reject`, `needs_more_evidence`.

The HTML is intentionally static. It does not write review decisions back to YAML; the expert edits the draft YAML or a review overlay before merge.

## Human Checklist

- Confirm operating regime: `superconducting` vs `normal_conducting`.
- Confirm cavity family and cell count match the user intent.
- Confirm every nonbaseline change has `source_refs`, `confidence`, `scope`, `applicability`, and `human_review_status`.
- Keep image-only and single-source numeric claims soft.
- Check units: frequency in MHz, length in mm, angle in degrees, ratios dimensionless.
- Make sure no HOM, coupler, wakefield, thermal, structural, multipacting, cooling, or tuner semantics enter executable prior fields.
- Confirm NC nose/reentrant evidence does not alter SRF elliptical defaults.
- Confirm unsupported parameters such as wall angle or ellipse ratios remain metadata until the generator supports them.

## Conflict Policy

Precedence:

```text
reviewed_feature_labels
  > baseline_geometry
  > human accepted multi-source text/hybrid literature
  > single-source text literature
  > image-only literature
```

If evidence conflicts:

- Do not delete existing reviewed feature mappings.
- Do not override baseline-derived geometry facts.
- Keep single-paper claims as soft metadata.
- Keep image-only claims motif-level.
- Split NC and SRF branches before candidate generation.

## Acceptance

The literature semantic MVP is accepted when:

- invalid packages fail validation with clear paths;
- pending drafts cannot merge with `--require-reviewed`;
- reviewed SRF packages produce smooth/free-equator candidates;
- reviewed NC packages produce controlled nose/reentrant candidates;
- merged prior changes only supported `expert_prior.v0.yaml` fields or additive audit metadata;
- no natural language, image-only hard rule, downloader, optimizer, HOM/coupler logic, multiphysics logic, or unverified CST API enters the generation path.
