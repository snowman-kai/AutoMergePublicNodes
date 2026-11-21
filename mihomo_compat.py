#!/usr/bin/env python3
"""Normalize generated Mihomo configs before they are published."""

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parent
EXAMPLE_FILE = ROOT / "snippets" / "example.yml"
FETCH_FILE = ROOT / "fetch.py"
CONFIG_FILE = ROOT / "config.yml"


class GoDumper(yaml.SafeDumper):
    """Keep list indentation compatible with Go's YAML decoder."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def leading_comments(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#"):
            lines.append(line)
        elif not line.strip() and lines:
            lines.append(line)
        else:
            break
    return "".join(lines)


def generated_yaml_files():
    yield from sorted(ROOT.glob("list*.yml"))
    yield from sorted((ROOT / "snippets").rglob("*.yml"))


def patch_sources():
    changed = 0
    errors = []

    fetch_text = FETCH_FILE.read_text(encoding="utf-8")
    old_security = "            elif k == 'security' and v == 'tls':"
    new_security = "            elif k == 'security' and v in ('tls', 'reality'):"
    if old_security in fetch_text:
        fetch_text = fetch_text.replace(old_security, new_security, 1)
        FETCH_FILE.write_text(fetch_text, encoding="utf-8")
        changed += 1
    elif new_security not in fetch_text:
        errors.append("fetch.py: could not locate VLESS security parser")

    config_text = CONFIG_FILE.read_text(encoding="utf-8")
    normalized = "\n".join(
        line
        for line in config_text.splitlines()
        if line.strip() != "global-client-fingerprint: chrome"
    ) + "\n"
    if normalized != config_text:
        CONFIG_FILE.write_text(normalized, encoding="utf-8")
        changed += 1

    return changed, errors


def main() -> int:
    source_changes, errors = patch_sources()
    if "--source-only" in sys.argv[1:]:
        print(f"Mihomo compatibility: patched {source_changes} source files.")
        for error in errors:
            print(error, file=sys.stderr)
        return 1 if errors else 0

    removed_fingerprints = 0
    fixed_reality_nodes = 0
    rewritten_files = 0

    for path in generated_yaml_files():
        if path == EXAMPLE_FILE:
            original = path.read_text(encoding="utf-8")
            normalized = "\n".join(
                line
                for line in original.splitlines()
                if line.strip() != "global-client-fingerprint: chrome"
            ) + "\n"
            if normalized != original:
                path.write_text(normalized, encoding="utf-8")
                removed_fingerprints += 1
                rewritten_files += 1
            continue

        try:
            original = path.read_text(encoding="utf-8")
            config = yaml.safe_load(original)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue

        if not isinstance(config, dict):
            continue

        changed = False
        if "global-client-fingerprint" in config:
            del config["global-client-fingerprint"]
            removed_fingerprints += 1
            changed = True

        proxies = config.get("proxies")
        if isinstance(proxies, list):
            for proxy in proxies:
                if not isinstance(proxy, dict) or "reality-opts" not in proxy:
                    continue
                if proxy.get("tls") is not True:
                    proxy["tls"] = True
                    fixed_reality_nodes += 1
                    changed = True

        if changed:
            body = yaml.dump(
                config,
                Dumper=GoDumper,
                allow_unicode=True,
                sort_keys=False,
            ).replace("!!str ", "")
            path.write_text(leading_comments(original) + body, encoding="utf-8")
            rewritten_files += 1

    for path in generated_yaml_files():
        if not path.name.startswith("list"):
            continue
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if not isinstance(config, dict):
            continue
        if "global-client-fingerprint" in config:
            errors.append(f"{path.relative_to(ROOT)}: global-client-fingerprint remains")
        for proxy in config.get("proxies", []):
            if isinstance(proxy, dict) and "reality-opts" in proxy and proxy.get("tls") is not True:
                errors.append(f"{path.relative_to(ROOT)}: REALITY node is not TLS-enabled")

    print(
        f"Mihomo compatibility: patched {source_changes} source files, "
        f"removed {removed_fingerprints} fingerprint fields, "
        f"fixed {fixed_reality_nodes} REALITY nodes, rewrote {rewritten_files} files."
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
