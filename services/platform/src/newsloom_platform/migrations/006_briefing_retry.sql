CREATE TABLE public.briefing_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cutoff timestamptz NOT NULL REFERENCES public.briefing_runs(cutoff),
    archived_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_call_ordinal integer NOT NULL CHECK (last_call_ordinal >= 0),
    failed_run jsonb NOT NULL CHECK (
        jsonb_typeof(failed_run) = 'object'
        AND failed_run ? 'status'
        AND failed_run->>'status' = 'failed'
    ),
    UNIQUE (cutoff, last_call_ordinal)
);
REVOKE ALL ON public.briefing_attempts FROM PUBLIC;
GRANT SELECT, INSERT ON public.briefing_attempts TO newsloom_briefing;
