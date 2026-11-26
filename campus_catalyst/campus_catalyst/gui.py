import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import date
import csv

from campus_catalyst.models import VALID_STATUSES
from campus_catalyst.validators import CATEGORIES, validate_record_payload
from campus_catalyst.analytics import build_summary, search_records, get_warnings
from campus_catalyst.storage import SQLiteStorage, VolunteerStorage, StorageError, merge_records
from campus_catalyst.reports import export_markdown, export_text

APP_BG = "#F3F6FA"
SIDEBAR = "#14243A"
SIDEBAR_HOVER = "#203A56"
NAV_ACTIVE = "#176B72"
ACCENT = "#1A9A91"
ACCENT_LIGHT = "#E3F5F2"
TEXT = "#1C2B3A"
MUTED = "#718096"
WHITE = "#FFFFFF"
BORDER = "#E4EAF1"
GREEN = "#16845B"
ORANGE = "#C47A16"
RED = "#C94B4B"
BLUE = "#3867B7"

class CampusCatalystApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Campus Catalyst | Volunteer Hours Tracker")
        self.geometry("1240x790")
        self.minsize(1050, 680)
        self.configure(bg=APP_BG)
        self.storage = SQLiteStorage()
        try:
            self.records = self.storage.load()
        except StorageError as exc:
            messagebox.showerror("Data file problem", str(exc))
            self.records = []
        if self.storage.recovery_message:
            messagebox.showwarning("Data file recovered", self.storage.recovery_message)
        self.current_page = "Dashboard"
        self.search_var = tk.StringVar()
        self.category_var = tk.StringVar(value="All categories")
        self.status_var = tk.StringVar(value="All statuses")
        self._style()
        self._layout()
        self.show_page("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=WHITE, foreground=TEXT,
                        fieldbackground=WHITE, rowheight=34, borderwidth=0,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#EAF0F6", foreground="#42556B",
                        font=("Segoe UI", 9, "bold"), relief="flat", padding=(9, 10))
        style.map("Treeview", background=[("selected", "#DDF2EF")],
                  foreground=[("selected", TEXT)])
        style.configure("TCombobox", padding=7, font=("Segoe UI", 9))
        style.configure("TEntry", padding=8, font=("Segoe UI", 9))
        style.configure("Vertical.TScrollbar", background="#DCE5ED", troughcolor=APP_BG)

    def _layout(self):
        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=235)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=22, pady=(25, 30))
        tk.Label(brand, text="✦", bg=SIDEBAR, fg="#53D4C4",
                 font=("Segoe UI", 25, "bold")).pack(anchor="w")
        tk.Label(brand, text="CAMPUS", bg=SIDEBAR, fg=WHITE,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(brand, text="CATALYST", bg=SIDEBAR, fg="#72D6CA",
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(brand, text="VOLUNTEER HOURS TRACKER", bg=SIDEBAR, fg="#A9BBCB",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(4, 0))

        tk.Label(self.sidebar, text="WORKSPACE", bg=SIDEBAR, fg="#8196AA",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=23, pady=(0, 9))
        self.nav_buttons = {}
        nav_items = [
            ("Dashboard", "▦"), ("Volunteer Records", "▤"),
            ("Add Volunteer", "＋"), ("Search & Filter", "⌕"),
            ("Analytics", "◫"), ("Import Dataset", "⇧"),
            ("Export Reports", "⇩"), ("Warnings", "⚑"),
        ]
        for name, symbol in nav_items:
            button = tk.Button(self.sidebar, text=f"  {symbol}    {name}",
                               anchor="w", relief="flat", bd=0, cursor="hand2",
                               bg=SIDEBAR, fg="#D6E0E9",
                               activebackground=SIDEBAR_HOVER, activeforeground=WHITE,
                               font=("Segoe UI", 10), padx=16, pady=11,
                               command=lambda n=name: self.show_page(n))
            button.pack(fill="x", padx=11, pady=2)
            self.nav_buttons[name] = button

        bottom = tk.Frame(self.sidebar, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=22, pady=22)
        tk.Frame(bottom, bg="#33485D", height=1).pack(fill="x", pady=(0, 12))
        tk.Label(bottom, text="PROJECT  #78", bg=SIDEBAR, fg="#8FA4B7",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(bottom, text="Safety & Community", bg=SIDEBAR, fg="#D6E0E9",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        self.main = tk.Frame(self, bg=APP_BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.topbar = tk.Frame(self.main, bg=WHITE, height=66,
                               highlightbackground=BORDER, highlightthickness=1)
        self.topbar.pack(fill="x")
        self.topbar.pack_propagate(False)
        self.page_title = tk.Label(self.topbar, text="Dashboard", bg=WHITE, fg=TEXT,
                                   font=("Segoe UI", 16, "bold"))
        self.page_title.pack(side="left", padx=28)
        self.top_right = tk.Frame(self.topbar, bg=WHITE)
        self.top_right.pack(side="right", padx=26)
        tk.Label(self.top_right, text="●", fg=ACCENT, bg=WHITE,
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Label(self.top_right, text="  Local data storage", fg=MUTED, bg=WHITE,
                 font=("Segoe UI", 9)).pack(side="left")

        self.content = tk.Frame(self.main, bg=APP_BG)
        self.content.pack(fill="both", expand=True, padx=27, pady=22)

    def clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_page(self, name):
        self.current_page = name
        self.page_title.config(text=name)
        for nav_name, button in self.nav_buttons.items():
            active = nav_name == name
            button.config(bg=NAV_ACTIVE if active else SIDEBAR,
                          fg=WHITE if active else "#D6E0E9",
                          font=("Segoe UI", 10, "bold" if active else "normal"))
        self.clear_content()
        pages = {
            "Dashboard": self.page_dashboard,
            "Volunteer Records": self.page_records,
            "Add Volunteer": self.page_add,
            "Search & Filter": self.page_search,
            "Analytics": self.page_analytics,
            "Import Dataset": self.page_import,
            "Export Reports": self.page_export,
            "Warnings": self.page_warnings,
        }
        pages[name]()

    def heading(self, title, subtitle):
        tk.Label(self.content, text=title, bg=APP_BG, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(self.content, text=subtitle, bg=APP_BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 18))

    def card(self, parent, title, value, detail, accent=ACCENT):
        frame = tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        tk.Frame(frame, bg=accent, width=4).pack(side="left", fill="y")
        inner = tk.Frame(frame, bg=WHITE)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=14)
        tk.Label(inner, text=title.upper(), bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(inner, text=value, bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(5, 1))
        tk.Label(inner, text=detail, bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        return frame

    def action_button(self, parent, text, command, primary=True):
        return tk.Button(parent, text=text, command=command, cursor="hand2",
                         relief="flat", bd=0, padx=15, pady=9,
                         bg=ACCENT if primary else WHITE,
                         fg=WHITE if primary else TEXT,
                         activebackground="#147C75" if primary else "#EAF0F6",
                         activeforeground=WHITE if primary else TEXT,
                         font=("Segoe UI", 9, "bold"),
                         highlightbackground=BORDER, highlightthickness=0 if primary else 1)

    def _table(self, parent, columns, headings, widths=None, height=11):
        wrap = tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=columns, show="headings", height=height)
        for i, col in enumerate(columns):
            tree.heading(col, text=headings[i])
            tree.column(col, width=(widths[i] if widths else 120), anchor="w")
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        yscroll.pack(side="right", fill="y", padx=(0, 5), pady=8)
        tree.tag_configure("Approved", foreground=GREEN)
        tree.tag_configure("Pending", foreground=ORANGE)
        tree.tag_configure("Rejected", foreground=RED)
        return tree

    def _populate(self, tree, records):
        tree.delete(*tree.get_children())
        for r in records:
            tree.insert("", "end", iid=r.record_id,
                        values=(r.record_id, r.service_date, r.volunteer_name,
                                r.activity, r.category, f"{r.hours:.2f}", r.status),
                        tags=(r.status,))

    def page_dashboard(self):
        self.heading("Good day! 👋", "Here is the latest overview of your campus volunteering activity.")
        s = build_summary(self.records)
        cards = tk.Frame(self.content, bg=APP_BG)
        cards.pack(fill="x", pady=(0, 18))
        values = [
            ("Total records", str(s["record_count"]), "All submitted activities", BLUE),
            ("Approved hours", f"{s['total_hours']:.1f}", "Verified service hours", GREEN),
            ("Pending hours", f"{s['pending_hours']:.1f}", "Awaiting approval", ORANGE),
            ("Volunteers", str(s["volunteer_count"]), "Unique contributors", ACCENT),
        ]
        for i, item in enumerate(values):
            c = self.card(cards, *item)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            cards.grid_columnconfigure(i, weight=1, uniform="cards")

        lower = tk.Frame(self.content, bg=APP_BG)
        lower.pack(fill="both", expand=True)
        left = tk.Frame(lower, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(left, text="Recent volunteer activity", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=17, pady=(15, 10))
        tree = self._table(left, ("id","date","name","activity","category","hours","status"),
                           ("RECORD ID","DATE","VOLUNTEER","ACTIVITY","CATEGORY","HOURS","STATUS"),
                           (78,90,125,150,115,55,80), height=9)
        self._populate(tree, sorted(self.records, key=lambda r:r.service_date, reverse=True)[:10])

        right = tk.Frame(lower, bg=WHITE, width=255,
                         highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Label(right, text="Quick actions", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(16, 12))
        for label, target in [
            ("＋  Add volunteer", "Add Volunteer"),
            ("▤  View records", "Volunteer Records"),
            ("◫  Analytics", "Analytics"),
            ("⇩  Export reports", "Export Reports"),
        ]:
            b = self.action_button(right, label, lambda n=target:self.show_page(n), False)
            b.pack(fill="x", padx=15, pady=5)
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", padx=15, pady=12)
        warning_count = len(get_warnings(self.records))
        tk.Label(right, text="ATTENTION", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16)
        tk.Label(right, text=f"{warning_count} item(s) need review", bg=WHITE,
                 fg=ORANGE if warning_count else GREEN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(5, 3))
        tk.Button(right, text="Review warnings →", command=lambda:self.show_page("Warnings"),
                  bg=WHITE, fg=ACCENT, relief="flat", cursor="hand2",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12)

    def page_records(self):
        self.heading("Volunteer records", "Browse, update approval status, and manage every saved activity.")
        bar = tk.Frame(self.content, bg=APP_BG)
        bar.pack(fill="x", pady=(0, 12))
        self.action_button(bar, "＋ Add volunteer", lambda:self.show_page("Add Volunteer")).pack(side="left")
        self.action_button(bar, "Update selected status", self.update_selected_status, False).pack(side="left", padx=8)
        self.action_button(bar, "Delete selected", self.delete_selected, False).pack(side="left")
        self.records_tree = self._table(self.content,
            ("id","date","name","activity","category","hours","status"),
            ("RECORD ID","DATE","VOLUNTEER","ACTIVITY","CATEGORY","HOURS","STATUS"),
            (85,100,150,190,140,70,100), height=15)
        self._populate(self.records_tree, sorted(self.records, key=lambda r:r.service_date, reverse=True))

    def page_add(self):
        self.heading("Add volunteer activity", "Enter the activity details. Service hours are calculated automatically.")
        panel = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        form = tk.Frame(panel, bg=WHITE)
        form.pack(anchor="nw", padx=28, pady=22)
        self.form_vars = {}
        fields = [
            ("volunteer_name","Volunteer full name","entry"),
            ("activity","Activity performed","entry"),
            ("category","Service category","category"),
            ("service_date","Service date (YYYY-MM-DD)","entry"),
            ("start_time","Start time (HH:MM)","entry"),
            ("end_time","End time (HH:MM)","entry"),
            ("status","Approval status","status"),
            ("supervisor","Supervisor (optional)","entry"),
            ("deadline","Approval deadline (optional)","entry"),
        ]
        for idx, (key, label, kind) in enumerate(fields):
            row, col = divmod(idx, 2)
            cell = tk.Frame(form, bg=WHITE)
            cell.grid(row=row, column=col, sticky="ew", padx=(0, 35 if col == 0 else 0), pady=8)
            tk.Label(cell, text=label, bg=WHITE, fg="#506174",
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 5))
            var = tk.StringVar()
            self.form_vars[key] = var
            if kind == "category":
                widget = ttk.Combobox(cell, textvariable=var, values=CATEGORIES, state="readonly", width=38)
                widget.set(CATEGORIES[0])
            elif kind == "status":
                widget = ttk.Combobox(cell, textvariable=var, values=sorted(VALID_STATUSES), state="readonly", width=38)
                widget.set("Pending")
            else:
                widget = ttk.Entry(cell, textvariable=var, width=41)
                if key == "service_date": var.set(date.today().isoformat())
                if key == "start_time": var.set("09:00")
                if key == "end_time": var.set("11:00")
                if key == "status": var.set("Pending")
            widget.pack(anchor="w", ipady=3)
            if key in ("start_time", "end_time"):
                widget.bind("<FocusOut>", lambda _e:self.preview_hours())
        note_cell = tk.Frame(form, bg=WHITE)
        note_cell.grid(row=5, column=0, sticky="ew", pady=8)
        tk.Label(note_cell, text="Notes (optional)", bg=WHITE, fg="#506174",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 5))
        self.notes_text = tk.Text(note_cell, width=43, height=3, font=("Segoe UI", 9),
                                  relief="solid", bd=1, highlightthickness=0)
        self.notes_text.pack(anchor="w")
        self.hours_preview = tk.Label(form, text="Calculated duration: —", bg=WHITE,
                                      fg=ACCENT, font=("Segoe UI", 10, "bold"))
        self.hours_preview.grid(row=5, column=1, sticky="w", padx=10)
        actions = tk.Frame(panel, bg=WHITE)
        actions.pack(anchor="w", padx=28, pady=(5, 20))
        self.action_button(actions, "Save volunteer record", self.save_new_record).pack(side="left")
        self.action_button(actions, "Clear form", self.clear_form, False).pack(side="left", padx=9)

    def preview_hours(self):
        try:
            from campus_catalyst.validators import calculate_hours
            h = calculate_hours(self.form_vars["start_time"].get(), self.form_vars["end_time"].get())
            self.hours_preview.config(text=f"Calculated duration: {h:.2f} hours")
        except ValueError:
            self.hours_preview.config(text="Calculated duration: check start/end times")

    def clear_form(self):
        for key, var in self.form_vars.items():
            var.set("")
        self.form_vars["category"].set(CATEGORIES[0])
        self.form_vars["status"].set("Pending")
        self.form_vars["service_date"].set(date.today().isoformat())
        self.form_vars["start_time"].set("09:00")
        self.form_vars["end_time"].set("11:00")
        self.notes_text.delete("1.0", "end")
        self.hours_preview.config(text="Calculated duration: —")

    def save_new_record(self):
        data = {key:var.get() for key,var in self.form_vars.items()}
        data["notes"] = self.notes_text.get("1.0", "end").strip()
        try:
            record = validate_record_payload(data)
            self.records.append(record)
            self.storage.save(self.records)
        except (ValueError, StorageError) as exc:
            messagebox.showerror("Please check the entry", str(exc))
            return
        messagebox.showinfo("Record saved", f"Volunteer activity saved successfully.\n\nRecord ID: {record.record_id}\nCalculated hours: {record.hours:.2f}")
        self.show_page("Dashboard")

    def page_search(self):
        self.heading("Search & filter", "Find records by volunteer, activity, supervisor, record ID or notes.")
        filters = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        filters.pack(fill="x", pady=(0, 13))
        tk.Label(filters, text="Keyword", bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0,column=0,sticky="w",padx=12,pady=(12,3))
        self.search_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search_var, width=35).grid(row=1,column=0,padx=12,pady=(0,12),sticky="w")
        tk.Label(filters, text="Category", bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0,column=1,sticky="w",padx=12,pady=(12,3))
        self.category_var = tk.StringVar(value="All categories")
        ttk.Combobox(filters, textvariable=self.category_var, values=["All categories"]+CATEGORIES,
                     state="readonly", width=23).grid(row=1,column=1,padx=12,pady=(0,12),sticky="w")
        tk.Label(filters, text="Status", bg=WHITE, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0,column=2,sticky="w",padx=12,pady=(12,3))
        self.status_var = tk.StringVar(value="All statuses")
        ttk.Combobox(filters, textvariable=self.status_var, values=["All statuses"]+sorted(VALID_STATUSES),
                     state="readonly", width=18).grid(row=1,column=2,padx=12,pady=(0,12),sticky="w")
        self.action_button(filters, "Apply filters", self.apply_search).grid(row=1,column=3,padx=12,pady=(0,12))
        self.action_button(filters, "Reset", lambda:self.show_page("Search & Filter"), False).grid(row=1,column=4,padx=(0,12),pady=(0,12))
        self.search_tree = self._table(self.content, ("id","date","name","activity","category","hours","status"),
            ("RECORD ID","DATE","VOLUNTEER","ACTIVITY","CATEGORY","HOURS","STATUS"),
            (85,100,150,190,140,70,100), height=13)
        self._populate(self.search_tree, search_records(self.records))

    def apply_search(self):
        category = self.category_var.get()
        status = self.status_var.get()
        result = search_records(self.records, self.search_var.get(),
                                "All" if category == "All categories" else category,
                                "All" if status == "All statuses" else status)
        self._populate(self.search_tree, result)

    def page_analytics(self):
        self.heading("Analytics & insights", "Understand verified service contributions across your campus.")
        s = build_summary(self.records)
        stats = tk.Frame(self.content, bg=APP_BG)
        stats.pack(fill="x", pady=(0, 16))
        for i, (label, value, detail, color) in enumerate([
            ("Approved entries", str(s["approved_count"]), "Verified activities", GREEN),
            ("Pending entries", str(s["pending_count"]), "Awaiting review", ORANGE),
            ("Rejected entries", str(s["rejected_count"]), "Not included in totals", RED),
            ("Average duration", f"{s['average_hours']:.2f} hrs", "Per approved record", BLUE),
        ]):
            self.card(stats,label,value,detail,color).grid(row=0,column=i,sticky="nsew",padx=(0 if i==0 else 8,0))
            stats.grid_columnconfigure(i,weight=1,uniform="analytics")
        panel = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="Approved hours by category", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(15, 4))
        canvas = tk.Canvas(panel, bg=WHITE, height=265, highlightthickness=0)
        canvas.pack(fill="x", padx=15, pady=8)
        totals = s["category_totals"]
        if not totals:
            canvas.create_text(30, 40, anchor="nw", text="No approved service hours available yet.", fill=MUTED, font=("Segoe UI",10))
        else:
            max_value = max(totals.values()) or 1
            palette = ["#1A9A91","#3867B7","#E1A13C","#8A6CCB","#D46C73","#4C9B77","#5C7898"]
            y = 25
            for idx, (category, hours) in enumerate(totals.items()):
                canvas.create_text(8,y+10,anchor="w",text=category,fill=TEXT,font=("Segoe UI",9))
                x0, x1 = 190, 700
                width = (hours/max_value)*420
                canvas.create_rectangle(x0,y,x0+width,y+21,fill=palette[idx%len(palette)],outline="")
                canvas.create_text(x0+width+9,y+10,anchor="w",text=f"{hours:.2f} hrs",fill=MUTED,font=("Segoe UI",9,"bold"))
                y += 36
        tk.Label(panel, text="Top volunteers (approved hours)", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(5, 6))
        top = "     •     ".join(f"{name}: {hours:.2f} hrs" for name,hours in s["top_volunteers"]) or "No approved volunteer hours yet."
        tk.Label(panel, text=top, bg=WHITE, fg=MUTED, font=("Segoe UI", 9),
                 wraplength=900, justify="left").pack(anchor="w", padx=18, pady=(0,15))

    def page_import(self):
        self.heading("Bulk dataset import", "Import legacy volunteer records from CSV with automatic row-by-row validation.")
        panel = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="x", pady=(0,15))
        tk.Label(panel, text="Import volunteer records", bg=WHITE, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=22, pady=(20,5))
        tk.Label(panel, text="Select a CSV file. Valid rows will be imported; invalid rows will be skipped and listed in the log.",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=22)
        row = tk.Frame(panel, bg=WHITE)
        row.pack(fill="x", padx=22, pady=18)
        self.import_path = tk.StringVar(value="data/volunteers.csv")
        ttk.Entry(row, textvariable=self.import_path, width=72).pack(side="left", ipady=4)
        self.action_button(row, "Browse…", self.browse_csv, False).pack(side="left", padx=8)
        self.action_button(row, "Import CSV", self.run_import).pack(side="left")
        self.import_log = tk.Text(self.content, height=13, bg="#17283C", fg="#DCE8F1",
                                  insertbackground=WHITE, relief="flat", padx=14, pady=12,
                                  font=("Consolas", 9), wrap="word")
        self.import_log.pack(fill="both", expand=True)
        self.import_log.insert("end", "IMPORT LOG\n" + "─"*58 + "\nChoose a CSV file to begin.\n")
        self.import_log.config(state="disabled")

    def browse_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if path: self.import_path.set(path)

    def run_import(self):
        try:
            imported, errors = self.storage.import_csv(self.import_path.get())
            added, duplicates = merge_records(self.records, imported)
            self.storage.save(self.records)
        except (StorageError, OSError) as exc:
            messagebox.showerror("Import failed", str(exc)); return
        self.import_log.config(state="normal")
        self.import_log.delete("1.0","end")
        self.import_log.insert("end", f"IMPORT COMPLETE\n{'─'*58}\nNew valid rows imported: {len(added)}\nDuplicate rows skipped: {duplicates}\nInvalid rows skipped: {len(errors)}\n\n")
        for err in errors:
            self.import_log.insert("end", "• " + err + "\n")
        if not errors: self.import_log.insert("end","No row validation errors detected.\n")
        self.import_log.config(state="disabled")
        messagebox.showinfo("Import complete", f"{len(added)} new valid record(s) imported.\n{duplicates} duplicate row(s) skipped.\n{len(errors)} invalid row(s) skipped.")

    def page_export(self):
        self.heading("Export reports", "Generate structured reports for review, audit and external sharing.")
        exports = [
            ("MARKDOWN SUMMARY", "Volunteer totals, category breakdown and record table.", "volunteer_summary.md"),
            ("PLAIN-TEXT AUDIT", "Readable audit log of saved volunteer records.", "volunteer_audit.txt"),
            ("CSV DATA EXPORT", "Structured records for spreadsheets and external analysis.", "volunteer_records.csv"),
        ]
        for title, desc, filename in exports:
            panel = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            panel.pack(fill="x", pady=7)
            info = tk.Frame(panel, bg=WHITE)
            info.pack(side="left", fill="both", expand=True, padx=18, pady=15)
            tk.Label(info, text=title, bg=WHITE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=desc, bg=WHITE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4,0))
            self.action_button(panel, "Export file", lambda f=filename:self.export_one(f)).pack(side="right", padx=18, pady=18)
        self.action_button(self.content, "Export all three reports", self.export_all).pack(anchor="w", pady=12)

    def export_one(self, filename):
        if not self.records:
            messagebox.showwarning("No records","Add or import records before exporting."); return
        ext = Path(filename).suffix
        target = filedialog.asksaveasfilename(initialfile=filename, defaultextension=ext,
                    filetypes=[("Markdown","*.md"),("Text","*.txt"),("CSV","*.csv")])
        if not target: return
        try:
            if filename.endswith(".md"): export_markdown(self.records,target)
            elif filename.endswith(".txt"): export_text(self.records,target)
            else: self.storage.export_csv(self.records,target)
        except OSError as exc:
            messagebox.showerror("Export failed",str(exc)); return
        messagebox.showinfo("Export complete",f"Report saved to:\n{target}")

    def export_all(self):
        if not self.records:
            messagebox.showwarning("No records","Add or import records before exporting."); return
        folder = filedialog.askdirectory()
        if not folder: return
        try:
            export_markdown(self.records,Path(folder)/"volunteer_summary.md")
            export_text(self.records,Path(folder)/"volunteer_audit.txt")
            self.storage.export_csv(self.records,Path(folder)/"volunteer_records.csv")
        except OSError as exc:
            messagebox.showerror("Export failed",str(exc)); return
        messagebox.showinfo("Export complete",f"All three reports saved in:\n{folder}")

    def page_warnings(self):
        self.heading("Warnings & data quality", "Review overdue approval deadlines and unusually long volunteer sessions.")
        warnings = get_warnings(self.records)
        summary = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        summary.pack(fill="x", pady=(0,13))
        tk.Label(summary, text=f"{len(warnings)} item(s) need attention", bg=WHITE,
                 fg=ORANGE if warnings else GREEN, font=("Segoe UI", 13, "bold")).pack(anchor="w",padx=18,pady=14)
        panel = tk.Frame(self.content, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        text = tk.Text(panel, bg=WHITE, fg=TEXT, relief="flat", padx=18,pady=15,
                       font=("Segoe UI",10),wrap="word")
        text.pack(fill="both",expand=True)
        if warnings:
            for warning in warnings:
                text.insert("end","⚑  "+warning+"\n\n")
        else:
            text.insert("end","✓  No overdue approvals or unusually long sessions were detected.\n\nYour current records have passed the configured warning checks.")
        text.config(state="disabled")

    def update_selected_status(self):
        selected = self.records_tree.selection()
        if not selected:
            messagebox.showwarning("Select a record","Choose a volunteer record first."); return
        record = next((r for r in self.records if r.record_id == selected[0]),None)
        if not record: return
        dialog = tk.Toplevel(self)
        dialog.title("Update approval status")
        dialog.configure(bg=WHITE); dialog.resizable(False,False)
        dialog.transient(self); dialog.grab_set()
        tk.Label(dialog,text=f"{record.volunteer_name}\n{record.activity}",bg=WHITE,fg=TEXT,
                 font=("Segoe UI",11,"bold")).pack(padx=25,pady=(20,10))
        value=tk.StringVar(value=record.status)
        ttk.Combobox(dialog,textvariable=value,values=sorted(VALID_STATUSES),state="readonly").pack(padx=25,pady=8)
        def save():
            record.status=value.get()
            try: self.storage.save(self.records)
            except StorageError as exc: messagebox.showerror("Save failed",str(exc)); return
            dialog.destroy(); self.show_page("Volunteer Records")
        self.action_button(dialog,"Save status",save).pack(padx=25,pady=18)

    def delete_selected(self):
        selected = self.records_tree.selection()
        if not selected:
            messagebox.showwarning("Select a record","Choose a volunteer record first."); return
        rid=selected[0]
        record=next((r for r in self.records if r.record_id==rid),None)
        if not record: return
        if messagebox.askyesno("Confirm deletion",f"Delete {record.volunteer_name}'s record {rid}?"):
            self.records.remove(record)
            try: self.storage.save(self.records)
            except StorageError as exc: messagebox.showerror("Save failed",str(exc)); return
            self.show_page("Volunteer Records")

    def on_close(self):
        try:
            self.storage.save(self.records)
        except StorageError as exc:
            if not messagebox.askyesno("Save problem",f"{exc}\n\nExit anyway?"): return
        self.destroy()

def run_gui():
    app = CampusCatalystApp()
    app.mainloop()

if __name__ == "__main__":
    run_gui()
