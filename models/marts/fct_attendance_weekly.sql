-- Attendance fact — grain: LA × week × phase.
-- Surrogate key over the full grain enforces uniqueness (tested in _marts.yml).
select
    md5(la_code || '|' || academic_year::string || '|' || week_label || '|' || phase) as attendance_key,
    la_code,
    academic_year,
    week_label,
    phase,
    possible_sessions,
    pct_overall_absence,
    pct_authorised_absence,
    pct_unauthorised_absence,
    pct_attendance
from {{ ref('stg_attendance') }}
