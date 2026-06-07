-- One row per currently-open establishment (school grain, PK = urn).
-- Raw is all-STRING; here we cast, rename, and filter to open schools.
-- Includes 'Open, but proposed to close' (still operating, and some sat 2024/25 KS4).
select
    cast(urn as integer)        as urn,
    establishment_name,
    phase_name                  as phase,
    lpad(la_code, 3, '0')       as la_code,
    la_name,
    region_name                 as region,
    establishment_status
from {{ source('raw', 'raw_gias') }}
where establishment_status in ('Open', 'Open, but proposed to close')
