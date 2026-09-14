# CLUP Monitoring Module

This module runs inside the SOCOCA Monitoring Portal and uses the Incident Dashboard's existing Supabase Auth session and `accounts` table.

## Access

- Super Admin and Admin: view, create, update, and delete CLUP dashboards.
- Operator: view and upload data only for the dashboard assigned in the portal's Admin Settings.

## Database setup

Run `supabase_setup.sql` once in the same Supabase project used by the portal. It creates only `clup_dashboards` and `clup_upload_history`; it does not reset existing data or create another account system.
