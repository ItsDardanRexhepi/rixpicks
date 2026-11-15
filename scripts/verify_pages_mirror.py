"""Check the served homepage, root JavaScript assets and missing-file response."""
import argparse
from hashlib import sha256
from pathlib import Path
import secrets
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def verify(root, origin):
    nonce = secrets.token_hex(12)

    def remote(path):
        url = f"{origin.rstrip('/')}/{quote(path)}?verify={nonce}"
        return urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=10)

    scripts = sorted(root.glob("*.js"))
    if not scripts:
        raise ValueError("No root JavaScript assets found in the release")
    for path in [root / "index.html", *scripts]:
        is_script = path.suffix == ".js"
        content_types = {"text/javascript", "application/javascript", "application/x-javascript"} if is_script else {"text/html"}
        expected = path.read_bytes()
        with remote(path.name if is_script else "") as response:
            content_type = response.headers.get_content_type()
            if response.status != 200 or content_type not in content_types:
                raise ValueError(f"{path.name} returned HTTP {response.status} with {content_type}")
            served = response.read(len(expected) + 1)
        if served != expected:
            raise ValueError(f"{path.name} differs from the release (expected SHA-256 {sha256(expected).hexdigest()})")

    try:
        with remote(f"rixpicks-missing-{nonce}.js") as response:
            raise ValueError(f"Missing JavaScript returned HTTP {response.status}; expected 404")
    except HTTPError as exc:
        with exc:
            if exc.code != 404:
                raise
    print(f"Verified homepage, {len(scripts)} JavaScript files, and missing-file 404")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("origin")
    args = cli.parse_args()
    try:
        verify(Path(__file__).resolve().parents[1], args.origin)
    except (OSError, URLError, ValueError) as error:
        sys.exit(str(error))
