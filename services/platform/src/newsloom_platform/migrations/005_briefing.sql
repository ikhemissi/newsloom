CREATE TABLE public.briefing_runs (
    cutoff timestamptz PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('running', 'ready', 'failed')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    error_category text CHECK (error_category IS NULL OR error_category ~ '^[a-z][a-z0-9_]{0,79}$'),
    evidence_count bigint CHECK (evidence_count >= 0),
    evidence_sha256 text CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    prompt_revision text NOT NULL,
    model text NOT NULL,
    model_version text NOT NULL,
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK ((status = 'running' AND finished_at IS NULL)
        OR (status <> 'running' AND finished_at IS NOT NULL))
);

CREATE TABLE public.briefing_calls (
    cutoff timestamptz NOT NULL REFERENCES public.briefing_runs(cutoff),
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    stage text NOT NULL CHECK (stage IN ('notes', 'reduce', 'summary', 'tldr')),
    status text NOT NULL CHECK (status IN ('pending', 'completed', 'unknown')),
    input_tokens bigint CHECK (input_tokens >= 0),
    output_tokens bigint CHECK (output_tokens >= 0),
    elapsed_seconds double precision CHECK (
        elapsed_seconds >= 0 AND elapsed_seconds < 'Infinity'::double precision),
    estimated_cost_usd numeric CHECK (
        estimated_cost_usd >= 0 AND estimated_cost_usd < 'Infinity'::numeric),
    price_basis text NOT NULL,
    PRIMARY KEY (cutoff, ordinal)
);

CREATE TABLE public.briefing_current (
    singleton boolean PRIMARY KEY CHECK (singleton),
    cutoff timestamptz NOT NULL UNIQUE REFERENCES public.briefing_runs(cutoff),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object')
);

CREATE VIEW public.briefing_status AS
SELECT cutoff, status, started_at, finished_at, error_category
FROM public.briefing_runs;

REVOKE ALL ON public.briefing_runs, public.briefing_calls,
    public.briefing_current, public.briefing_status FROM PUBLIC;
GRANT CONNECT ON DATABASE newsloom TO newsloom_briefing;
GRANT USAGE ON SCHEMA public TO newsloom_briefing;
GRANT SELECT (id, title, summary, source, category, tags, published_at, canonical_url)
    ON public.news TO newsloom_briefing;
GRANT SELECT, INSERT, UPDATE ON public.briefing_runs, public.briefing_calls,
    public.briefing_current TO newsloom_briefing;
GRANT SELECT ON public.briefing_current, public.briefing_status TO newsloom_mcp;
