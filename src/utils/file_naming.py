import re

def _city_code(city: str) -> str:
    """
    Convert a city name to a 3-letter code.
    Multi-word cities use the last word's first 3 letters.
    Examples: Montreal → MTL, San Salvador → SAL
    """
    city = city.strip()
    words = city.split()
    return words[-1][:3].upper()

def _route_to_codes(route: str) -> tuple[str, str]:
    """
    Parse 'Montreal-San Salvador' → ('MTL', 'SAL').
    Splits on the first hyphen to separate origin and destination.
    """

    """
    The 1 in route.split("-", 1) on line 18
    It's a max splits limit. It tells Python: split on - but stop after the first one. Without it, "Montreal-San-Salvador" would split into 3 parts and break the logic. With it, you always get exactly 2 parts: everything before the first - and everything after.

    {route!r} on line 20
    It's inside an f-string. The !r means "use the repr (representation) format" — it wraps the value in quotes and escapes special characters. So if route = "bad input", the error message shows got: 'bad input' instead of just got: bad input. It makes debugging easier because you can see exactly what string was passed, including whitespace or weird characters.
    """
    parts = route.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Route must be in 'Origin-Destination' format, got: {route!r}")
    origin_code = _city_code(parts[0])
    dest_code = _city_code(parts[1])
    return origin_code, dest_code

def _format_date(date: str) -> str:
    """Convert '2026-03-04' to '20260304'."""
    # that's regex. It means: replace every character that is NOT a digit with an empty string. So "2026-03-04" → "20260304". The ^ inside [] means "not these characters."
    return re.sub(r"[^0-9]", "", date)

def generate_campaign_key(route: str, date: str) -> str:
    """
    Generate the S3 key for the campaign PDF.
    Example: generate_campaign_key('Montreal-San Salvador', '2026-03-04')
             → 'campaigns/campaign-MTL-SAL-20260304.pdf'
    """
    origin, dest = _route_to_codes(route)
    date_str = _format_date(date)
    return f"campaigns/campaign-{origin}-{dest}-{date_str}.pdf"

def generate_metadata_key(route: str, date: str) -> str:
    """
    Generate the S3 key for the metadata PDF.
    Example: generate_metadata_key('Montreal-San Salvador', '2026-03-04')
             → 'metadata/metadata-campaign-MTL-SAL-20260304.pdf'
    """
    origin, dest = _route_to_codes(route)
    date_str = _format_date(date)
    return f"metadata/metadata-campaign-{origin}-{dest}-{date_str}.pdf"

# The existing_keys set is passed in by the caller (it would be loaded from S3 before calling this function).
def generate_unique_campaign_key(route: str, date: str, existing_keys: set) -> str:
    """
    Generate a unique campaign key, appending a counter if the base key already exists.
    Example: 'campaigns/campaign-MTL-SAL-20260304-2.pdf'
    """
    base = generate_campaign_key(route, date)
    if base not in existing_keys:
        return base
    # Strip .pdf, append counter
    base_no_ext = base[:-4]
    counter = 2
    while True:
        candidate = f"{base_no_ext}-{counter}.pdf"
        if candidate not in existing_keys:
            return candidate
        counter += 1

def generate_unique_metadata_key(route: str, date: str, existing_keys: set) -> str:
    """
    Generate a unique metadata key, appending a counter if the base key already exists.
    """
    base = generate_metadata_key(route, date)
    if base not in existing_keys:
        return base
    base_no_ext = base[:-4]
    counter = 2
    while True:
        candidate = f"{base_no_ext}-{counter}.pdf"
        if candidate not in existing_keys:
            return candidate
        counter += 1
