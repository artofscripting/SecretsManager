import os
import json
import base64
import getpass
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

try:
    from sqlalchemy import create_engine, text, Table, Column, Integer, String, MetaData, select
except ImportError:
    pass

class SecretsSaver:
    def __init__(self, filename="secrets.db", db_url: Optional[str] = None, key: Optional[str] = None):
        """
        Initialize the SecretsSaver.
        Provide db_url to use a remote database (e.g., PostgreSQL or MSSQL).
        Example: db_url="postgresql+psycopg2://user:password@localhost:5432/mydb"
                 db_url="mssql+pyodbc://user:password@localhost/mydb?driver=ODBC+Driver+17+for+SQL+Server"
        """
        self.filename = filename
        self.db_url = db_url
        self._key = key.encode('utf-8') if key else None
        self._data = None
        self._engine = None
        
        if self.db_url:
            self._engine = create_engine(self.db_url)
            self._metadata = MetaData()
            # We store the encrypted JSON payload and metadata in a single row just like the file.
            self._secrets_table = Table(
                'encrypted_secrets', self._metadata,
                Column('id', Integer, primary_key=True),
                Column('salt', String(255)),
                Column('nonce', String(255)),
                Column('ciphertext', String)
            )
            self._metadata.create_all(self._engine)
        
        if not self._exists():
            self._initialize_db()

    def _exists(self):
        if self.db_url:
            with self._engine.connect() as conn:
                stmt = select(self._secrets_table.c.id).where(self._secrets_table.c.id == 1)
                result = conn.execute(stmt).fetchone()
                return result is not None
        return os.path.exists(self.filename)

    def _get_key(self):
        if self._key is None:
            location = self.db_url if self.db_url else self.filename
            password = getpass.getpass(f"Enter key for {location}: ")
            self._key = password.encode('utf-8')
        return self._key

    def _derive_key(self, salt: bytes):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,
        )
        return kdf.derive(self._get_key())

    def _initialize_db(self):
        self._get_key() # Prompt for key on creation
        self._data = {}
        self._save()

    def _load_raw(self):
        if self.db_url:
            with self._engine.connect() as conn:
                stmt = select(
                    self._secrets_table.c.salt,
                    self._secrets_table.c.nonce,
                    self._secrets_table.c.ciphertext
                ).where(self._secrets_table.c.id == 1)
                row = conn.execute(stmt).fetchone()
                if not row:
                    raise FileNotFoundError("Secrets not found in database.")
                # the result varies by SQLAlchemy versions, indices are safer across versions
                return {'salt': row[0], 'nonce': row[1], 'ciphertext': row[2]}
        else:
            with open(self.filename, 'r') as f:
                return json.load(f)

    def _save_raw(self, content):
        if self.db_url:
            with self._engine.begin() as conn:
                stmt = select(self._secrets_table.c.id).where(self._secrets_table.c.id == 1)
                res = conn.execute(stmt).fetchone()
                if res:
                    u = self._secrets_table.update().where(self._secrets_table.c.id == 1).values(
                        salt=content['salt'],
                        nonce=content['nonce'],
                        ciphertext=content['ciphertext']
                    )
                    conn.execute(u)
                else:
                    i = self._secrets_table.insert().values(
                        id=1,
                        salt=content['salt'],
                        nonce=content['nonce'],
                        ciphertext=content['ciphertext']
                    )
                    conn.execute(i)
        else:
            with open(self.filename, 'w') as f:
                json.dump(content, f)

    def _load(self):
        content = self._load_raw()
            
        salt = base64.b64decode(content['salt'])
        nonce = base64.b64decode(content['nonce'])
        ciphertext = base64.b64decode(content['ciphertext'])

        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            self._data = json.loads(plaintext.decode('utf-8'))
        except InvalidTag:
            self._key = None
            raise ValueError("Invalid key or corrupted data.")

    def _ensure_loaded(self):
        if self._data is None:
            if self._exists():
                self._load()
            else:
                self._data = {}

    def _save(self):
        self._ensure_loaded()
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        
        plaintext = json.dumps(self._data).encode('utf-8')
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        content = {
            'salt': base64.b64encode(salt).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
        }
        
        self._save_raw(content)

    def set_secret(self, key: str, value: str):
        """Sets a secret in the database."""
        self._ensure_loaded()
        self._data[key] = value
        self._save()

    def get_secret(self, key: str) -> str:
        """Gets a secret from the database."""
        self._ensure_loaded()
        return self._data.get(key)
        
    def list_secrets(self) -> list:
        """Returns a list of keys for stored secrets."""
        self._ensure_loaded()
        return list(self._data.keys())

    def clear_database(self):
        self._data = {}
        self._save()

