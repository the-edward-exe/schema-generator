"""Neutralize the template skeletons in schemagen/templates/.

Removes the industry/identity/location specifics (roofing, Joe Bob's, Phoenix,
Yoast, etc.) from the EXAMPLE STRING VALUES while keeping every property and the
full set of values each template uses to claim its schema profile (the long
sameAs citation list, awards/knowsAbout keyword arrays, about/mentions entity
arrays, geo, credentials, etc.). Only string *values* are touched — never keys,
never structure — so nothing is dropped.

Run:  python tools/neutralize_templates.py
"""
import json
import os
import re
import glob

TPL = os.path.join("schemagen", "templates")

# Exact, case-sensitive, ordered longest-first (identities, proper nouns, @types,
# entity URLs, domains).
EXACT = [
    # business identities
    ("Joe Bob's Super Duper Roofer", "Example Business"),
    ("Joe Bob's Phoenix Roofing LLC", "Example Business LLC"),
    ("Joe Bob's Roofing Contractor", "Example Business"),
    ("Joe Bob's Roofing in Phoenix", "Example Business"),
    ("Joe Bob's Roofing", "Example Business"),
    ("Job Bob's Roofing in Phoenix", "Example Business"),
    ("Job Bob's Roofing", "Example Business"),
    ("Joes Phoenix Roofing Contractor", "Example Business"),
    ("Job Bob's", "Example Business"),
    ("Joe Bob's", "Example Business"),
    ("Joe Bob", "Jane Doe"),
    ("Braun's Roofing", "Example Business"),
    ("Lyons Roofing", "Example Business"),
    ("Lyons Team", "Example Team"),
    ("Lyons", "Example"),
    ("National Roofing Contractors Association", "National Example Trade Association"),
    ("National_Roofing_Contractors_Association", "Trade_association"),
    ("NRCA", "Example Trade Association"),
    ("nrca.net", "example.org"),
    ("Domestic_roof_construction", "Service_economics"),
    ("Braun’s", "Example Business"),
    ("Joe’s", "the owner’s"),
    ("Joe has", "the owner has"),
    ("roofmasters", "servicemasters"),
    ("rencoroofing", "examplebusiness"),
    ("Certigrade", "Premium"),
    ("Certi-sawn", "Certified"),
    ("tapersawn", "premium"),
    # people
    ("Patrick Coombe", "Jane Doe"),
    ("Joe William Smith", "John Smith"),
    ("Craig Mount", "Alex Roe"),
    ("Mark van Berkel", "Jane Doe"),
    ("Marieke van de Rakt", "Jane Doe"),
    ("marieke-van-de-rakt", "jane-doe"),
    ("mariekerakt", "janedoe"),
    ("mgarakt", "janedoe"),
    ("marieke.blog", "janedoe.example.com"),
    ("Marieke", "Jane"),
    ("Joost de Valk", "John Smith"),
    ("joost-de-valk", "john-smith"),
    # seo handles / domains
    ("elite-strategies", "example-business"),
    ("elitestrategies", "examplebusiness"),
    ("delraybeachseo", "examplebusiness"),
    ("lyonsroofing.com", "example.com"),
    ("jobbobs.wordpress.com", "blog.example.org"),
    ("jobbobs.blogger.com", "news.example.org"),
    ("jobbobs", "examplebiz"),
    ("joebobs.png", "logo.png"),
    ("joebob.jpg", "person.jpg"),
    ("joebobs", "examplelogo"),
    # de-platform: WordPress/Shopify-flavored example paths -> neutral
    ("/wp-content/uploads/2013/04/", "/assets/"),
    ("/app/uploads/2019/06/", "/assets/"),
    ("profiles.wordpress.org/", "www.example.org/u/"),
    (".wordpress.com", ".example.org"),
    ("/?s={search_term_string}", "/search?q={search_term_string}"),
    ("?s={search_term_string}", "search?q={search_term_string}"),
    # landmarks
    ("Empire State Building", "Example Landmark"),
    # @types and additionalTypes (industry-specific -> generic)
    ("RoofingContractor", "LocalBusiness"),
    ("HomeAndConstructionBusiness", "ProfessionalService"),
    # entity URLs (wikipedia/wikidata roofing -> generic)
    ("en.wikipedia.org/wiki/Domestic_roof_construction", "en.wikipedia.org/wiki/Service_(economics)"),
    ("en.wikipedia.org/wiki/Roof_shingle", "en.wikipedia.org/wiki/Product_(business)"),
    ("en.wikipedia.org/wiki/Asphalt_shingle", "en.wikipedia.org/wiki/Product_(business)"),
    ("en.wikipedia.org/wiki/Asphalt", "en.wikipedia.org/wiki/Material"),
    ("en.wikipedia.org/wiki/Metal_roof", "en.wikipedia.org/wiki/Product_(business)"),
    ("en.wikipedia.org/wiki/Flat_roof", "en.wikipedia.org/wiki/Product_(business)"),
    ("en.wikipedia.org/wiki/Roofer", "en.wikipedia.org/wiki/Tradesperson"),
    ("en.wikipedia.org/wiki/Roof", "en.wikipedia.org/wiki/Service_(economics)"),
    ("en.wikipedia.org/wiki/Slate", "en.wikipedia.org/wiki/Material"),
    ("en.wikipedia.org/wiki/Metal", "en.wikipedia.org/wiki/Material"),
    ("en.wikipedia.org/wiki/Foam", "en.wikipedia.org/wiki/Material"),
    ("en.wikipedia.org/wiki/Tile", "en.wikipedia.org/wiki/Product_(business)"),
    ("en.wikipedia.org/wiki/Phoenix,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Tucson,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Glendale,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Tempe,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Mesa,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Peoria,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Gilbert,_Arizona", "en.wikipedia.org/wiki/City"),
    ("en.wikipedia.org/wiki/Arizona", "en.wikipedia.org/wiki/Region"),
    ("en.wikipedia.org/wiki/Phoenix_metropolitan_area", "en.wikipedia.org/wiki/Metropolitan_area"),
    # yoast specifics
    ("yoast.com", "example.com"),
    ("Yoast BV", "Example Holdings"),
    ("Newfold Digital", "Example Holdings"),
    ("Yoast", "Example"),
    ("/yoast", "/examplebrand"),
    ("yoast", "example"),
    ("avoid-site-structure-mistakes", "example-article"),
    # product specifics
    ("24 X 5 8 Western Red Cedar Certigrade Premium Grade Tapersawn Shakes",
     "Premium Example Widget"),
    ("images.mechanicsurplus.com", "www.example.com"),
]

# Whole-word / phrase, case-insensitive, ordered longest-first (industry + place
# terms). Replacement keeps the field's sentiment but generic.
WORDS = [
    ("metal roofing", "premium service"),
    ("commercial roofing", "commercial service"),
    ("residential roofing", "residential service"),
    ("roofing contractors", "service providers"),
    ("roofing contractor", "service provider"),
    ("roofing companies", "service companies"),
    ("roofing company", "service company"),
    ("roofing services", "professional services"),
    ("roofing service", "professional service"),
    ("roofing materials", "quality materials"),
    ("roofing material", "quality material"),
    ("roofing maintenance", "maintenance"),
    ("roofing inspection", "inspection"),
    ("roofing financing", "financing"),
    ("roofing repairs", "repairs"),
    ("roofing repair", "repair"),
    ("roofing", "service"),
    ("roofers", "specialists"),
    ("roofer", "specialist"),
    ("roof contractors", "service providers"),
    ("roof repairs", "repairs"),
    ("roof repair", "repair"),
    ("roof replacement", "replacement"),
    ("roof company", "service company"),
    ("re-roofing", "renovation"),
    ("cedar shakes", "premium products"),
    ("tapersawn shakes", "premium products"),
    ("shingles", "products"),
    ("shingle", "product"),
    ("shakes", "products"),
    ("shake", "product"),
    ("skylights", "fixtures"),
    ("skylight", "fixture"),
    ("roofs", "projects"),
    ("roof", "project"),
    ("cedar", "composite"),
    # places (longest first)
    ("Phoenix, Arizona", "Anytown, ST"),
    ("Phoenix, AZ", "Anytown, ST"),
    ("Tucson, Arizona", "Springfield, ST"),
    ("Scottsdale, AZ", "Springfield, ST"),
    ("Glendale, AZ", "Riverside, ST"),
    ("Mesa, AZ", "Fairview, ST"),
    ("Tempe, AZ", "Lakeside, ST"),
    ("Valley of the Sun", "the metro area"),
    ("Phoenix metropolitan area", "the metro area"),
    ("Phoenix metro area", "the metro area"),
    ("Phoenix metro", "the metro area"),
    ("greater Phoenix", "the greater metro area"),
    ("Phoenix", "Anytown"),
    ("Tucson", "Springfield"),
    ("Scottsdale", "Springfield"),
    ("Glendale", "Riverside"),
    ("Fountain Hills", "Hilltown"),
    ("Peoria", "Lakeside"),
    ("Gilbert", "Fairview"),
    ("Mesa", "Fairview"),
    ("Tempe", "Lakeside"),
    ("Arizona", "the region"),
    ("the Valley", "the region"),
    (r"\bAZ\b", "ST"),
]


def neutralize(text: str) -> str:
    for old, new in EXACT:
        text = text.replace(old, new)
    for pat, new in WORDS:
        rx = pat if pat.startswith(r"\b") else r"\b" + re.escape(pat) + r"\b"
        text = re.sub(rx, new, text, flags=re.IGNORECASE)
    return text


def walk(node):
    if isinstance(node, dict):
        return {k: walk(v) for k, v in node.items()}  # keys untouched
    if isinstance(node, list):
        return [walk(v) for v in node]
    if isinstance(node, str):
        return neutralize(node)
    return node


def main():
    for f in sorted(glob.glob(os.path.join(TPL, "*.json"))):
        obj = json.load(open(f, encoding="utf-8"))
        obj = walk(obj)
        json.dump(obj, open(f, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("  neutralized", os.path.basename(f))


if __name__ == "__main__":
    main()
