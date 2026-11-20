"""Restaurant desktop client for the Small Restaurant.sql schema."""
import os
import sys
import re
import tkinter as tk
from tkinter import ttk, messagebox
from contextlib import closing

try:
    import pyodbc
except ImportError:
    pyodbc = None


def connect():
    if pyodbc is None:
        raise RuntimeError("Install pyodbc with: py -m pip install pyodbc")
    database = os.environ.get("RESTAURANT_DB", "RESTAURANT")
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("Invalid RESTAURANT_DB database name.")
    drivers = pyodbc.drivers()
    for version in (18, 17):
        driver = f"ODBC Driver {version} for SQL Server"
        if driver in drivers:
            return pyodbc.connect(
                f"DRIVER={{{driver}}};SERVER=localhost;DATABASE={database};"
                "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;",
                timeout=5,
            )
    raise RuntimeError("Install Microsoft ODBC Driver 18 for SQL Server.")


QUERIES = {
    "Customers": ("SELECT CUSTOMERID, NAME, PHONE FROM CUSTOMER ORDER BY CUSTOMERID",
                  ("ID", "Name", "Phone")),
    "Menu": ("SELECT ITEMID, ITEMNAME, PRICE, CATEGORY FROM MENUU ORDER BY ITEMID",
             ("ID", "Item", "Price", "Category")),
    "Orders": ("SELECT o.ORDERID, o.ORDERDATE, o.CUSTOMERID, c.NAME, o.TOTALPRICE FROM ORDERRRR o LEFT JOIN CUSTOMER c ON c.CUSTOMERID=o.CUSTOMERID ORDER BY o.ORDERID",
               ("ID", "Date", "Customer ID", "Customer", "Total (EGP)")),
    "Order details": ("""SELECT d.ORDERID, d.ITEMID, m.ITEMNAME, d.QUANTITY, d.UNITPRICE, d.QUANTITY*d.UNITPRICE
                         FROM ORDERDETAILS d JOIN MENUU m ON m.ITEMID = d.ITEMID
                         ORDER BY d.ORDERID, d.ITEMID""",
                      ("Order ID", "Item ID", "Item", "Quantity", "Sale price", "Line total")),
}


from datetime import date
from decimal import Decimal


# Only identifiers from this fixed schema are used to build SQL.
SCHEMA = {
    "Customers": ("CUSTOMER", ("CUSTOMERID", "NAME", "PHONE"), 1),
    "Menu": ("MENUU", ("ITEMID", "ITEMNAME", "PRICE", "CATEGORY"), 1),
    "Orders": ("ORDERRRR", ("ORDERID", "ORDERDATE", "CUSTOMERID"), 1),
    "Order details": ("ORDERDETAILS", ("ORDERID", "ITEMID", "QUANTITY"), 2),
}
LABELS = {
    "CUSTOMERID": "Customer ID", "NAME": "Name", "PHONE": "Phone",
    "ITEMID": "Item ID", "ITEMNAME": "Item name", "PRICE": "Price",
    "CATEGORY": "Category", "ORDERID": "Order ID", "ORDERDATE": "Date (YYYY-MM-DD)",
    "TOTALPRICE": "Stored total", "QUANTITY": "Quantity",
}


def parse_value(column, value):
    value = value.strip()
    if column.endswith("ID") or column == "QUANTITY":
        if not re.fullmatch(r"[0-9]{1,10}", value) or not 1 <= int(value) <= 2147483647:
            raise ValueError(f"{LABELS[column]} must be a positive whole number.")
        return int(value)
    if column == "PHONE" and not re.fullmatch(r"0[0-9]{10}", value):
        raise ValueError("Enter 11 phone digits starting with 0.")
    if column in ("PRICE", "TOTALPRICE"):
        if not re.fullmatch(r"[0-9]{1,8}(\.[0-9]{1,2})?", value):
            raise ValueError("Enter a non-negative amount with up to two decimal places.")
        return Decimal(value)
    if column == "ORDERDATE":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use YYYY-MM-DD for the date.")
        return date.fromisoformat(value)
    length = {"NAME": 50, "ITEMNAME": 40, "CATEGORY": 30}.get(column)
    if length and not 1 <= len(value) <= length:
        raise ValueError(f"{LABELS[column]} requires 1 to {length} characters.")
    return value


def write_row(cursor, page, action, values, original):
    table, columns, key_count = SCHEMA[page]
    if action == "Add":
        if page == "Orders":
            columns = (*columns, "TOTALPRICE")
            values = (*values, 0)
        elif page == "Order details":
            price_row = cursor.execute("SELECT PRICE FROM MENUU WITH (HOLDLOCK) WHERE ITEMID=?", values[1]).fetchone()
            if not price_row or price_row[0] is None or price_row[0] < 0:
                raise ValueError("Choose a menu item with a valid price.")
            columns = (*columns, "UNITPRICE")
            values = (*values, price_row[0])
        marks = ", ".join("?" for _ in columns)
        cursor.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})", values)
        return
    # Match the loaded record so a stale edit cannot overwrite a teammate's work.
    terms, params = [], []
    for col, val in zip(columns, original):
        if val is None:
            terms.append(f"{col} IS NULL")
        else:
            terms.append(f"{col} = ?")
            params.append(val)
    where = " AND ".join(terms)
    if action == "Update":
        assignments = ", ".join(f"{col} = ?" for col in columns[key_count:])
        cursor.execute(f"UPDATE {table} SET {assignments} WHERE {where}",
                       tuple(values[key_count:]) + tuple(params))
    else:
        cursor.execute(f"DELETE FROM {table} WHERE {where}", tuple(params))
    if cursor.rowcount != 1:
        raise ValueError("This row changed or was deleted. Refresh and try again.")


class Editor(ttk.Frame):
    def __init__(self, notebook, app, title):
        super().__init__(notebook, padding=12)
        self.app, self.title = app, title
        _, self.columns, self.key_count = SCHEMA[title]
        self.records = {}
        self.original = None
        self.fields = {}
        headings = QUERIES[title][1]
        self.gridview = ttk.Treeview(self, columns=headings, show="headings", selectmode="browse")
        for col in headings:
            self.gridview.heading(col, text=col)
            self.gridview.column(col, width=120, anchor="w")
        scroll = ttk.Scrollbar(self, command=self.gridview.yview)
        self.gridview.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self.gridview.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        form = ttk.Frame(self, padding=(0, 12))
        form.grid(row=1, column=0, sticky="ew")
        for i, col in enumerate(self.columns):
            ttk.Label(form, text=LABELS[col]).grid(row=0, column=i, sticky="w")
            field = ttk.Entry(form, width=15)
            field.grid(row=1, column=i, sticky="ew", padx=(0, 8))
            form.columnconfigure(i, weight=1)
            self.fields[col] = field
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="w")
        ttk.Button(buttons, text="New / Clear", command=self.clear).pack(side="left")
        for action in ("Add", "Update", "Delete"):
            ttk.Button(buttons, text=action, style={"Add": "Add.TButton", "Delete": "Delete.TButton"}.get(action, "TButton"),
                       command=lambda a=action: self.save(a)).pack(side="left", padx=3)
        self.gridview.bind("<<TreeviewSelect>>", self.select)

    def populate(self, rows):
        self.clear()
        self.gridview.delete(*self.gridview.get_children())
        self.records.clear()
        self.gridview.tag_configure("alternate", background="#f0f5fa")
        for index, row in enumerate(rows):
            item = self.gridview.insert("", "end", tags=("alternate",) if index % 2 else (), values=tuple("" if v is None else str(v) for v in row))
            self.records[item] = (row[0], row[1], row[3]) if self.title == "Order details" else tuple(row[:len(self.columns)])

    def clear(self):
        self.gridview.selection_remove(*self.gridview.selection())
        self.original = None
        for field in self.fields.values():
            field.configure(state="normal")
            field.delete(0, "end")

    def select(self, event):
        selected = self.gridview.selection()
        if not selected:
            return
        self.original = self.records[selected[0]]
        for i, (field, val) in enumerate(zip(self.fields.values(), self.original)):
            field.configure(state="normal")
            field.delete(0, "end")
            if val is not None:
                field.insert(0, str(val))
            if i < self.key_count:
                field.configure(state="readonly")

    def save(self, action):
        if action == "Add" and self.original is not None:
            messagebox.showinfo(action, "Click New / Clear before adding a row.")
            return
        if action != "Add" and self.original is None:
            messagebox.showinfo(action, "Select a row first.")
            return
        try:
            values = []
            if action != "Delete":
                for i, col in enumerate(self.columns):
                    raw = self.fields[col].get()
                    if self.original and raw == str(self.original[i] if self.original[i] is not None else ""):
                        values.append(self.original[i])
                    else:
                        values.append(parse_value(col, raw))
            elif not messagebox.askyesno("Confirm delete",
                    f"Delete {self.title} row {self.original[:self.key_count]}?"):
                return
            with closing(connect()) as db:
                write_row(db.cursor(), self.title, action, values, self.original)
                db.commit()
        except Exception as error:
            message = str(error)
            if "547" in message:
                message = ("Check the order and item IDs. To remove a referenced order or menu item, "
                           "delete its order details first.\n\n" + message)
            elif "2627" in message or "2601" in message:
                message = "This ID or order/item combination already exists."
            messagebox.showerror(action, message)
            return
        self.app.refresh(f"{self.title}: {action} saved.")


NAVY = "#142947"
TEAL = "#008984"
PAPER = "#f7f9fc"
INK = "#162944"


def table(parent, headings):
    grid = ttk.Treeview(parent, height=4, columns=headings, show="headings", selectmode="browse")
    for name in headings:
        grid.heading(name, text=name)
        grid.column(name, width=72, minwidth=45, anchor="w")
    grid.column(headings[0], width=146)
    grid.pack(fill="both", expand=True, padx=8, pady=8)
    return grid


class Restaurant:
    def __init__(self, root):
        self.root = root
        root.title("Restaurant Order Management")
        root.geometry("1120x700")
        root.minsize(900, 530)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), foreground=INK, background=PAPER)
        style.configure("TEntry", fieldbackground="white", padding=5)
        style.configure("TButton", padding=(10, 6))
        style.configure("Add.TButton", background=TEAL, foreground="white")
        style.map("Add.TButton", background=[("active", "#006e6b")])
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=28)
        style.configure("Treeview.Heading", background="#e0e7ef", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#c2e1fa")], foreground=[("selected", INK)])
        tk.Label(root, text="  Restaurant Order Management", bg=NAVY, fg="white",
                 font=("Segoe UI", 15, "bold"), anchor="w", pady=9).pack(fill="x")
        self.status = tk.StringVar(value="Connecting…")
        ttk.Label(root, textvariable=self.status, padding=5).pack(side="bottom", fill="x")
        side = tk.Frame(root, bg=NAVY, padx=8, pady=20)
        side.pack(side="left", fill="y")
        workspace = ttk.Frame(root, padding=14)
        workspace.pack(fill="both", expand=True)
        top = ttk.Frame(workspace)
        top.pack(fill="x")
        self.heading = ttk.Label(top, font=("Segoe UI", 22, "bold"))
        self.heading.pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right")
        self.body = ttk.Frame(workspace)
        self.body.pack(fill="both", expand=True)
        self.cart, self.menu, self.customers = {}, {}, {}
        self.pages = {"New Order": ttk.Frame(self.body)}
        self.order_screen(self.pages["New Order"])
        self.buttons = {}
        for key in ["New Order", *SCHEMA]:
            label = "Order History" if key == "Orders" else key
            if key in SCHEMA:
                self.pages[key] = Editor(self.body, self, key)
            button = tk.Button(side, text=label, width=15, anchor="w", relief="flat",
                               fg="white", bg=NAVY, activebackground=TEAL,
                               activeforeground="white", font=("Segoe UI", 12),
                               padx=12, pady=9, command=lambda k=key: self.show(k))
            button.pack(fill="x", pady=3)
            self.buttons[key] = button
        self.show("New Order")
        root.after_idle(self.refresh)

    def show(self, page):
        for key, panel in self.pages.items():
            panel.pack_forget()
            self.buttons[key].configure(bg=TEAL if page == key else NAVY)
        self.heading.configure(text=self.buttons[page]["text"])
        self.pages[page].pack(fill="both", expand=True)

    def order_screen(self, frame):
        ttk.Label(frame, text="Create and save a customer order").pack(anchor="w", pady=(0, 12))
        bar = ttk.Frame(frame, padding=9)
        bar.pack(fill="x")
        self.customer = ttk.Combobox(bar, state="readonly", width=23)
        self.phone = tk.StringVar()
        for i, (label, widget) in enumerate([
                ("Customer", self.customer),
                ("Phone", ttk.Entry(bar, textvariable=self.phone, state="readonly"))]):
            ttk.Label(bar, text=label).grid(row=0, column=i, sticky="w")
            widget.grid(row=1, column=i, sticky="ew", padx=(0, 12))
            bar.columnconfigure(i, weight=1)
        self.customer.bind("<<ComboboxSelected>>", self.update_phone)
        ttk.Button(bar, text="+ Add Customer", style="Add.TButton",
                   command=self.new_customer).grid(row=1, column=2)
        panels = ttk.Frame(frame)
        panels.pack(fill="both", expand=True, pady=10)
        panels.rowconfigure(0, weight=1)
        cards = []
        for i, label in enumerate(("Menu", "Current Order")):
            card = ttk.LabelFrame(panels, text=label, padding=5)
            card.grid(row=0, column=i, sticky="nsew", padx=3)
            panels.columnconfigure(i, weight=1, uniform="cards")
            cards.append(card)
        self.search = tk.StringVar()
        ttk.Label(cards[0], text="Search items").pack(anchor="w", padx=8)
        ttk.Entry(cards[0], textvariable=self.search).pack(fill="x", padx=8)
        self.search.trace_add("write", lambda *_: self.filter_menu())
        self.catalog = table(cards[0], ("Item", "Category", "EGP"))
        self.basket = table(cards[1], ("Item", "Qty", "Price", "Total"))
        controls = ttk.Frame(cards[0])
        controls.pack(side="bottom", fill="x", before=self.catalog)
        ttk.Label(controls, text="Quantity").pack(side="left")
        self.qty = ttk.Spinbox(controls, from_=1, to=9999, width=5)
        self.qty.set(1)
        self.qty.pack(side="left", padx=4)
        ttk.Button(controls, text="Add to Order", command=self.add_item,
                   style="Add.TButton").pack(side="right")
        ttk.Button(cards[1], text="Remove Selected", command=self.remove_item).pack(side="bottom", anchor="w", before=self.basket)
        footer = ttk.Frame(frame, padding=6)
        footer.pack(side="bottom", fill="x", before=panels)
        self.total = ttk.Label(footer, text="Total: EGP 0.00", font=("Segoe UI", 17, "bold"))
        self.total.pack(anchor="e")
        ttk.Button(footer, text="Clear Order", command=self.clear_cart).pack(side="right", padx=5)
        ttk.Button(footer, text="Save Order", style="Add.TButton", command=self.save_order).pack(side="right")

    def new_customer(self):
        self.show("Customers")
        self.pages["Customers"].clear()
        self.pages["Customers"].fields["CUSTOMERID"].focus_set()

    def update_phone(self, event=None):
        row = self.customers.get(self.customer.get())
        self.phone.set((row[2] or "") if row else "")

    def refresh(self, status="Ready"):
        try:
            with closing(connect()) as db:
                cur = db.cursor()
                check_schema(cur)
                data = {page: cur.execute(sql).fetchall() for page, (sql, _) in QUERIES.items()}
            for key, rows in data.items():
                self.pages[key].populate(rows)
            self.customers = {f"{r[1]} (#{r[0]})": r for r in data["Customers"]}
            self.customer.configure(values=list(self.customers))
            if self.customer.get() not in self.customers:
                self.customer.set(next(iter(self.customers), ""))
            self.update_phone()
            self.menu = {int(r[0]): r for r in data["Menu"]}
            self.filter_menu()
            self.status.set(status)
        except Exception as error:
            self.status.set("Refresh failed")
            messagebox.showerror("Refresh", str(error))

    def filter_menu(self):
        self.catalog.delete(*self.catalog.get_children())
        needle = self.search.get().casefold()
        for key, (_, name, price, category) in self.menu.items():
            if needle in f"{name} {category}".casefold():
                self.catalog.insert("", "end", iid=str(key), values=(name, category, price))

    def add_item(self):
        selected = self.catalog.selection()
        if not selected:
            return messagebox.showinfo("Menu", "Select an item first.")
        try:
            qty = parse_value("QUANTITY", self.qty.get())
            key = int(selected[0])
            _, name, price, _ = self.menu[key]
            if price is None or price < 0:
                raise ValueError("Set a valid menu price first.")
            if key in self.cart:
                old_name, old_price, count = self.cart[key]
                if old_price != price:
                    raise ValueError("Price changed. Remove this item and add it again.")
                qty = parse_value("QUANTITY", str(qty + count))
            self.cart[key] = (name, price, qty)
            self.draw_cart()
        except ValueError as error:
            messagebox.showerror("Menu", str(error))

    def remove_item(self):
        for key in self.basket.selection():
            self.cart.pop(int(key))
        self.draw_cart()

    def clear_cart(self):
        self.cart.clear()
        self.draw_cart()

    def draw_cart(self):
        self.basket.delete(*self.basket.get_children())
        total = Decimal(0)
        for key, (name, price, qty) in self.cart.items():
            total += price * qty
            self.basket.insert("", "end", iid=str(key), values=(name, qty, price, f"{price * qty:.2f}"))
        self.total.configure(text=f"Total: EGP {total:,.2f}")

    def save_order(self):
        customer = self.customers.get(self.customer.get())
        if not self.cart or not customer:
            return messagebox.showinfo("New Order", "Choose a customer and add at least one item.")
        try:
            with closing(connect()) as db:
                cur = db.cursor()
                total = sum(price * qty for _, price, qty in self.cart.values())
                if total > Decimal("99999999.99"):
                    raise ValueError("Order total exceeds the database limit.")
                cur.execute("SELECT COALESCE(MAX(ORDERID),0)+1 FROM ORDERRRR WITH (UPDLOCK,HOLDLOCK)")
                order_id = cur.fetchone()[0]
                cur.execute("INSERT INTO ORDERRRR (ORDERID,ORDERDATE,TOTALPRICE,CUSTOMERID) VALUES(?,?,?,?)",
                            order_id, date.today(), total, customer[0])
                for key, (_, price, qty) in self.cart.items():
                    current = cur.execute("SELECT PRICE FROM MENUU WITH (HOLDLOCK) WHERE ITEMID=?", key).fetchone()
                    if not current or current[0] != price:
                        raise ValueError("Menu changed. Refresh, remove the affected item and add it again.")
                    cur.execute("INSERT INTO ORDERDETAILS (ORDERID,ITEMID,QUANTITY,UNITPRICE) VALUES (?,?,?,?)",
                                order_id, key, qty, price)
                db.commit()
        except Exception as error:
            return messagebox.showerror("Save Order", str(error))
        self.clear_cart()
        self.refresh(f"Order #{order_id} saved.")


def check_schema(cur):
    row = cur.execute("""SELECT COL_LENGTH('dbo.ORDERRRR','CUSTOMERID'),
               COL_LENGTH('dbo.ORDERDETAILS','UNITPRICE'),
               OBJECTPROPERTY(OBJECT_ID('dbo.trg_OrderDetails_Total'),'ExecIsTriggerDisabled')""").fetchone()
    if row[0] is None or row[1] is None or row[2] != 0:
        raise ValueError("Select a database with the updated Small Restaurant.sql schema and enabled order-total trigger.")


def check_database():
    with closing(connect()) as db:
        try:
            cur = db.cursor()
            check_schema(cur)
            for query, _ in QUERIES.values():
                cur.execute(query).fetchall()
            customer = cur.execute("SELECT TOP 1 CUSTOMERID FROM CUSTOMER ORDER BY CUSTOMERID").fetchone()
            item = cur.execute("SELECT TOP 1 ITEMID,PRICE FROM MENUU WITH (HOLDLOCK) WHERE PRICE BETWEEN 0.01 AND 10000 ORDER BY ITEMID").fetchone()
            if not customer or not item:
                raise ValueError("Test requires a customer and a menu item priced between 0.01 and 10000.")
            oid = cur.execute("SELECT COALESCE(MAX(ORDERID),0)+1 FROM ORDERRRR WITH (UPDLOCK,HOLDLOCK)").fetchone()[0]
            write_row(cur, "Orders", "Add", (oid, date.today(), customer[0]), None)
            for action, quantity, previous in [("Add", 2, None), ("Update", 3, 2), ("Delete", 0, 3)]:
                values = (oid, item[0], quantity)
                original = (oid, item[0], previous)
                write_row(cur, "Order details", action, values, original)
                total, customer_id = cur.execute("SELECT TOTALPRICE,CUSTOMERID FROM ORDERRRR WHERE ORDERID=?", oid).fetchone()
                if total != item[1] * quantity or customer_id != customer[0]:
                    raise ValueError(f"{action} test failed: unexpected total or customer.")
        finally:
            db.rollback()
    print("PASS: connection, four views, customer link and order totals. Test changes rolled back.")


if __name__ == "__main__":
    if "--check" in sys.argv:
        try:
            check_database()
        except Exception as error:
            sys.exit(f"Check failed: {error}")
    else:
        root = tk.Tk()
        Restaurant(root)
        root.mainloop()
