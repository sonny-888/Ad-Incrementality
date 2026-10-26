-- Headline experiment numbers in plain SQL (DuckDB), as an independent check on the Python analysis.
-- Expects a table or view named `criteo` with the Criteo Uplift v2.1 columns;
-- python/tests/test_sql_lift.py creates it from data/processed/criteo_uplift.parquet and checks every
-- column below against results/ produced by the Python pipeline.
--
-- These are the raw (unadjusted) estimates. The adjusted, doubly robust figures need fitted models and are
-- computed in Python (python/incrementality/lift.py).

WITH groups AS (
  SELECT
    count(*)                                                        AS n,
    count(*) FILTER (WHERE treatment = 1)                           AS n_t,
    count(*) FILTER (WHERE treatment = 0)                           AS n_c,
    count(*) FILTER (WHERE treatment = 1 AND exposure = 1)          AS n_exposed,
    count(*) FILTER (WHERE treatment = 0 AND exposure = 1)          AS n_control_exposed,  -- must be 0
    avg(conversion) FILTER (WHERE treatment = 1)                    AS r_t,
    avg(conversion) FILTER (WHERE treatment = 0)                    AS r_c,
    avg(conversion) FILTER (WHERE exposure = 1)                     AS r_exposed,
    avg(conversion) FILTER (WHERE exposure = 0)                     AS r_unexposed,
    avg(conversion) FILTER (WHERE treatment = 1 AND exposure = 0)   AS r_never_exposed
  FROM criteo
),

stats AS (
  SELECT
    *,
    n_t / n                                                         AS treated_share,
    -- Sample ratio mismatch: chi-square of the observed split against the designed 85/15 (1 degree of freedom)
    power(n_t - 0.85 * n, 2) / (0.85 * n) + power(n_c - 0.15 * n, 2) / (0.15 * n) AS srm_chi2,
    -- Intent-to-treat: whole treatment group vs control, as randomly assigned
    r_t - r_c                                                       AS itt,
    sqrt(r_t * (1 - r_t) / n_t + r_c * (1 - r_c) / n_c)             AS itt_se,
    n_exposed / n_t                                                 AS exposure_share
  FROM groups
)

SELECT
  n,
  treated_share,
  srm_chi2,
  n_control_exposed,
  r_exposed / r_unexposed                                           AS naive_multiple,     -- the dashboard view
  itt,
  itt - 1.959964 * itt_se                                           AS itt_lo,
  itt + 1.959964 * itt_se                                           AS itt_hi,
  r_t / r_c - 1                                                     AS itt_relative,
  exposure_share,
  -- Effect of actually seeing an ad (CACE): instrumental variables / Wald estimator, valid because
  -- random assignment shifts exposure and no control user can be exposed
  itt / exposure_share                                              AS cace,
  -- Conversion rate the exposed users would have had without the ad
  (r_c - (1 - exposure_share) * r_never_exposed) / exposure_share   AS baseline_exposed,
  r_exposed,
  -- Share of conversions after an ad view (what view-through attribution credits) that the ad caused
  (itt / exposure_share) / r_exposed                                AS caused_share
FROM stats;
