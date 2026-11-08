-- Announcements extracted from news, linked to canonical vendors and products.
ALTER TABLE public.news
    ADD COLUMN article_kind text CHECK (article_kind IN (
        'announcement','roundup','security','retirement','regulation','case_study',
        'opinion','tutorial','other'
    )),
    ADD COLUMN search_text tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', title || ' ' || summary)
    ) STORED;

CREATE INDEX news_search_text ON public.news USING gin (search_text);

CREATE TABLE public.entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ('vendor','product')),
    vendor_id uuid REFERENCES public.entities(id),
    canonical_name text NOT NULL CHECK (
        length(btrim(canonical_name)) BETWEEN 1 AND 120
    ),
    embedding vector(1536) CHECK (embedding IS NULL OR vector_norm(embedding) > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((kind = 'vendor') = (vendor_id IS NULL))
);

-- Aliases are normalised names; product aliases are unique within their vendor.
CREATE TABLE public.entity_aliases (
    alias text NOT NULL CHECK (alias ~ '^[0-9a-z+#.]+( [0-9a-z+#.]+)*$'),
    vendor_id uuid REFERENCES public.entities(id),
    entity_id uuid NOT NULL REFERENCES public.entities(id),
    method text NOT NULL CHECK (method IN ('curated','canonical','exact','similar')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE NULLS NOT DISTINCT (vendor_id, alias)
);

CREATE INDEX entity_aliases_entity ON public.entity_aliases (entity_id);

CREATE TABLE public.announcements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id uuid NOT NULL REFERENCES public.news(id),
    ordinal smallint NOT NULL CHECK (ordinal BETWEEN 0 AND 29),
    statement text NOT NULL CHECK (length(btrim(statement)) BETWEEN 1 AND 400),
    change_type text NOT NULL CHECK (change_type IN (
        'launch','update','availability','pricing','deprecation','retirement','security',
        'policy','other'
    )),
    status text NOT NULL CHECK (status IN (
        'announced','preview','ga','updated','deprecated','retired','none'
    )),
    effective_date date,
    deadline date,
    search_text tsvector GENERATED ALWAYS AS (to_tsvector('simple', statement)) STORED,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (news_id, ordinal)
);

CREATE INDEX announcements_search_text ON public.announcements USING gin (search_text);
CREATE INDEX announcements_deadline ON public.announcements (deadline) WHERE deadline IS NOT NULL;

CREATE TABLE public.announcement_entities (
    announcement_id uuid NOT NULL REFERENCES public.announcements(id),
    entity_id uuid NOT NULL REFERENCES public.entities(id),
    method text NOT NULL CHECK (method IN ('curated','exact','similar','new')),
    PRIMARY KEY (announcement_id, entity_id)
);

CREATE INDEX announcement_entities_entity ON public.announcement_entities (entity_id);

CREATE TABLE public.entity_relations (
    source_id uuid NOT NULL REFERENCES public.entities(id),
    target_id uuid NOT NULL REFERENCES public.entities(id),
    relation text NOT NULL CHECK (relation IN ('part_of','replaces')),
    announcement_id uuid REFERENCES public.announcements(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_id, target_id, relation),
    CHECK (source_id <> target_id)
);

REVOKE ALL ON public.entities, public.entity_aliases, public.announcements,
    public.announcement_entities, public.entity_relations FROM PUBLIC;
GRANT SELECT, INSERT ON public.entities, public.entity_aliases, public.announcements,
    public.announcement_entities, public.entity_relations TO newsloom_enrichment;
GRANT UPDATE (article_kind) ON public.news TO newsloom_enrichment;
GRANT SELECT ON public.entities, public.entity_aliases, public.announcements,
    public.announcement_entities, public.entity_relations TO newsloom_mcp;
GRANT SELECT (article_kind, search_text) ON public.news TO newsloom_mcp;
