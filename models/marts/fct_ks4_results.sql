-- KS4 (GCSE) results fact — grain: school × academic year.
-- FK urn -> dim_school.urn is a clean FK-to-PK (tested in _marts.yml).
select
    md5(urn::string || '|' || academic_year::string) as ks4_key,
    urn,
    school_name,
    la_name,
    academic_year,
    attainment8_score,
    pct_grade5_eng_maths,
    ebacc_aps
from {{ ref('stg_ks4') }}
