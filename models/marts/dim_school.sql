-- School dimension — grain: school, PK = urn (open schools, all phases).
-- is_secondary flags Secondary + All-through, the population for the cross-fact insight.
select
    urn,
    establishment_name,
    phase,
    phase in ('Secondary', 'All-through') as is_secondary,
    la_code,
    la_name,
    region
from {{ ref('stg_gias') }}
