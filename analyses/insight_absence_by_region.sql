-- Insight 2: mean secondary absence by region.
-- Region comes from dim_school (school grain); collapse to one region per LA, then
-- join to the LA-grain attendance fact.
with la_region as (
    select la_code, max(region) as region
    from {{ ref('dim_school') }}
    group by 1
)
select
    coalesce(r.region, '(unmapped)')          as region,
    round(avg(f.pct_overall_absence), 2)      as mean_secondary_absence,
    count(distinct f.la_code)                 as n_las
from {{ ref('fct_attendance_weekly') }} f
left join la_region r on r.la_code = f.la_code
where f.phase = 'Secondary'
group by 1
order by 2 desc
