import argparse
import sys
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog, ttk
import glob
import os
import time
import csv
import webbrowser
from secrets_saver import SecretsSaver

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

class SecretsGUI(tk.Tk):
    def __init__(self, timeout_minutes=60.0):
        super().__init__()
        self.timeout_minutes = timeout_minutes
        self.title("Secrets Manager")
        self.geometry("600x450")
        
        try:
            self.iconbitmap(resource_path("favicon.ico"))
        except tk.TclError:
            pass # Fallback to default if icon is completely missing/invalid
        
        self.savers = {} # Maps db filename to unlocked SecretsSaver instance
        self.lock_timers = {} # Maps db filename to lock timer IDs
        self.lock_deadlines = {} # Maps db filename to expiration timestamp
        self.clipboard_timer = None
        self.tray_icon = None
        
        # Override window close for system tray
        if HAS_PYSTRAY:
            self.protocol('WM_DELETE_WINDOW', self.hide_window)
        
        # UI Elements for Main App
        self.main_frame = tk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search Bar
        search_frame = tk.Frame(self.main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.on_search())
        tk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        tree_frame = tk.Frame(self.main_frame)
        tree_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.secrets_tree = ttk.Treeview(tree_frame, columns=("Name",), show="tree", yscrollcommand=tree_scroll.set)
        self.secrets_tree.heading("#0", text="Folder")
        self.secrets_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.secrets_tree.yview)
        
        self.secrets_tree.bind("<Double-1>", self.on_select_secret)
        self.secrets_tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.secrets_tree.bind("<Button-3>", self.on_right_click)
        
        # Configure styles
        self.secrets_tree.tag_configure("locked_db", foreground="gray")
        self.secrets_tree.tag_configure("unlocked_db", background="light green", foreground="black")
        self.secrets_tree.tag_configure("locked_dummy", background="#f7e0e0", foreground="grey")
        self.secrets_tree.tag_configure("search_result", background="light blue", foreground="black")

        # Key bindings
        self.secrets_tree.bind("<Delete>", lambda e: self.on_delete_key())
        self.bind("<Control-a>", lambda e: self.add_secret())
        self.bind("<Control-A>", lambda e: self.add_secret())

        # Menu Bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Import CSV", command=self.import_csv)
        file_menu.add_command(label="Export Selection / Group", command=self.export_group)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Button(btn_frame, text="Quit", command=self.do_quit).pack(side=tk.RIGHT, padx=5)
        tk.Button(btn_frame, text="Lock", command=self.forget_all).pack(side=tk.RIGHT, padx=5)

        self.status_var = tk.StringVar()
        self.status_var.set("All databases locked.")
        self.status_bar = tk.Label(btn_frame, textvariable=self.status_var, anchor=tk.W, fg="gray")
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.refresh_list()
        self.update_countdown()

    def update_countdown(self):
        if not self.lock_deadlines:
            self.status_var.set("All databases locked.")
        else:
            now = time.time()
            # find earliest deadline
            earliest_db = min(self.lock_deadlines.keys(), key=lambda k: self.lock_deadlines[k])
            remaining = int(self.lock_deadlines[earliest_db] - now)
            
            if remaining > 0:
                mins, secs = divmod(remaining, 60)
                self.status_var.set(f"Next lock timeout: '{earliest_db}' in {mins:02d}:{secs:02d}")
            else:
                self.status_var.set("Locking...")
                
        self.after(1000, self.update_countdown)

    def on_search(self):
        self.refresh_list(preserve_state=True)

    def refresh_list(self, preserve_state=True):
        search_query = self.search_var.get().lower()
        # Keep track of what was open visually
        open_nodes = []
        if preserve_state and not search_query:
            open_nodes = [self.secrets_tree.item(child, "text") for child in self.secrets_tree.get_children() 
                        if self.secrets_tree.item(child, "open")]
                    
        self.secrets_tree.delete(*self.secrets_tree.get_children())
        db_files = glob.glob("*.ep")
        
        # If absolutely no database exists, prompt to securely create a default one
        if not db_files:
            self.update()
            pwd = simpledialog.askstring("Welcome", "No databases found.\nCreate a password for your new 'default.ep':", show="*", parent=self)
            if pwd:
                try:
                    SecretsSaver(filename="default.ep", key=pwd)
                    db_files = ["default.ep"]
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create default.ep: {e}", parent=self)
        
        for f in db_files:
            # We treat the db file itself as a group container
            # If searching, auto-expand
            is_open = True if search_query else (f in open_nodes)
            
            # Determine visual state based on whether it is unlocked
            db_tag = "unlocked_db" if f in self.savers else "locked_db"
            db_node = self.secrets_tree.insert("", "end", text=f, tags=("db", f, db_tag), open=is_open)
            
            if f in self.savers:
                self.populate_db_node(db_node, f, search_query)
            else:
                dummy_text = "(Database Locked)" if search_query else ""
                dummy_tags = ("dummy", "locked_dummy") if search_query else ("dummy",)
                self.secrets_tree.insert(db_node, "end", text=dummy_text, tags=dummy_tags) # node to show expand arrow

    def populate_db_node(self, db_node_id, db_name, search_query=""):
        saver = self.savers[db_name]
        secrets = saver.list_secrets()
        folders = {}
        for s in secrets:
            group = s["group"]
            name = s["name"]
            url = s.get("url", "")
            
            # Apply filter
            if search_query and search_query not in name.lower() and search_query not in group.lower() and search_query not in url.lower():
                continue
                
            if group not in folders:
                folders[group] = self.secrets_tree.insert(db_node_id, "end", text=group, tags=("group", db_name), open=True)
                
            secret_tags = ("secret", db_name, "search_result") if search_query else ("secret", db_name)
            secret_node = self.secrets_tree.insert(folders[group], "end", text=name, tags=secret_tags, open=True if search_query else False)
            
            if url:
                self.secrets_tree.insert(secret_node, "end", text=url, tags=("url", db_name, url))


    def on_tree_open(self, event):
        item_id = self.secrets_tree.focus()
        tags = self.secrets_tree.item(item_id, "tags")
        if not tags or "db" not in tags:
            return
            
        db_name = tags[1]
        
        if db_name not in self.savers:
            self.update()
            pwd = simpledialog.askstring("Unlock", f"Enter password for {db_name}:", show="*", parent=self)
            if not pwd:
                self.secrets_tree.item(item_id, open=False)
                return
            try:
                saver = SecretsSaver(filename=db_name, key=pwd)
                saver.list_secrets() # force a load to verify key
                
                # Check if password change is forced
                if saver.get_config("change_password"):
                    messagebox.showinfo("Security Requirement", f"The database '{db_name}' requires a password reset before it can be accessed.", parent=self)
                    
                    while True:
                        self.update()
                        new_pwd = simpledialog.askstring("Forced Password Reset", f"Enter NEW password for {db_name}:", show="*", parent=self)
                        if not new_pwd:
                            self.secrets_tree.item(item_id, open=False)
                            return # Cancelled unlock entirely
                            
                        confirm_pwd = simpledialog.askstring("Forced Password Reset", f"Confirm NEW password for {db_name}:", show="*", parent=self)
                        if new_pwd != confirm_pwd:
                            messagebox.showwarning("Warning", "Passwords do not match! Try again.", parent=self)
                            continue
                            
                        try:
                            saver.change_key(new_pwd)
                            messagebox.showinfo("Success", f"Password for {db_name} changed successfully.", parent=self)
                            break
                        except ValueError as ve: # Catches the same-password exception explicitly
                            messagebox.showerror("Error", str(ve), parent=self)
                            continue
                        except Exception as e:
                            messagebox.showerror("Error", f"Failed to change password: {e}", parent=self)
                            self.secrets_tree.item(item_id, open=False)
                            return
                
                self.savers[db_name] = saver
                self.schedule_lock(db_name)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to unlock {db_name}: {e}")
                self.secrets_tree.item(item_id, open=False)
                return
                
        # If unlocked successfully, clear dummy and populate
        children = self.secrets_tree.get_children(item_id)
        if len(children) == 1 and "dummy" in self.secrets_tree.item(children[0], "tags"):
            self.secrets_tree.delete(children[0])
            self.populate_db_node(item_id, db_name, self.search_var.get().lower())
            
        # Update styling tags
        self.secrets_tree.item(item_id, tags=("db", db_name, "unlocked_db"))

    def schedule_lock(self, db_name):
        if db_name in self.lock_timers:
            self.after_cancel(self.lock_timers[db_name])
        
        timeout_ms = int(self.timeout_minutes * 60 * 1000)
        timeout_sec = self.timeout_minutes * 60
        
        self.lock_timers[db_name] = self.after(timeout_ms, lambda: self.lock_db(db_name))
        self.lock_deadlines[db_name] = time.time() + timeout_sec

    def lock_db(self, db_name):
        if db_name in self.savers:
            del self.savers[db_name]
            
        if db_name in self.lock_timers:
            del self.lock_timers[db_name]
            
        if db_name in self.lock_deadlines:
            del self.lock_deadlines[db_name]
            
        for item in self.secrets_tree.get_children():
            tags = self.secrets_tree.item(item, "tags")
            if tags and "db" in tags and tags[1] == db_name:
                self.secrets_tree.item(item, open=False)
                self.secrets_tree.delete(*self.secrets_tree.get_children(item))
                self.secrets_tree.insert(item, "end", text="", tags=("dummy",))
                self.secrets_tree.item(item, tags=("db", db_name, "locked_db"))
                self.show_toast(f"Session for '{db_name}' expired and locked.")
                break

    def on_delete_key(self):
        selection = self.secrets_tree.selection()
        if not selection: return
        item_id = selection[0]
        tags = self.secrets_tree.item(item_id, "tags")
        if tags and "secret" in tags:
            self.delete_secret()

    def add_secret(self, preset_db=None, preset_group=None):
        if preset_db:
            db_name = preset_db
        else:
            selection = self.secrets_tree.selection()
            if not selection:
                messagebox.showinfo("Select", "Please select a database or group to add a secret to.")
                return
                
            item_id = selection[0]
            tags = self.secrets_tree.item(item_id, "tags")
            if not tags: return
            db_name = tags[1]
            
            if "group" in tags and not preset_group:
                preset_group = self.secrets_tree.item(item_id, "text")
            
        if db_name not in self.savers:
            messagebox.showinfo("Unlock", f"Please expand and unlock '{db_name}' first.")
            return
            
        saver = self.savers[db_name]
        
        groups = list(set(s["group"] for s in saver.list_secrets()))
        if "Default" not in groups:
            groups.insert(0, "Default")
            
        top = tk.Toplevel(self)
        top.title(f"Add Secret to {db_name}")
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 150
        y = self.winfo_y() + (self.winfo_height() // 2) - 135
        top.geometry(f"300x270+{x}+{y}")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="Secret Name:").pack(pady=(10, 0))
        name_entry = tk.Entry(top, width=30)
        name_entry.pack()

        tk.Label(top, text="Group:").pack(pady=(10, 0))
        group_combo = ttk.Combobox(top, values=groups, width=27)
        if preset_group:
            group_combo.set(preset_group)
        else:
            group_combo.set("Default")
        group_combo.pack()

        tk.Label(top, text="Value:").pack(pady=(10, 0))
        value_entry = tk.Entry(top, width=30, show="*")
        value_entry.pack()

        tk.Label(top, text="URL (Optional):").pack(pady=(10, 0))
        url_entry = tk.Entry(top, width=30)
        url_entry.pack()

        def save():
            name = name_entry.get().strip()
            group = group_combo.get().strip() or "Default"
            url = url_entry.get().strip()
            value = value_entry.get()
            if not name:
                messagebox.showwarning("Warning", "Secret Name is required", parent=top)
                return
                
            # Prevent duplicates within the same group
            if any(s["name"] == name and s["group"] == group for s in saver.list_secrets()):
                messagebox.showwarning("Warning", f"A secret named '{name}' already exists in group '{group}' in this file. Please choose a different name.", parent=top)
                return
                
            if not value:
                messagebox.showwarning("Warning", "Value is required", parent=top)
                return
            try:
                saver.set_secret(name, value, group, url)
                self.refresh_list()
                top.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save secret: {e}", parent=top)

        tk.Button(top, text="Save", command=save).pack(pady=15)

    def on_select_secret(self, event):
        item_id = self.secrets_tree.identify_row(event.y)
        if item_id:
            tags = self.secrets_tree.item(item_id, "tags")
            if tags:
                if "url" in tags:
                    url = tags[2]
                    db_name = tags[1]
                    try:
                        webbrowser.open(url)
                        
                        # Fetch and copy the associated secret
                        secret_id = self.secrets_tree.parent(item_id)
                        name = self.secrets_tree.item(secret_id, "text")
                        
                        group_id = self.secrets_tree.parent(secret_id)
                        group = self.secrets_tree.item(group_id, "text")
                        
                        saver = self.savers[db_name]
                        value = saver.get_secret(name, group)
                        
                        self.clipboard_clear()
                        self.clipboard_append(value)
                        self.update()
                        
                        # wipe decrypted payload from memory
                        saver._data = None
                        self.schedule_clipboard_clear()
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to open URL or copy secret: {e}")
                    return
                elif "secret" in tags:
                    db_name = tags[1]
                    name = self.secrets_tree.item(item_id, "text")
                    parent_id = self.secrets_tree.parent(item_id)
                    group = self.secrets_tree.item(parent_id, "text")
                    saver = self.savers[db_name]
                    try:
                        value = saver.get_secret(name, group)
                        # Copy directly to clipboard and notify silently
                        self.clipboard_clear()
                        self.clipboard_append(value)
                        self.update()
                        self.show_toast(f"Copied '{name}' to clipboard.")
                        # wipe decrypted payload from memory
                        saver._data = None
                        self.schedule_clipboard_clear()
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to get secret: {e}")

    def schedule_clipboard_clear(self):
        if self.clipboard_timer:
            self.after_cancel(self.clipboard_timer)
        # Clear clipboard after 30 seconds
        self.clipboard_timer = self.after(30000, self.do_clipboard_clear)

    def do_clipboard_clear(self):
        try:
            self.clipboard_clear()
            self.update()
            self.show_toast("Clipboard automatically wiped for security.")
        except tk.TclError:
            pass

    def show_toast(self, message):
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 100
        y = self.winfo_y() + (self.winfo_height() // 2) - 25
        toast.geometry(f"200x50+{x}+{y}")
        
        frame = tk.Frame(toast, highlightbackground="gray", highlightthickness=1)
        frame.pack(expand=True, fill=tk.BOTH)
        tk.Label(frame, text=message, bg="#333333", fg="white", font=("Arial", 10)).pack(expand=True, fill=tk.BOTH)
        
        self.after(1500, toast.destroy)

    def on_right_click(self, event):
        item_id = self.secrets_tree.identify_row(event.y)
        if item_id:
            self.secrets_tree.selection_set(item_id)
            tags = self.secrets_tree.item(item_id, "tags")
            if tags:
                if "db" in tags:
                    db_name = tags[1]
                    menu = tk.Menu(self, tearoff=0)
                    menu.add_command(label="Add Secret", command=lambda: self.add_secret(preset_db=db_name))
                    menu.add_command(label="Change Password", command=lambda: self.change_password(preset_db=db_name))
                    menu.add_command(label="Force Password Reset on Next Use", command=lambda: self.force_password_reset_next_use(db_name))
                    menu.post(event.x_root, event.y_root)
                elif "group" in tags:
                    db_name = tags[1]
                    group_name = self.secrets_tree.item(item_id, "text")
                    menu = tk.Menu(self, tearoff=0)
                    menu.add_command(label="Add Secret", command=lambda: self.add_secret(preset_db=db_name, preset_group=group_name))
                    menu.post(event.x_root, event.y_root)
                elif "secret" in tags or "url" in tags:
                    menu = tk.Menu(self, tearoff=0)
                    menu.add_command(label="Edit Secret", command=self.edit_secret)
                    menu.add_command(label="Delete Secret", command=self.delete_secret)
                    menu.post(event.x_root, event.y_root)

    def edit_secret(self):
        selection = self.secrets_tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        tags = self.secrets_tree.item(item_id, "tags")
        if not tags or ("secret" not in tags and "url" not in tags):
            return
            
        if "url" in tags:
            # If they right clicked the URL, treat it as if they right clicked the parent secret
            item_id = self.secrets_tree.parent(item_id)
            tags = self.secrets_tree.item(item_id, "tags")
            
        db_name = tags[1]
        saver = self.savers.get(db_name)
        if not saver:
            return
            
        name = self.secrets_tree.item(item_id, "text")
        parent_id = self.secrets_tree.parent(item_id)
        group = self.secrets_tree.item(parent_id, "text")
        
        try:
            value = saver.get_secret(name, group)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get secret: {e}")
            return
            
        # find URL if it exists
        url = ""
        children = self.secrets_tree.get_children(item_id)
        if children:
            child_tags = self.secrets_tree.item(children[0], "tags")
            if child_tags and "url" in child_tags:
                url = child_tags[2]
                
        groups = list(set(s["group"] for s in saver.list_secrets()))
        if "Default" not in groups:
            groups.insert(0, "Default")
            
        top = tk.Toplevel(self)
        top.title(f"Edit Secret in {db_name}")
        
        x = self.winfo_x() + (self.winfo_width() // 2) - 150
        y = self.winfo_y() + (self.winfo_height() // 2) - 135
        top.geometry(f"300x270+{x}+{y}")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="Secret Name:").pack(pady=(10, 0))
        name_entry = tk.Entry(top, width=30)
        name_entry.insert(0, name)
        name_entry.pack()

        tk.Label(top, text="Group:").pack(pady=(10, 0))
        group_combo = ttk.Combobox(top, values=groups, width=27)
        group_combo.set(group)
        group_combo.pack()

        tk.Label(top, text="Value:").pack(pady=(10, 0))
        value_entry = tk.Entry(top, width=30, show="*")
        value_entry.insert(0, value)
        value_entry.pack()

        tk.Label(top, text="URL (Optional):").pack(pady=(10, 0))
        url_entry = tk.Entry(top, width=30)
        url_entry.insert(0, url)
        url_entry.pack()

        def save():
            new_name = name_entry.get().strip()
            new_group = group_combo.get().strip() or "Default"
            new_url = url_entry.get().strip()
            new_value = value_entry.get()
            if not new_name:
                messagebox.showwarning("Warning", "Secret Name is required", parent=top)
                return
                
            if (new_name != name or new_group != group) and any(s["name"] == new_name and s["group"] == new_group for s in saver.list_secrets()):
                messagebox.showwarning("Warning", f"A secret named '{new_name}' already exists in group '{new_group}' in this file. Please choose a different name.", parent=top)
                return
                
            if not new_value:
                messagebox.showwarning("Warning", "Value is required", parent=top)
                return
            try:
                if new_name != name or new_group != group:
                    saver.delete_secret(name, group)
                saver.set_secret(new_name, new_value, new_group, new_url)
                self.refresh_list()
                top.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save secret: {e}", parent=top)

        tk.Button(top, text="Save", command=save).pack(pady=15)

    def force_password_reset_next_use(self, db_name):
        if db_name not in self.savers:
            self.update()
            pwd = simpledialog.askstring("Unlock", f"Enter password for {db_name} to modify settings:", show="*", parent=self)
            if not pwd:
                return
            try:
                saver = SecretsSaver(filename=db_name, key=pwd)
                saver.list_secrets()
                self.savers[db_name] = saver
                self.schedule_lock(db_name)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to unlock {db_name}: {e}", parent=self)
                return

        try:
            self.savers[db_name].set_config("change_password", True)
            messagebox.showinfo("Success", f"Password change will be forced on next use for '{db_name}'.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update settings for {db_name}: {e}", parent=self)

    def delete_secret(self):
        selection = self.secrets_tree.selection()
        if not selection:
            messagebox.showinfo("Select", "Please select a secret to delete.")
            return
            
        item_id = selection[0]
        tags = self.secrets_tree.item(item_id, "tags")
        if not tags or ("secret" not in tags and "url" not in tags):
            messagebox.showinfo("Select", "Please select a specific secret.")
            return

        if "url" in tags:
            # Shift focus up to parent secret
            item_id = self.secrets_tree.parent(item_id)
            tags = self.secrets_tree.item(item_id, "tags")

        db_name = tags[1]
        name = self.secrets_tree.item(item_id, "text")
        parent_id = self.secrets_tree.parent(item_id)
        group = self.secrets_tree.item(parent_id, "text")
        
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete the secret '{name}' from '{group}'?"):
            try:
                self.savers[db_name].delete_secret(name, group)
                self.refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete secret: {e}")

    def import_csv(self):
        filepath = filedialog.askopenfilename(
            title="Select CSV to Import",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath: return
        
        # Ask for target .ep or default to new
        target_db = simpledialog.askstring("Import", "Enter the name of the database to import into (e.g. 'main.ep'):\n(If it doesn't exist, it will be created)", initialvalue="imported.ep")
        if not target_db: return
        if not target_db.endswith(".ep"): target_db += ".ep"
        
        # Need password
        if target_db in self.savers:
            saver = self.savers[target_db]
        else:
            pwd = simpledialog.askstring("Import", f"Enter password for {target_db}:", show="*")
            if not pwd: return
            try:
                saver = SecretsSaver(filename=target_db, key=pwd)
                saver.list_secrets()
                self.savers[target_db] = saver
                self.schedule_lock(target_db)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open/create {target_db}: {e}")
                return

        try:
            count = 0
            with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                
                # Try to map columns: expecting [Name, Group, Value, URL] or similar
                # We'll just take simple columns if exact map fails
                for row in reader:
                    if not row: continue
                    group = row[0].strip() if len(row) > 0 and row[0].strip() else "Imported"
                    name = row[1].strip() if len(row) > 1 and row[1].strip() else f"Imported_{count}"
                    value = row[2].strip() if len(row) > 2 else ""
                    url = row[3].strip() if len(row) > 3 else ""
                    
                    if not name or not value: continue
                    
                    saver.set_secret(name, value, group, url)
                    count += 1
                    if count % 10 == 0:
                        self.show_toast(f"Importing: {count} secrets processed...")
                        self.update()
                    
            messagebox.showinfo("Success", f"Successfully imported {count} secrets into {target_db}.")
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse CSV: {e}")

    def export_group(self):
        selection = self.secrets_tree.selection()
        dbs_to_export = []
        groups_to_export = []
        secrets_to_export = []
        
        for item_id in selection:
            tags = self.secrets_tree.item(item_id, "tags")
            if tags:
                if "db" in tags:
                    db_name = tags[1]
                    dbs_to_export.append(db_name)
                elif "group" in tags:
                    db_name = tags[1]
                    group_name = self.secrets_tree.item(item_id, "text")
                    groups_to_export.append((db_name, group_name))
                elif "secret" in tags:
                    db_name = tags[1]
                    secret_name = self.secrets_tree.item(item_id, "text")
                    parent_id = self.secrets_tree.parent(item_id)
                    group_name = self.secrets_tree.item(parent_id, "text")
                    secrets_to_export.append((db_name, group_name, secret_name))
        
        if not dbs_to_export and not groups_to_export and not secrets_to_export:
            messagebox.showinfo("Select", "Please select at least one database, group, or secret to export (use Ctrl+Click to select multiple).")
            return

        # Ensure all selected DBs to export wholly are unlocked
        for db_name in dbs_to_export:
            if db_name not in self.savers:
                self.update()
                pwd = simpledialog.askstring("Unlock", f"Please unlock {db_name} for exporting:", show="*", parent=self)
                if not pwd:
                    messagebox.showwarning("Warning", f"Export cancelled because {db_name} was not unlocked.", parent=self)
                    return
                try:
                    saver = SecretsSaver(filename=db_name, key=pwd)
                    saver.list_secrets() # force load
                    self.savers[db_name] = saver
                    self.schedule_lock(db_name)
                    # Visually unlock it
                    for item in self.secrets_tree.get_children():
                        tags = self.secrets_tree.item(item, "tags")
                        if tags and "db" in tags and tags[1] == db_name:
                            children = self.secrets_tree.get_children(item)
                            if len(children) == 1 and "dummy" in self.secrets_tree.item(children[0], "tags"):
                                self.secrets_tree.delete(children[0])
                                self.populate_db_node(item, db_name, self.search_var.get().lower())
                                self.secrets_tree.item(item, tags=("db", db_name, "unlocked_db"))
                                self.secrets_tree.item(item, open=True)
                            break
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to unlock {db_name}: {e}")
                    return

        filepath = filedialog.asksaveasfilename(
            title="Export Selection",
            defaultextension=".ep",
            filetypes=[("Secrets Files", "*.ep"), ("All Files", "*.*")]
        )
        
        if not filepath:
            return
            
        self.update()
        export_key = simpledialog.askstring(
            "Export Key", 
            "Enter a password to encrypt the newly exported file:", 
            show="*",
            parent=self
        )
        
        if not export_key:
            messagebox.showwarning("Warning", "Export cancelled. A password is required.", parent=self)
            return
            
        try:
            exporter = SecretsSaver(filename=filepath, key=export_key)
            exported_names = set()
            processed_secrets = set() # To prevent double exporting the exact same secret
            count = 0
            
            # Helper function to add a secret intelligently avoiding duplicates
            def process_secret(s_name, s_val, s_group, s_url, origin_db):
                nonlocal count
                if (origin_db, s_name, s_group) in processed_secrets:
                    return # already grabbed this specific secret through a wider selection
                
                processed_secrets.add((origin_db, s_name, s_group))
                final_name = s_name
                
                if (s_group, final_name) in exported_names:
                    db_base = os.path.splitext(origin_db)[0]
                    final_name = f"{s_name} ({db_base})"
                    
                    suffix = 1
                    base_final = final_name
                    while (s_group, final_name) in exported_names:
                        final_name = f"{base_final} {suffix}"
                        suffix += 1
                        
                exporter.set_secret(final_name, s_val, s_group, s_url)
                exported_names.add((s_group, final_name))
                count += 1

            # 1. Process entirely selected databases
            for db_name in dbs_to_export:
                saver = self.savers.get(db_name)
                if not saver: continue
                secrets = saver.list_secrets()
                for s in secrets:
                    name = s["name"]
                    group = s["group"]
                    url = s.get("url", "")
                    val = saver.get_secret(name, group)
                    process_secret(name, val, group, url, db_name)

            # 2. Process specific groups
            for db_name, group_name in groups_to_export:
                saver = self.savers.get(db_name)
                if not saver: continue # Should be unlocked if they selected its subfolders, but catch to be safe
                secrets = saver.list_secrets()
                for s in secrets:
                    if s["group"] == group_name:
                        name = s["name"]
                        url = s.get("url", "")
                        val = saver.get_secret(name, group_name)
                        process_secret(name, val, group_name, url, db_name)
                            
            # 3. Process individual secrets
            for db_name, group_name, secret_name in secrets_to_export:
                saver = self.savers.get(db_name)
                if not saver: continue
                
                url = ""
                for s in saver.list_secrets():
                    if s["group"] == group_name and s["name"] == secret_name:
                        url = s.get("url", "")
                        break
                        
                val = saver.get_secret(secret_name, group_name)
                process_secret(secret_name, val, group_name, url, db_name)
            
            # Force password change on exported file
            exporter.set_config("change_password", True)
            
            messagebox.showinfo("Success", f"Successfully exported {count} items.")
            self.refresh_list() # refresh so the newly created .ep file shows up as a top level folder
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")

    def change_password(self, preset_db=None):
        if preset_db:
            db_name = preset_db
        else:
            selection = self.secrets_tree.selection()
            if not selection:
                messagebox.showinfo("Select", "Please select a database or an item inside it to change its password.")
                return

            item_id = selection[0]
            tags = self.secrets_tree.item(item_id, "tags")
            if not tags: return

            # Index 1 of tags contains the db_name based on our tree population logic
            db_name = tags[1]
            
        if db_name not in self.savers:
            messagebox.showinfo("Unlock", f"Please expand and unlock '{db_name}' first.")
            return

        saver = self.savers[db_name]

        self.update()
        old_pwd = simpledialog.askstring("Change Password", f"Enter OLD password for {db_name}:", show="*", parent=self)
        if not old_pwd:
            return

        if old_pwd.encode('utf-8') != saver._key:
            messagebox.showerror("Error", "Incorrect old password.", parent=self)
            return

        while True:
            self.update()
            new_pwd = simpledialog.askstring("Change Password", f"Enter NEW password for {db_name}:", show="*", parent=self)
            if not new_pwd:
                return

            confirm_pwd = simpledialog.askstring("Change Password", f"Confirm NEW password for {db_name}:", show="*", parent=self)
            if new_pwd != confirm_pwd:
                messagebox.showwarning("Warning", "Passwords do not match! Try again.", parent=self)
                continue

            try:
                self.savers[db_name].change_key(new_pwd)
                messagebox.showinfo("Success", f"Password for {db_name} changed successfully.", parent=self)
                break
            except ValueError as ve:
                messagebox.showerror("Error", str(ve), parent=self)
                continue
            except Exception as e:
                messagebox.showerror("Error", f"Failed to change password: {e}", parent=self)
                break

    def merge_dbs(self):
        selection = self.secrets_tree.selection()
        db_names = []
        for item_id in selection:
            tags = self.secrets_tree.item(item_id, "tags")
            if tags and "db" in tags:
                db_names.append(tags[1])
                
        if len(db_names) < 2:
            messagebox.showinfo("Select", "Please select at least two database (.ep) folders to merge (use Ctrl+Click to select multiple).")
            return
            
        # Ensure all selected DBs are unlocked
        for db_name in db_names:
            if db_name not in self.savers:
                self.update()
                pwd = simpledialog.askstring("Unlock", f"Please unlock {db_name} for merging:", show="*", parent=self)
                if not pwd:
                    messagebox.showwarning("Warning", f"Merge cancelled because {db_name} was not unlocked.", parent=self)
                    return
                try:
                    saver = SecretsSaver(filename=db_name, key=pwd)
                    saver.list_secrets() # force load
                    self.savers[db_name] = saver
                    self.schedule_lock(db_name)
                    # Visually unlock it
                    for item in self.secrets_tree.get_children():
                        tags = self.secrets_tree.item(item, "tags")
                        if tags and "db" in tags and tags[1] == db_name:
                            children = self.secrets_tree.get_children(item)
                            if len(children) == 1 and "dummy" in self.secrets_tree.item(children[0], "tags"):
                                self.secrets_tree.delete(children[0])
                                self.populate_db_node(item, db_name, self.search_var.get().lower())
                                self.secrets_tree.item(item, tags=("db", db_name, "unlocked_db"))
                                self.secrets_tree.item(item, open=True)
                            break
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to unlock {db_name}: {e}", parent=self)
                    return
                    
        # Ask for new file
        filepath = filedialog.asksaveasfilename(
            title="Save Merged Database As",
            defaultextension=".ep",
            filetypes=[("Secrets Files", "*.ep"), ("All Files", "*.*")]
        )
        if not filepath: return
        
        # Ask for password for merged DB
        self.update()
        merge_key = simpledialog.askstring("Merge Key", f"Enter a password to encrypt the new merged file '{os.path.basename(filepath)}':", show="*", parent=self)
        if not merge_key:
            messagebox.showwarning("Warning", "Merge cancelled. A password is required.")
            return
            
        try:
            merged_saver = SecretsSaver(filename=filepath, key=merge_key)
            # track names by group for deduplication
            merged_identifiers = set((s["group"], s["name"]) for s in merged_saver.list_secrets())
            
            count = 0
            for db_name in db_names:
                saver = self.savers[db_name]
                for s in saver.list_secrets():
                    grp = s["group"]
                    name = s["name"]
                    val = saver.get_secret(name, grp)
                    
                    final_name = name
                    suffix = 1
                    while (grp, final_name) in merged_identifiers:
                        final_name = f"{name} ({suffix})"
                        suffix += 1
                        
                    merged_saver.set_secret(final_name, val, grp)
                    merged_identifiers.add((grp, final_name))
                    count += 1
                    
            messagebox.showinfo("Success", f"Successfully merged {count} secrets into '{os.path.basename(filepath)}'.")
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Merge Error", f"Failed to merge databases: {e}")

    def forget_all(self):
        if not self.savers:
            return
            
        # Wipe and discard all SecretSaver instances
        for saver in self.savers.values():
            saver._data = None
            saver._key = None
        self.savers.clear()
        
        # Cancel any pending lock timers
        for timer in self.lock_timers.values():
            self.after_cancel(timer)
        self.lock_timers.clear()
        self.lock_deadlines.clear()
        
        # Clear clipboard just in case
        self.clipboard_clear()
        
        # Refresh UI to return to locked state and force them to collapse
        self.refresh_list(preserve_state=False)
        self.show_toast("All databases have been locked.")

    def create_image(self):
        try:
            return Image.open(resource_path("favicon.ico"))
        except FileNotFoundError:
            # Fallback to simple icon if not found
            image = Image.new('RGB', (64, 64), color=(43, 43, 43))
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 16, 48, 48), fill=(0, 120, 215))
            draw.text((22, 24), "SM", fill=(255, 255, 255))
            return image

    def hide_window(self):
        self.withdraw()
        image = self.create_image()
        menu = pystray.Menu(
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Quit', self.quit_window)
        )
        self.tray_icon = pystray.Icon("SecretsManager", image, "Secrets Manager", menu)
        # Run in a separate thread so it doesn't block tkinter mainloop
        import threading
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon, item):
        icon.stop()
        self.after(0, self.deiconify)
        
    def do_quit(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()

    def quit_window(self, icon, item):
        icon.stop()
        self.after(0, self.destroy)

if __name__ == "__main__":
    import sys
    parser = argparse.ArgumentParser(description="Secrets Manager GUI")
    parser.add_argument("--timeout", type=float, default=60.0, help="Custom lock timeout in minutes")
    parser.add_argument("--example-csv", action="store_true", help="Outputs a sample import CSV and quits")
    args = parser.parse_args()

    if args.example_csv:
        sample_csv = "Group,Name,Value,URL\nSocial,Twitter,my_password123,https://twitter.com\nWork,Email,secure_pwd!,https://mail.work.com\n"
        with open("import_sample.csv", "w", encoding="utf-8") as f:
            f.write(sample_csv)
        print("Created import_sample.csv")
        sys.exit(0)

    app = SecretsGUI(timeout_minutes=args.timeout)
    app.mainloop()
