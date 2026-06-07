-- Least-privilege setup for the school-data pipeline.
-- Run ONCE as ACCOUNTADMIN. Creates a scoped role + key-pair SERVICE user so the
-- RSA key unlocks ONLY this pipeline's privileges, not the whole account.
-- (Public keys are not secrets, so this file is safe to commit — it documents the security model.)

USE ROLE ACCOUNTADMIN;

-- 1. Dedicated role -------------------------------------------------------------
CREATE ROLE IF NOT EXISTS TRANSFORMER;
GRANT ROLE TRANSFORMER TO ROLE SYSADMIN;            -- so admins retain manageability

-- 2. Least-privilege grants -----------------------------------------------------
GRANT USAGE ON WAREHOUSE COMPUTE_WH        TO ROLE TRANSFORMER;
GRANT USAGE ON DATABASE  SCHOOLS           TO ROLE TRANSFORMER;
GRANT CREATE SCHEMA ON DATABASE SCHOOLS    TO ROLE TRANSFORMER;   -- dbt creates ANALYTICS (role owns it)

-- RAW landing schema already exists (made by ACCOUNTADMIN); let TRANSFORMER build objects in it
GRANT USAGE ON SCHEMA SCHOOLS.RAW          TO ROLE TRANSFORMER;
GRANT CREATE TABLE, CREATE STAGE, CREATE FILE FORMAT, CREATE VIEW
  ON SCHEMA SCHOOLS.RAW                     TO ROLE TRANSFORMER;

-- 3. Dedicated key-pair service identity (no password; key-pair only) -----------
CREATE USER IF NOT EXISTS DBT_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = TRANSFORMER
  DEFAULT_WAREHOUSE = COMPUTE_WH
  COMMENT = 'Key-pair service identity for the school-data dbt pipeline (least privilege)';

ALTER USER DBT_SVC SET RSA_PUBLIC_KEY='<your_rsa_public_key_base64>';

GRANT ROLE TRANSFORMER TO USER DBT_SVC;

-- 4. Remove the key from the human admin user -----------------------------------
-- Key now unlocks ONLY the scoped DBT_SVC. <your_admin_user> keeps Snowsight password login.
-- (Runs last so a failure above never strands us without the admin key.)
ALTER USER <your_admin_user> UNSET RSA_PUBLIC_KEY;
