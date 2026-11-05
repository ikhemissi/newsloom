CREATE TABLE public.feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reader_hash text NOT NULL CHECK (reader_hash ~ '^[0-9a-f]{64}$'),
    target_type text NOT NULL CHECK (target_type IN ('briefing', 'research')),
    target_ref text NOT NULL CHECK (char_length(target_ref) BETWEEN 1 AND 200),
    rating smallint NOT NULL CHECK (rating IN (-1, 1)),
    comment text CHECK (comment IS NULL OR char_length(comment) BETWEEN 1 AND 1000),
    snapshot jsonb CHECK (snapshot IS NULL OR jsonb_typeof(snapshot) = 'object'),
    snapshot_source text CHECK (snapshot_source IS NULL OR snapshot_source = 'client'),
    CHECK ((target_type = 'research') = (snapshot IS NOT NULL)),
    CHECK ((snapshot IS NULL) = (snapshot_source IS NULL))
);
-- Latest vote per reader and item is resolved at read time; rows are never updated.
CREATE INDEX feedback_latest ON public.feedback (target_type, target_ref, reader_hash, created_at DESC);
CREATE INDEX feedback_created ON public.feedback (created_at);

REVOKE ALL ON public.feedback FROM PUBLIC;
GRANT SELECT, INSERT ON public.feedback TO newsloom_mcp;
