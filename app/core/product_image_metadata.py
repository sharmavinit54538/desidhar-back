"""Presentation metadata for the independently generated Pure Desi Ghee gallery.

Descriptions refer only to visible styling, not provenance or production claims.
The product name is catalog data; the serving photograph is explicitly illustrative.
"""

PURE_DESI_GHEE_ALTS = (
    "Golden semi-solid desi ghee in an unlabelled glass jar on a cream background",
    "Golden desi ghee in a traditional brass bowl on rustic wood",
    "Macro close-up of the smooth semi-solid texture of golden desi ghee",
    "Melted golden desi ghee pouring from a spoon into a bowl",
    "Overhead view of golden desi ghee in a simply styled bowl",
    "Golden desi ghee with soft side lighting against a dark studio background",
    "Desi ghee in a traditional Indian kitchen with metal utensils",
    "Serving suggestion: golden desi ghee melting over hot roti",
    "Desi ghee in a glass jar with a wooden spoon and a small serving bowl",
    "Golden desi ghee in soft morning light in a rustic Indian home setting",
)

PURE_DESI_GHEE_IMAGES = tuple(
    {
        "url": f"/static/products/pure-desi-ghee/pure-desi-ghee-{index:02d}.webp",
        "sort_order": index - 1,
        "alt": alt,
    }
    for index, alt in enumerate(PURE_DESI_GHEE_ALTS, start=1)
)

_ALT_BY_URL = {image["url"]: image["alt"] for image in PURE_DESI_GHEE_IMAGES}


def product_image_alt(url: str) -> str | None:
    """Return known image descriptions without inferring claims about other uploads."""
    return _ALT_BY_URL.get(url)
