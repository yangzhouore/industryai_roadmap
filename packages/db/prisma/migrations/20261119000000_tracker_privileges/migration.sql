-- The tracker has an explicit curator. The routine worker only reads tracker tables.
DO $tracker_privileges$
DECLARE
    target_schema text := current_schema();
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'industrial_web') THEN
        EXECUTE format(
            'GRANT SELECT ON TABLE %1$I.tracker_milestones, %1$I.tracker_milestone_revisions,
                %1$I.tracker_evidence, %1$I.tracker_revision_companies, %1$I.tracker_revision_technologies
                TO industrial_web',
            target_schema
        );
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'industrial_worker') THEN
        EXECUTE format(
            'REVOKE INSERT, UPDATE ON TABLE %1$I.tracker_companies, %1$I.tracker_company_aliases,
                %1$I.tracker_technologies, %1$I.tracker_technology_aliases, %1$I.tracker_projects,
                %1$I.tracker_milestones, %1$I.tracker_milestone_revisions, %1$I.tracker_evidence,
                %1$I.tracker_revision_companies, %1$I.tracker_revision_technologies
                FROM industrial_worker',
            target_schema
        );
    END IF;
END;
$tracker_privileges$;
