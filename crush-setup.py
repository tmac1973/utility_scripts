#!/usr/bin/env python3
"""
Generate a crush.json configuration file for charmbracelet/crush
by querying an OpenAI-compatible API endpoint for available models.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def fetch_model_info(base_url: str, model_id: str, api_key: str | None = None, extra_headers: dict | None = None) -> dict | None:
    """Fetch model-specific info from /api/models/{id}/info if available."""
    url = f"{base_url.rstrip('/')}/api/models/{model_id}/info"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def fetch_models(base_url: str, api_key: str | None = None, extra_headers: dict | None = None) -> list[dict]:
    """Fetch available models from the /models endpoint."""
    url = f"{base_url.rstrip('/')}/models"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"Error fetching models: HTTP {e.code} — {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error connecting to {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    models = data.get("data", [])
    if not models:
        print("No models returned from the API.", file=sys.stderr)
        sys.exit(1)

    return sorted(models, key=lambda m: m.get("id", ""))


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"{prompt} [{hint}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def guess_context_window(model_id: str) -> int:
    """Heuristic guess at context window from model name."""
    mid = model_id.lower()
    if "1m" in mid or "1000k" in mid:
        return 1_000_000
    if "200k" in mid:
        return 200_000
    if "128k" in mid or "gpt-4o" in mid or "gpt-4-turbo" in mid:
        return 128_000
    if "100k" in mid:
        return 100_000
    if "64k" in mid:
        return 64_000
    if "32k" in mid:
        return 32_000
    if "16k" in mid:
        return 16_384
    if any(x in mid for x in ("gpt-4", "gpt4")):
        return 128_000
    if any(x in mid for x in ("gpt-3.5", "gpt-35")):
        return 16_384
    if any(x in mid for x in ("claude", "anthropic")):
        return 200_000
    if any(x in mid for x in ("llama-3", "llama3")):
        return 128_000
    if any(x in mid for x in ("mistral", "mixtral")):
        return 32_000
    if any(x in mid for x in ("gemma", "phi")):
        return 8_192
    if any(x in mid for x in ("qwen", "deepseek")):
        return 128_000
    # Conservative default
    return 8_192


def get_context_window_from_api(base_url: str, model_id: str, api_key: str | None = None, extra_headers: dict | None = None) -> int | None:
    """Try to fetch context window from /api/models/{id}/info endpoint."""
    info = fetch_model_info(base_url, model_id, api_key, extra_headers)
    if info:
        # Try common field names for context window
        for field in ("context_length", "context_length", "max_context_length", "max_context_length", "context_size", "max_input_tokens", "context_window"):
            if field in info:
                val = info[field]
                if isinstance(val, (int, float)):
                    return int(val)
        # Also check nested structure
        if "data" in info and isinstance(info["data"], dict):
            for field in ("context_length", "max_context_length", "context_size", "max_input_tokens", "context_window"):
                if field in info["data"]:
                    val = info["data"][field]
                    if isinstance(val, (int, float)):
                        return int(val)
    return None


def guess_can_reason(model_id: str) -> bool:
    mid = model_id.lower()
    return any(x in mid for x in ("o1", "o3", "o4", "reason", "think", "deepseek-r1", "qwq"))


def guess_supports_attachments(model_id: str) -> bool:
    mid = model_id.lower()
    if any(x in mid for x in ("vision", "gpt-4o", "gpt-4-turbo", "claude-3", "claude-4",
                                "gemini", "llava", "pixtral")):
        return True
    return False


def prettify_model_name(model_id: str) -> str:
    """Turn a model ID into a human-friendly display name."""
    name = model_id.rsplit("/", 1)[-1]  # strip org prefix like "meta-llama/"
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"(\d{4})(\d{2})(\d{2})", r"\1-\2-\3", name)  # date stamps
    return name.title()


def build_model_entry(model: dict, base_url: str, api_key: str | None = None, extra_headers: dict | None = None) -> dict:
    mid = model["id"]
    # Try to get context window from API first, fall back to guessing
    context_window = get_context_window_from_api(base_url, mid, api_key, extra_headers)
    if context_window is None:
        context_window = guess_context_window(mid)
    return {
        "id": mid,
        "name": prettify_model_name(mid),
        "cost_per_1m_in": 0,
        "cost_per_1m_out": 0,
        "context_window": context_window,
        "default_max_tokens": min(4096, context_window),
        "can_reason": guess_can_reason(mid),
        "supports_attachments": guess_supports_attachments(mid),
    }


def select_models(models: list[dict], all_models: bool = False) -> list[dict]:
    """Let the user interactively select which models to include."""
    print(f"\nFound {len(models)} model(s):\n")
    for i, m in enumerate(models, 1):
        owned = m.get("owned_by", "")
        suffix = f"  (owned by: {owned})" if owned else ""
        print(f"  {i:3d}. {m['id']}{suffix}")

    if all_models:
        return models

    print()
    if prompt_yes_no("Include all models?", default=True):
        return models

    print("\nEnter model numbers to include (comma-separated, ranges ok e.g. 1-5,8,12):")
    raw = input("> ").strip()
    if not raw:
        return models

    selected_indices: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            for i in range(int(lo), int(hi) + 1):
                selected_indices.add(i)
        else:
            selected_indices.add(int(part))

    return [models[i - 1] for i in sorted(selected_indices) if 1 <= i <= len(models)]


def load_existing_config(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not parse existing {path}: {e}")
    return {}


def merge_provider(existing_config: dict, provider_key: str, new_provider: dict) -> dict:
    """Merge new provider into existing config, preserving non-duplicate entries."""
    config = dict(existing_config)
    if "providers" not in config:
        config["providers"] = {}

    if provider_key not in config["providers"]:
        config["providers"][provider_key] = new_provider
        return config

    existing_provider = config["providers"][provider_key]

    # Update provider-level fields
    for k in ("type", "name", "base_url", "api_key", "extra_headers"):
        if k in new_provider:
            existing_provider[k] = new_provider[k]

    # Merge models: don't overwrite existing model entries (matched by id)
    existing_model_ids = {m["id"] for m in existing_provider.get("models", [])}
    existing_models = list(existing_provider.get("models", []))
    new_count = 0
    for model in new_provider.get("models", []):
        if model["id"] not in existing_model_ids:
            existing_models.append(model)
            new_count += 1

    if new_count:
        print(f"  Added {new_count} new model(s), kept {len(existing_model_ids)} existing.")
    else:
        print(f"  All {len(new_provider.get('models', []))} model(s) already present — no duplicates added.")

    existing_provider["models"] = existing_models
    config["providers"][provider_key] = existing_provider
    return config


def write_config(config: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"Wrote config to {path}")


def derive_provider_slug(base_url: str) -> str:
    """Derive a provider slug from the base URL."""
    host = re.sub(r"https?://", "", base_url).split("/")[0]
    host = host.split(":")[0]  # strip port
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return slug or "local"


def resolve_api_key(api_key: str | None) -> tuple[str | None, str | None]:
    """Resolve an API key argument into (actual_key, config_key).

    Returns (None, None) if no key was provided.
    If the key starts with $, resolve it from the environment.
    """
    if not api_key:
        return None, None

    if api_key.startswith("$"):
        env_var = api_key.lstrip("$")
        actual = os.environ.get(env_var, "")
        if not actual:
            print(f"Error: environment variable {env_var} is not set.", file=sys.stderr)
            sys.exit(1)
        return actual, api_key  # store $VAR reference in config
    return api_key, api_key


def parse_header(value: str) -> tuple[str, str]:
    """Parse a 'Key: Value' header string."""
    if ":" not in value:
        raise argparse.ArgumentTypeError(f"Invalid header format (expected 'Key: Value'): {value}")
    k, v = value.split(":", 1)
    return k.strip(), v.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate crush.json for charmbracelet/crush by querying an OpenAI-compatible API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s http://localhost:11434/v1
  %(prog)s http://localhost:8080/v1 --name "Local LLM" --all
  %(prog)s https://api.openai.com/v1 --api-key '$OPENAI_API_KEY'
  %(prog)s http://localhost:11434/v1 --local
  %(prog)s http://localhost:11434/v1 -H "X-Custom: value" -H "X-Other: value2"
""",
    )

    parser.add_argument(
        "base_url",
        help="API base URL (e.g. http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--api-key", "-k",
        help="API key or $ENV_VAR reference (omit for local servers with no auth)",
    )
    parser.add_argument(
        "--provider", "-p",
        help="Provider slug used as the JSON key (default: derived from URL)",
    )
    parser.add_argument(
        "--name", "-n",
        help="Provider display name (default: derived from provider slug)",
    )
    parser.add_argument(
        "--type", "-t",
        default="openai-compat",
        help="Provider type (default: openai-compat)",
    )
    parser.add_argument(
        "--header", "-H",
        action="append",
        default=[],
        metavar="'Key: Value'",
        help="Extra header to send with API requests (repeatable)",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Include all models without prompting for selection",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Write to ./crush.json in the current directory",
    )
    parser.add_argument(
        "--global",
        action="store_true",
        dest="global_config",
        help="Write to ~/.config/crush/crush.json (default)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Normalize base URL
    base_url = re.sub(r"/models/?$", "", args.base_url.rstrip("/"))

    # Resolve API key
    actual_key, config_key = resolve_api_key(args.api_key)

    # Provider metadata
    provider_key = args.provider or derive_provider_slug(base_url)
    provider_name = args.name or provider_key.replace("-", " ").title()
    provider_type = args.type

    # Parse extra headers
    extra_headers: dict[str, str] = {}
    for h in args.header:
        k, v = parse_header(h)
        extra_headers[k] = v

    # Fetch and select models
    print(f"Fetching models from {base_url}...")
    raw_models = fetch_models(base_url, actual_key, extra_headers or None)
    selected = select_models(raw_models, all_models=args.all)

    if not selected:
        print("No models selected.", file=sys.stderr)
        sys.exit(1)

    model_entries = [build_model_entry(m, base_url, actual_key, extra_headers or None) for m in selected]

    # Show preview
    print(f"\nWill configure {len(model_entries)} model(s) for provider '{provider_key}':")
    for m in model_entries:
        flags = ""
        if m["can_reason"]:
            flags += " [reason]"
        if m["supports_attachments"]:
            flags += " [attachments]"
        print(f"  • {m['id']}  (ctx: {m['context_window']:,}){flags}")

    # Build provider block
    new_provider: dict = {
        "type": provider_type,
        "name": provider_name,
        "base_url": base_url,
    }
    if config_key:
        new_provider["api_key"] = config_key
    if extra_headers:
        new_provider["extra_headers"] = extra_headers
    new_provider["models"] = model_entries

    # Determine output paths
    paths: list[Path] = []
    if args.local and not args.global_config:
        paths.append(Path.cwd() / "crush.json")
    elif args.global_config and not args.local:
        paths.append(Path.home() / ".config" / "crush" / "crush.json")
    elif args.local and args.global_config:
        paths.append(Path.cwd() / "crush.json")
        paths.append(Path.home() / ".config" / "crush" / "crush.json")
    else:
        # Neither specified — ask interactively
        print("\nWhere should the config be saved?")
        print("  1. Local ./crush.json (current directory)")
        print("  2. ~/.config/crush/crush.json (user config)")
        print("  3. Both")
        choice = input("Choice [2]: ").strip() or "2"
        if choice in ("1", "3"):
            paths.append(Path.cwd() / "crush.json")
        if choice in ("2", "3"):
            paths.append(Path.home() / ".config" / "crush" / "crush.json")
        if not paths:
            paths.append(Path.home() / ".config" / "crush" / "crush.json")

    # Write config
    schema_url = "https://charm.land/crush.json"

    print()
    for path in paths:
        existing = load_existing_config(path)
        if not existing:
            existing = {"$schema": schema_url}
        elif "$schema" not in existing:
            existing["$schema"] = schema_url

        merged = merge_provider(existing, provider_key, new_provider)
        write_config(merged, path)

    print("\nDone!")


if __name__ == "__main__":
    main()
