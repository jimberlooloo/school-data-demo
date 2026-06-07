-- School × academic-year grain (PK = urn).
-- Filtered to the all-pupils headline rows (breakdown_topic = 'Total') so each URN
-- appears once — the unique(urn) test in _staging.yml enforces this.
-- Progress 8 deliberately excluded (not published for 2024/25; see SPEC §7).
select
    cast(school_urn as integer)                  as urn,
    school_name,
    la_name,
    cast(time_period as integer)                 as academic_year,
    try_cast(attainment8_average as float)       as attainment8_score,
    try_cast(gcse_five_engmath_percent as float) as pct_grade5_eng_maths,
    try_cast(ebacc_aps_average as float)         as ebacc_aps
from {{ source('raw', 'raw_ks4') }}
where breakdown_topic = 'Total'
