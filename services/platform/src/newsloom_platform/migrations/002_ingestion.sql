CREATE TABLE public.feed_sources (
    id text PRIMARY KEY,
    configuration jsonb NOT NULL,
    etag text,
    last_modified text,
    checked_at timestamptz,
    last_run text,
    outcome text,
    counts jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE public.ingestion_queue (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL REFERENCES public.feed_sources(id),
    guid text,
    canonical_url text NOT NULL UNIQUE,
    entry jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status = 'pending'),
    score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
    threshold double precision NOT NULL CHECK (threshold BETWEEN 0 AND 1),
    model text NOT NULL,
    model_version text NOT NULL,
    correlation_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source, guid)
);

CREATE TABLE public.quarantine (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL REFERENCES public.feed_sources(id),
    guid text,
    canonical_url text NOT NULL UNIQUE,
    entry jsonb NOT NULL,
    disposition text NOT NULL CHECK (disposition IN ('rejected', 'deferred', 'resolved')),
    reason text NOT NULL CHECK (reason ~ '^[a-z0-9_]+$'),
    score double precision CHECK (score BETWEEN 0 AND 1),
    threshold double precision CHECK (threshold BETWEEN 0 AND 1),
    model text NOT NULL,
    model_version text NOT NULL,
    correlation_id text NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    retry_after timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_queue_id uuid REFERENCES public.ingestion_queue(id),
    UNIQUE (source, guid)
);

CREATE INDEX quarantine_retry ON public.quarantine (retry_after, created_at)
WHERE disposition = 'deferred';

REVOKE ALL ON public.feed_sources, public.ingestion_queue, public.quarantine FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO newsloom_ingestion;
GRANT SELECT, INSERT, UPDATE ON
    public.feed_sources, public.ingestion_queue, public.quarantine TO newsloom_ingestion;
