-- Insight 1: secondary absence vs GCSE Attainment 8, by LA absence quartile.
-- Joins the two facts at LA level (attendance is LA-grain) for secondary schools.
with la_absence as (
    select la_code, avg(pct_overall_absence) as avg_secondary_absence
    from {{ ref('fct_attendance_weekly') }}
    where phase = 'Secondary'
    group by 1
),
la_attainment as (
    select d.la_code, avg(f.attainment8_score) as avg_attainment8
    from {{ ref('fct_ks4_results') }} f
    join {{ ref('dim_school') }} d on d.urn = f.urn
    where d.is_secondary
    group by 1
),
joined as (
    select a.la_code, a.avg_secondary_absence, t.avg_attainment8
    from la_absence a
    join la_attainment t on a.la_code = t.la_code
)
select
    ntile(4) over (order by avg_secondary_absence) as absence_quartile,
    round(avg(avg_secondary_absence), 2)           as mean_absence_pct,
    round(avg(avg_attainment8), 2)                 as mean_attainment8,
    count(*)                                       as n_las
from joined
group by 1
order by 1
-- overall correlation: select corr(avg_secondary_absence, avg_attainment8) from joined;  -> -0.60
