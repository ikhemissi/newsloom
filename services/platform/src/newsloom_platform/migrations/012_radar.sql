-- Architect radar: announcement triage and per-reader stack and card state.
ALTER TABLE public.announcements
    ADD COLUMN tier text CHECK (tier IN ('act_now','worth_knowing','later')),
    ADD COLUMN reason text CHECK (length(btrim(reason)) BETWEEN 1 AND 200),
    ADD COLUMN capability text CHECK (capability ~ '^[a-z0-9][a-z0-9+#. -]{0,59}$'),
    ADD COLUMN triaged_at timestamptz,
    ADD CONSTRAINT announcements_triage_check CHECK (
        (tier IS NULL) = (triaged_at IS NULL)
        AND (tier IS NULL OR (reason IS NOT NULL AND capability IS NOT NULL))
    );

CREATE INDEX announcements_untriaged ON public.announcements (created_at) WHERE tier IS NULL;

-- Readers are the pseudonymous key also used by feedback (sha256 hex), never names or IDs.
CREATE TABLE public.reader_stack (
    reader text NOT NULL CHECK (reader ~ '^[0-9a-f]{64}$'),
    entity_id uuid NOT NULL REFERENCES public.entities(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (reader, entity_id)
);

CREATE TABLE public.reader_card_state (
    reader text NOT NULL CHECK (reader ~ '^[0-9a-f]{64}$'),
    announcement_id uuid NOT NULL REFERENCES public.announcements(id),
    state text NOT NULL CHECK (state IN ('done','snoozed')),
    snoozed_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (reader, announcement_id),
    CHECK ((state = 'snoozed') = (snoozed_until IS NOT NULL))
);

REVOKE ALL ON public.reader_stack, public.reader_card_state FROM PUBLIC;
GRANT UPDATE (tier, reason, capability, triaged_at) ON public.announcements TO newsloom_enrichment;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reader_stack, public.reader_card_state TO newsloom_mcp;
