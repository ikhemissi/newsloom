-- Article acquisition outcome and the original feed text when the article body replaced it.
ALTER TABLE public.quarantine
    ADD COLUMN acquisition text CHECK (acquisition ~ '^[a-z0-9_]+$'),
    ADD COLUMN feed_text text;

ALTER TABLE public.ingestion_queue
    ADD COLUMN acquisition text CHECK (acquisition ~ '^[a-z0-9_]+$'),
    ADD COLUMN feed_text text,
    ADD COLUMN acquired_at timestamptz;
