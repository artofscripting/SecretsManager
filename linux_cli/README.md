# Harbor CLI (Linux)

This folder contains a command-line interface for Harbor vault files (`.ep`) and a build path for generating a native Linux binary.

## Why this is separate

The GUI remains unchanged. This CLI is isolated in `linux_cli/` and reuses `secrets_saver.py` from the repository root to keep vault compatibility.

## Commands

```bash
./harbor-cli --help
./harbor-cli --vault main.ep init
./harbor-cli --vault main.ep set API_KEY --group Dev --url https://example.local
./harbor-cli --vault main.ep get API_KEY --group Dev
./harbor-cli --vault main.ep list
./harbor-cli --vault main.ep list --plain
./harbor-cli --vault main.ep groups
./harbor-cli --vault main.ep delete API_KEY --group Dev
./harbor-cli --vault main.ep change-password
```

`list` is interactive in a TTY:

- `Up/Down` to select a group first
- `Enter` or `Right` to open that group's secrets
- `Up/Down` to select a secret in the group
- `Enter` to reveal selected secret value
- Revealed view also shows the exact `get` command for that secret
- `Left` to go back to group list
- `q` to quit

Use `--plain` for non-interactive table output.

## Build Native Linux Binary

Build on Linux (or inside a Linux container/VM). PyInstaller does not produce Linux executables from Windows.

1. Create and activate a Linux virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Build binary:

```bash
python build_binary.py
```

The executable will be created at:

`linux_cli/dist/harbor-cli`

## Build Linux Binary From Windows/macOS (Docker)

If you are not currently on Linux, you can still produce a Linux binary via Docker:

```bash
docker build -t harbor-cli-linux-builder -f linux_cli/Dockerfile .
docker create --name harbor-cli-export harbor-cli-linux-builder
docker cp harbor-cli-export:/workspace/linux_cli/dist/harbor-cli ./harbor-cli
docker rm harbor-cli-export
```

This exports a Linux executable named `harbor-cli` into your current directory.

## Notes

- Master passwords are always prompted securely via `getpass`.
- The CLI does not accept master passwords as command-line arguments.
- Secret values for `set` are also prompted securely and never passed as command-line arguments.
- Commands other than `init` require an existing vault path and will error if the file does not exist.
