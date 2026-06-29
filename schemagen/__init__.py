"""schemagen — a JSON-LD schema generator driven by the Schema Markup SOP.

Builds SOP-compliant schema.org JSON-LD from vetted templates: single types or a
connected @graph. Entity links (Wikipedia/Wikidata/Google KG sameAs) are supplied
manually, per the SOP workflow.
"""
from . import core, project, registry

__all__ = ["core", "project", "registry"]
__version__ = "0.1.0"
