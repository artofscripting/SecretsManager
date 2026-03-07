# SecretsManager

A secure, fully-featured Python desktop application and library for managing secrets. It uses strong encryption (AES-GCM with PBKDF2HMAC key derivation) to securely store your sensitive data, whether in a local file or a remote database.

## Features

- **Robust Security & Encryption:** Uses the `cryptography` library with AES-GCM for authenticated encryption and PBKDF2HMAC for key derivation. Secrets are kept tightly encrypted at rest using algorithms and key lengths that are FIPS 140-3 compliant.
- **Multi-Vault Management:** Seamlessly manage multiple database vaults (`.ep` files) simultaneously.
- **Hierarchical Grouping:** Create logical folders (Groups) to organize related secrets natively in the GUI.
- **URL Workflows:** Store URLs alongside your passwords. Double-click the URL inside the GUI to instantly open your default browser AND securely copy the associated password to your clipboard simultaneously.
- **Clipboard & Memory Protection:** 
  - **Auto-Wipe:** The application automatically clears passwords from your system clipboard after 30 seconds.
  - **Memory Flushing:** Unencrypted secret arrays are wiped from system memory the moment operations complete.
- **Auto-Lock Session Timer:** Vaults will automatically lock themselves after a designated timeout (default 60 minutes), complete with a live countdown display.
- **Live Search Filtering:** Instantly filter your nested vaults, highlighting matched entries cleanly.
- **System Tray Integration:** Minimize the application directly to your System Tray to run quietly in the background without cluttering your taskbar.
- **Import / Export Capabilities:**
  - Export entire vaults, specific groups, or individual secrets securely.
  - Bulk import secrets directly into specific groups using straightforward CSV mapping.
- **Advanced Context Menus & Hotkeys:** Includes full right-click integration to Add, Edit, Delete, or Force Password Resets on individual vaults. Supports hotkeys (`Ctrl+A` for Add, `Delete` to remove keys).

## Requirements

- Python 3.x
- `cryptography`
- `pystray` & `Pillow` (for System Tray icon support)
- `sqlalchemy` (optional, for remote database support)

## Installation

It is recommended to use a virtual environment.

1. Clone or download this repository.
2. Create and activate a virtual environment:

   **Windows:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

   **macOS / Linux:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install cryptography pystray pillow sqlalchemy
   ```

## Usage

### Using the GUI

To launch the graphical interface, run:

```bash
python secrets_gui.py
```

#### Command Line Options
```bash
python secrets_gui.py --help
options:
  -h, --help            show this help message and exit
  --timeout TIMEOUT     Custom lock timeout in minutes (default is 60.0)
  --example-csv         Outputs a sample import CSV (import_sample.csv) and quits
```

1. **Vault Interaction:** When launching, the app will scan the local directory for `.ep` files. If none exist, it will prompt you to create a secure `default.ep`.
2. **Unlock:** Double-click a greyed-out database to unlock it with your password (rows highlight green when successfully unlocked).
3. **Add Secret:** Press `Ctrl+A`, use the right-click context menu, or use the menu bar to add a Name, Group, Value, and URL.
4. **Copying:** Double-click a Secret to dynamically copy its value. Double-click a URL to open it while simultaneously copying its corresponding secret.

### Using the Library Programmatically

You can also use the `SecretsSaver` class directly in your own Python scripts:

```python
from secrets_saver import SecretsSaver

# Initialize with a string key (local file storage)
saver = SecretsSaver(filename="main.ep", key="my_super_secret_master_password")

# Store a secret under a specific group
saver.set_secret(name="API_KEY", value="abc123xyz", group="Development", url="https://api.domain.com")

# Retrieve a secret
my_key = saver.get_secret("API_KEY", group="Development")

# List all saved secret metadata
print(saver.list_secrets())
```

To use a remote database, pass a SQLAlchemy-compatible Database URL:
```python
saver = SecretsSaver(db_url="postgresql+psycopg2://user:password@localhost:5432/mydb", key="my_super_secret_master_password")
```

## Security Note

Keep your master passwords safe! If you lose a vault's password, you will **not** be able to decrypt and recover your stored secrets. There is no password recovery mechanism.
