GRANT USAGE ON SCHEMA public TO newsloom_mcp;
GRANT SELECT (
    id,title,summary,source,category,tags,published_at,canonical_url,
    author,date_origin,publisher_categories,embedding,embedding_model,embedding_version
) ON public.news TO newsloom_mcp;
