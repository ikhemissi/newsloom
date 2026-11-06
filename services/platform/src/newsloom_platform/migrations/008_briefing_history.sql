CREATE TABLE public.briefing_history (
    version uuid PRIMARY KEY,
    cutoff timestamptz NOT NULL,
    editorial_policy text,
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    payload jsonb NOT NULL CHECK (
        jsonb_typeof(payload) = 'object' AND payload->>'version' = version::text
    )
);
CREATE INDEX briefing_history_cutoff ON public.briefing_history (cutoff);

-- Keep what still exists: the current briefing and briefings superseded by revisions.
INSERT INTO public.briefing_history (version, cutoff, editorial_policy, published_at, payload)
SELECT (payload->>'version')::uuid, (payload->>'window_end')::timestamptz,
    payload->>'editorial_policy', (payload->>'generated_at')::timestamptz, payload
FROM public.briefing_current
UNION ALL
SELECT (prior_payload->>'version')::uuid, (prior_payload->>'window_end')::timestamptz,
    prior_payload->>'editorial_policy', (prior_payload->>'generated_at')::timestamptz,
    prior_payload
FROM public.briefing_revisions
ON CONFLICT (version) DO NOTHING;

REVOKE ALL ON public.briefing_history FROM PUBLIC;
GRANT SELECT, INSERT ON public.briefing_history TO newsloom_briefing;
GRANT SELECT ON public.briefing_history TO newsloom_mcp;
