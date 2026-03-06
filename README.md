# SecretsManager

A secure, lightweight Python desktop application and library for managing secrets. It uses strong encryption (AES-GCM with PBKDF2HMAC key derivation) to securely store your sensitive data, whether in a local file or a remote database.

## Features

- **Secure by Default:** Uses the `cryptography` library with AES-GCM for authenticated encryption and PBKDF2HMAC for key derivation.
- **Graphical User Interface (GUI):** An easy-to-use Tkinter interface for managing your secrets without needing to use the command line.
- **Flexible Authentication:** Unlock your secrets using a master password string or by loading a key file.
- **Hidden Values:** Secret values are always masked (e.g., `********`) in the GUI to prevent shoulder-surfing, with a convenient "Copy to Clipboard" button.
- **Multiple Storage Backends:** 
  - Local file storage (default `secrets.db`).
  - Remote SQL database support (PostgreSQL, MSSQL, etc.) via SQLAlchemy.

## Requirements

- Python 3.x
- `cryptography`
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
   pip install cryptography sqlalchemy
   ```

## Usage

### Using the GUI

To launch the graphical interface, run:

```bash
python secrets_gui.py
```

1. **Unlock:** Enter your master password string or select a file containing your key.
2. **Add Secret:** Click "Add Secret", provide a name, and enter the hidden value.
3. **View/Copy:** Click on a secret in the list to reveal a masked entry, and click "Copy to Clipboard" to use it.
4. **Delete All:** Clears the entire database (use with caution!).

### Using the Library Programmatically

You can also use the `SecretsSaver` class directly in your own Python scripts:

```python
from secrets_saver import SecretsSaver

# Initialize with a string key (local file storage)
saver = SecretsSaver(filename="my_secrets.db", key="my_super_secret_master_password")

# Store a secret
saver.set_secret("API_KEY", "abc123xyz")

# Retrieve a secret
my_key = saver.get_secret("API_KEY")

# List all saved secret names
print(saver.list_secrets())
```

To use a remote database, pass a SQLAlchemy-compatible Database URL:
```python
saver = SecretsSaver(db_url="postgresql+psycopg2://user:password@localhost:5432/mydb", key="my_password")
```

## Security Note

Keep your master password or key file safe! If you lose it, you will not be able to decrypt and recover your stored secrets.
