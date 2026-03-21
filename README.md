# utility_scripts

A collection of utility scripts for system setup and configuration.

## Scripts

### `setup-debian13-server.sh`

A bash script for setting up a new Debian 13 server with common tools and optional Docker.

**Usage:**
```bash
# Must be run as root (not with sudo)
./setup-debian13-server.sh [OPTIONS]
```

**Options:**
- `-d, --docker` - Install and configure Docker using the official installation script
- `-n, --non-interactive` - Run without prompting (assume yes to all prompts)
- `-y` - Alias for `--non-interactive`
- `-h, --help` - Show help message

**Examples:**
```bash
# Install base packages only (interactive)
./setup-debian13-server.sh

# Install everything non-interactively
./setup-debian13-server.sh -dny

# Interactive mode with Docker option
./setup-debian13-server.sh --docker
```

**What it installs:**
- `sudo` - Superuser privileges
- `cifs-utils` - CIFS/SMB filesystem support
- `curl` - Command-line HTTP client
- `btop` - Resource monitor
- `build-essential` - Compilation tools
- `linux-headers` - Kernel headers for current kernel

When Docker is installed, it:
- Downloads and runs the official Docker installation script
- Starts and enables the Docker service
- Adds a non-root user to the docker group

---

### `crush-setup.py`

A Python script for generating `crush.json` configuration for [charmbracelet/crush](https://github.com/charmbracelet/crush), an AI chat CLI tool.

**Usage:**
```bash
python3 ./crush-setup.py <base_url> [OPTIONS]
```

**Arguments:**
- `base_url` - API base URL (e.g. `http://localhost:11434/v1`)

**Options:**
- `-k, --api-key KEY` - API key or `$ENV_VAR` reference
- `-p, --provider SLUG` - Provider slug for JSON key (default: derived from URL)
- `-n, --name NAME` - Provider display name
- `-t, --type TYPE` - Provider type (default: `openai-compat`)
- `-H, --header 'Key: Value'` - Extra header (repeatable)
- `-a, --all` - Include all models without prompting
- `--local` - Write to `./crush.json` in current directory
- `--global` - Write to `~/.config/crush/crush.json` (default)

**Examples:**
```bash
# Local Ollama instance
python3 ./crush-setup.py http://localhost:11434/v1

# With API key
python3 ./crush-setup.py https://api.openai.com/v1 --api-key '$OPENAI_API_KEY'

# All models, non-interactive
python3 ./crush-setup.py http://localhost:8080/v1 --name "Local LLM" --all

# Custom headers
python3 ./crush-setup.py http://localhost:11434/v1 -H "X-Custom: value"
```

**Requirements:**
- Python 3.8+
- Access to an OpenAI-compatible API endpoint
