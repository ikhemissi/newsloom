ALTER TABLE public.ingestion_queue
    DROP CONSTRAINT ingestion_queue_status_check,
    ADD CONSTRAINT ingestion_queue_status_check
        CHECK (status IN ('pending','processing','completed','failed','dead_letter')),
    ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    ADD COLUMN retry_after timestamptz NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN lease_token uuid,
    ADD COLUMN lease_until timestamptz,
    ADD COLUMN started_at timestamptz,
    ADD COLUMN completed_at timestamptz,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN last_error text CHECK (last_error ~ '^[a-z0-9_]+$'),
    ADD COLUMN enrichment_run_id text,
    ADD CONSTRAINT ingestion_queue_lease_check CHECK (
        (status='processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
        OR (status<>'processing' AND lease_token IS NULL AND lease_until IS NULL)
    ),
    ADD CONSTRAINT ingestion_queue_completion_check
        CHECK ((status='completed') = (completed_at IS NOT NULL));

CREATE INDEX ingestion_queue_claim ON public.ingestion_queue (created_at, id)
WHERE status IN ('pending','failed');
CREATE INDEX ingestion_queue_expired ON public.ingestion_queue (lease_until)
WHERE status='processing';

CREATE TABLE public.news (
    id uuid PRIMARY KEY REFERENCES public.ingestion_queue(id),
    source text NOT NULL REFERENCES public.feed_sources(id),
    guid text,
    canonical_url text NOT NULL UNIQUE,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    published_at timestamptz NOT NULL,
    date_origin text NOT NULL CHECK (date_origin IN ('published','updated','retrieved')),
    author text NOT NULL,
    publisher_categories text[] NOT NULL,
    summary text NOT NULL CHECK (
        length(btrim(summary)) > 0
        AND cardinality(regexp_split_to_array(btrim(summary), '[[:space:]]+')) <= 100
    ),
    category text NOT NULL CHECK (category IN (
        'regulations','models','agents-applications','developer-tools','infrastructure',
        'research-evaluations','security-safety','governance','industry-business',
        'service-providers','finops'
    )),
    tags text[] NOT NULL CHECK (
        cardinality(tags) BETWEEN 3 AND 5 AND array_position(tags,NULL) IS NULL
    ),
    embedding vector(1536) NOT NULL CHECK (vector_norm(embedding) > 0),
    generation_model text NOT NULL,
    generation_version text NOT NULL,
    embedding_model text NOT NULL,
    embedding_version text NOT NULL,
    prompt_revision text NOT NULL CHECK (prompt_revision ~ '^[a-f0-9]{64}$'),
    taxonomy_revision text NOT NULL CHECK (taxonomy_revision ~ '^[a-f0-9]{64}$'),
    enrichment_run_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source,guid)
);

CREATE INDEX news_published ON public.news (published_at DESC);
CREATE INDEX news_source_published ON public.news (source,published_at DESC);
CREATE INDEX news_category_published ON public.news (category,published_at DESC);
CREATE INDEX news_tags ON public.news USING gin (tags);
CREATE INDEX news_embedding ON public.news USING hnsw (embedding vector_cosine_ops);

REVOKE ALL ON public.news FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO newsloom_enrichment;
GRANT SELECT ON public.ingestion_queue TO newsloom_enrichment;
GRANT UPDATE (
    status,attempts,retry_after,lease_token,lease_until,started_at,completed_at,
    updated_at,last_error,enrichment_run_id
) ON public.ingestion_queue TO newsloom_enrichment;
GRANT SELECT,INSERT ON public.news TO newsloom_enrichment;
