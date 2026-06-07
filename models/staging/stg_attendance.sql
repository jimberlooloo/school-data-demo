-- LA × week × phase grain.
-- Filtered to Local authority rows; the all-phase "Total" row dropped.
-- Numerics use try_cast so EES suppression markers (c/x/z/low) become NULL.
select
    cast(time_period as integer)                 as academic_year,
    time_identifier                              as week_label,
    lpad(old_la_code, 3, '0')                    as la_code,
    la_name,
    school_type                                  as phase,
    try_cast(possible_sessions as integer)       as possible_sessions,
    try_cast(overall_absence_perc as float)      as pct_overall_absence,
    try_cast(authorised_absence_perc as float)   as pct_authorised_absence,
    try_cast(unauthorised_absence_perc as float) as pct_unauthorised_absence,
    try_cast(attendance_perc as float)           as pct_attendance
from {{ source('raw', 'raw_attendance') }}
where geographic_level = 'Local authority'
  and school_type <> 'Total'
  -- data-quality guard: drop negligible-reporting weeks (real LA-weeks have 100k+
  -- sessions; a near-empty submission produced a bogus 100% absence on 20 sessions).
  and try_cast(possible_sessions as integer) >= 1000
