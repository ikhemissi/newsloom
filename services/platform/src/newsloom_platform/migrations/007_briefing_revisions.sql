CREATE TABLE public.briefing_revisions (
    request_id uuid PRIMARY KEY,
    cutoff timestamptz NOT NULL REFERENCES public.briefing_runs(cutoff),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reason text NOT NULL CHECK (reason IN ('editorial-policy-upgrade')),
    base_version uuid NOT NULL,
    last_call_ordinal integer NOT NULL CHECK (last_call_ordinal >= 0),
    prior_run jsonb NOT NULL CHECK (
        jsonb_typeof(prior_run) = 'object'
        AND prior_run->>'status' IN ('ready', 'failed')
    ),
    prior_payload jsonb NOT NULL CHECK (
        jsonb_typeof(prior_payload) = 'object'
        AND prior_payload->>'version' = base_version::text
    ),
    UNIQUE (cutoff, last_call_ordinal)
);
REVOKE ALL ON public.briefing_revisions FROM PUBLIC;
GRANT SELECT, INSERT ON public.briefing_revisions TO newsloom_briefing;
