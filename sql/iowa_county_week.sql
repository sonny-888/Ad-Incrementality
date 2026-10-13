-- Iowa liquor sales: weekly sales per county, for the simulated geo tests (finding 8).
-- Methods demonstration: real data, simulated campaign.
--
-- How to run (you sign in yourself; no keys or logins are stored anywhere in this project):
--   1. Open https://console.cloud.google.com/bigquery with your sandbox project selected.
--   2. Paste this whole query into the editor. Top right shows "This query will process ... GB";
--      it should be a few GB, well inside the free 1 TB a month.
--   3. Run. Then Save results > CSV (local file).
--   4. Save it as data/raw/iowa_county_week.csv in this project.
--
-- Output: one row per county per week (weeks start on Monday) from 2016 onwards.

WITH sales AS (
  SELECT
    date,
    store_number,
    UPPER(TRIM(county)) AS county_raw,
    sale_dollars,
    volume_sold_liters
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE date >= DATE '2016-01-01'
),

-- A few rows have no county. Fill them from the county that the same store reports most often.
store_county AS (
  SELECT store_number, county_raw
  FROM (
    SELECT
      store_number,
      county_raw,
      ROW_NUMBER() OVER (PARTITION BY store_number ORDER BY COUNT(*) DESC, county_raw) AS rank_in_store
    FROM sales
    WHERE county_raw IS NOT NULL AND county_raw != ''
    GROUP BY store_number, county_raw
  )
  WHERE rank_in_store = 1
)

SELECT
  COALESCE(NULLIF(s.county_raw, ''), sc.county_raw) AS county,
  DATE_TRUNC(s.date, WEEK(MONDAY)) AS week,
  ROUND(SUM(s.sale_dollars), 2) AS sales_dollars,
  ROUND(SUM(s.volume_sold_liters), 2) AS volume_liters,
  COUNT(*) AS line_items,
  COUNT(DISTINCT s.store_number) AS stores
FROM sales AS s
LEFT JOIN store_county AS sc
  ON s.store_number = sc.store_number
GROUP BY county, week
ORDER BY county, week;
