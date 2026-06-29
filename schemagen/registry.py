"""Metadata for every schema type the generator can build.

Each entry maps a short CLI key to:
  schema_type   the schema.org @type as it appears in the template (kept as-is,
                including house-style choices like the LocalBusiness subtype)
  fragment      the @id fragment used when the node is placed in an @graph
  template      the cleaned skeleton file in templates/
  prompt_fields the handful of "varies per business" fields the interactive
                prompt asks about by default (any field is still overridable
                via --set key=value)

Structure is taken verbatim from the user's Schema Templates; only JSON-breaking
issues were repaired when the skeletons were built (see tools/build_templates.py).
"""

# Default node order when assembling a full-site @graph (identity first, then
# page, then content).
GRAPH_ORDER = [
    "organization",
    "localbusiness",
    "website",
    "webpage",
    "breadcrumb",
    "article",
    "person",
]

TYPES = {
    "organization": {
        "schema_type": "Organization",
        "fragment": "organization",
        "template": "organization.json",
        "prompt_fields": ["name", "legalName", "url", "logo", "description",
                          "disambiguatingDescription"],
        "blurb": "Site-wide brand identity; sameAs = all social profiles.",
    },
    "localbusiness": {
        "schema_type": "LocalBusiness",  # set @type to your industry subtype per client
        "fragment": "localbusiness",
        "template": "localbusiness.json",
        "prompt_fields": ["name", "url", "description",
                          "disambiguatingDescription", "telePhone", "priceRange"],
        "blurb": "Local SEO node; set @type to your industry subtype.",
    },
    "website": {
        "schema_type": "WebSite",
        "fragment": "website",
        "template": "website.json",
        "prompt_fields": ["url", "name", "alternateName", "description",
                          "disambiguatingDescription"],
        "blurb": "Site-level node with the sitelinks SearchAction.",
    },
    "webpage": {
        "schema_type": "WebPage",
        "fragment": "webpage",
        "template": "webpage.json",
        "prompt_fields": ["headline", "url", "description",
                          "disambiguatingDescription", "mainEntityOfPage"],
        "blurb": "Per-page node with about/mentions entity arrays.",
    },
    "article": {
        "schema_type": "Article",
        "fragment": "article",
        "template": "article.json",
        "prompt_fields": ["headline", "url", "author", "datePublished",
                          "description", "disambiguatingDescription"],
        "blurb": "Blog/article node (use newsArticle for actual news).",
    },
    "product": {
        "schema_type": "Product",
        "fragment": "product",
        "template": "product.json",
        "prompt_fields": ["name", "url", "brand", "sku", "description"],
        "blurb": "E-commerce / product-review node.",
    },
    "breadcrumb": {
        "schema_type": "BreadcrumbList",
        "fragment": "breadcrumb",
        "template": "breadcrumb.json",
        "prompt_fields": ["mainEntityOfPage"],
        "blurb": "Breadcrumb rich snippet (4 items).",
    },
    "person": {
        "schema_type": "Person",
        "fragment": "person",
        "template": "person.json",
        "prompt_fields": ["name", "jobTitle", "url", "description",
                          "disambiguatingDescription"],
        "blurb": "Author/owner node.",
    },
    "service": {
        "schema_type": "Service",
        "fragment": "service",
        "template": "service.json",
        "prompt_fields": ["name", "description", "disambiguatingDescription"],
        "blurb": "Service offering with hasOfferCatalog.",
    },
    "howto": {
        "schema_type": "HowTo",
        "fragment": "howto",
        "template": "howto.json",
        "prompt_fields": ["name", "description"],
        "blurb": "Step-by-step HowTo node.",
    },
    "book": {
        "schema_type": "Book",
        "fragment": "book",
        "template": "book.json",
        "prompt_fields": ["name"],
        "blurb": "Book (wrapped in a WebPage mainEntity).",
    },
    "recipe": {
        "schema_type": "Recipe",
        "fragment": "recipe",
        "template": "recipe.json",
        "prompt_fields": ["name", "author", "description"],
        "blurb": "Recipe node with steps.",
    },
    "video": {
        "schema_type": "VideoObject",
        "fragment": "video",
        "template": "video.json",
        "prompt_fields": ["name", "description", "contentUrl", "thumbnailUrl"],
        "blurb": "VideoObject node.",
    },
    "jobposting": {
        "schema_type": "JobPosting",
        "fragment": "jobposting",
        "template": "jobposting.json",
        "prompt_fields": ["title", "name", "description", "baseSalary"],
        "blurb": "Job posting node.",
    },
    "faqpage": {
        "schema_type": "FAQPage",
        "fragment": "faqpage",
        "template": "faqpage.json",
        "prompt_fields": [],
        "blurb": "FAQ rich result; set mainEntity to the page's Q&A.",
    },
}


def get(name: str) -> dict:
    key = name.strip().lower()
    if key not in TYPES:
        raise KeyError(name)
    return TYPES[key]
