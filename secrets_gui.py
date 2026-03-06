import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from secrets_saver import SecretsSaver

class SecretsGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Secrets Manager")
        self.geometry("400x400")
        
        self.saver = None
        
        # UI Elements for Authentication
        self.auth_frame = tk.Frame(self)
        self.auth_frame.pack(pady=20, fill=tk.BOTH, expand=True)

        tk.Label(self.auth_frame, text="Unlock Secrets", font=("Arial", 14)).pack(pady=10)
        
        self.key_entry = tk.Entry(self.auth_frame, show="*", width=30)
        self.key_entry.pack(pady=5)
        
        tk.Button(self.auth_frame, text="Unlock with String", command=self.unlock_with_string).pack(pady=5)
        
        tk.Label(self.auth_frame, text="OR").pack(pady=5)
        
        tk.Button(self.auth_frame, text="Unlock with Key File", command=self.unlock_with_file).pack(pady=5)

        # UI Elements for Main App
        self.main_frame = tk.Frame(self)
        
        self.secrets_listbox = tk.Listbox(self.main_frame)
        self.secrets_listbox.pack(pady=10, fill=tk.BOTH, expand=True)
        self.secrets_listbox.bind("<<ListboxSelect>>", self.on_select_secret)

        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="Add Secret", command=self.add_secret).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Delete All", command=self.clear_database).pack(side=tk.RIGHT, padx=5)

    def unlock_with_string(self):
        key = self.key_entry.get()
        if key:
            self.init_saver(key)
        else:
            messagebox.showwarning("Warning", "Please enter a key string.")

    def unlock_with_file(self):
        filepath = filedialog.askopenfilename(title="Select Key File")
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    key = f.read().strip()
                self.init_saver(key)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read file: {e}")

    def init_saver(self, key):
        try:
            self.saver = SecretsSaver(key=key)
            self.refresh_list()
            self.auth_frame.pack_forget()
            self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to unlock: {e}\nCheck your key!")

    def refresh_list(self):
        self.secrets_listbox.delete(0, tk.END)
        try:
            secrets = self.saver.list_secrets()
            for s in secrets:
                self.secrets_listbox.insert(tk.END, s)
        except Exception as e:
             messagebox.showerror("Error", f"Failed to load secrets: {e}\nCheck your key!")
             self.main_frame.pack_forget()
             self.auth_frame.pack(pady=20, fill=tk.BOTH, expand=True)

    def add_secret(self):
        name = simpledialog.askstring("Add Secret", "Secret Name:")
        if not name:
            return
        value = simpledialog.askstring("Add Secret", f"Value for {name}:", show="*")
        if value is not None:
            try:
                self.saver.set_secret(name, value)
                self.refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save secret: {e}")

    def on_select_secret(self, event):
        selection = self.secrets_listbox.curselection()
        if selection:
            name = self.secrets_listbox.get(selection[0])
            try:
                value = self.saver.get_secret(name)
                # Show the secret and allow copying
                self.show_secret_value(name, value)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to get secret: {e}")

    def show_secret_value(self, name, value):
        top = tk.Toplevel(self)
        top.title(f"Secret: {name}")
        top.geometry("300x150")
        
        tk.Label(top, text=f"Value for {name}:").pack(pady=5)
        
        entry = tk.Entry(top, width=30, show="*")
        entry.insert(0, value)
        entry.config(state="readonly")
        entry.pack(pady=10)
        
        def copy():
            self.clipboard_clear()
            self.clipboard_append(value)
            self.update()
            top.destroy()
            messagebox.showinfo("Copied", "Secret value copied to clipboard!")
            
        tk.Button(top, text="Copy to Clipboard", command=copy).pack()

    def clear_database(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to delete all secrets?"):
            try:
                self.saver.clear_database()
                self.refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear database: {e}")

if __name__ == "__main__":
    app = SecretsGUI()
    app.mainloop()
