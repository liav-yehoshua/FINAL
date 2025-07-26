import sys
import os
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, scrolledtext
import requests
import io
from PIL import Image, ImageTk
from google.cloud import vision
from difflib import SequenceMatcher
from image_text_viewer import run_google_vision_ocr

# ====== CONFIG ======
API_KEY = "AIzaSyASCAy9Rtvcd-V_1xBHuurvsJGHi0KB4QQ"  # Gemini API Key
GOOGLE_CREDENTIALS = os.path.join(os.getcwd(), 'google-credentials.json')

# ====== PARAMETERS & WEIGHTS ======
PARAMETERS = [
    ("Correctness", 0.4),
    ("Syntax", 0.15),
    ("Code Structure", 0.15),
    ("Efficiency", 0.15),
    ("Edge Cases", 0.15)
]

# ====== OCR FUNCTION ======
def get_ocr_text(image_path):
    return run_google_vision_ocr(image_path)

# ====== GEMINI FUNCTION ======
def get_gemini_answer(question_text):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY
    }
    data = {
        "contents": [{"parts": [{"text": question_text}]}]
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        try:
            return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            return "[שגיאה בפענוח תשובת Gemini]"
    else:
        return f"[שגיאה בחיבור ל-Gemini: {resp.status_code} {resp.text}]"

# ====== GRADING FUNCTION ======
def grade_student_answer(student_code, gemini_code):
    # Correctness: דמיון כללי (SequenceMatcher)
    similarity = SequenceMatcher(None, student_code, gemini_code).ratio()
    correctness = int(similarity * 100)
    # Syntax: בדיקת מילים נפוצות של שגיאות (פשוט)
    syntax = 100 if ("error" not in student_code.lower() and "syntax" not in student_code.lower()) else 60
    # Code Structure: בדיקת הזחות, שמות משתנים (פשוט)
    structure = 100 if ("def " in student_code or "function" in student_code) else 70
    # Efficiency: בדיקת שימוש בלולאות/מבנים יעילים (פשוט)
    efficiency = 100 if ("for" in student_code or "while" in student_code) else 70
    # Edge Cases: בדיקת טיפול ב-if/else/try (פשוט)
    edge_cases = 100 if ("if" in student_code or "try" in student_code) else 60
    # משוקלל
    scores = [correctness, syntax, structure, efficiency, edge_cases]
    weighted = sum([score * weight for score, (_, weight) in zip(scores, PARAMETERS)])
    return {
        "Correctness": correctness,
        "Syntax": syntax,
        "Code Structure": structure,
        "Efficiency": efficiency,
        "Edge Cases": edge_cases,
        "Final Score": int(weighted)
    }

# ====== UI ======
class ExamGraderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Exam Grader - Gemini")
        self.root.configure(bg="#f7f7fa")
        self.question_text = ""
        self.gemini_answer = ""
        self.students = []  # List of (name, image_path, ocr_text, scores)
        self.question_score = 10  # ברירת מחדל
        self.build_ui()

    def build_ui(self):
        self.frame = tk.Frame(self.root, bg="#f7f7fa")
        self.frame.pack(padx=30, pady=30)
        self.step_label = tk.Label(self.frame, text="שלב 1: הזן או העלה שאלה", font=("Arial", 14, "bold"), bg="#f7f7fa", fg="#222")
        self.step_label.pack(pady=(0, 10))
        self.btn_text = tk.Button(self.frame, text="הקלד שאלה (טקסט)", command=self.enter_question_text, font=("Arial", 12), bg="#e0e7ff", fg="#222", relief="raised")
        self.btn_text.pack(pady=5, fill='x')
        self.btn_img = tk.Button(self.frame, text="העלה תמונה של שאלה", command=self.upload_question_image, font=("Arial", 12), bg="#e0e7ff", fg="#222", relief="raised")
        self.btn_img.pack(pady=5, fill='x')
        # ניקוד שאלה
        score_frame = tk.Frame(self.frame, bg="#f7f7fa")
        score_frame.pack(pady=(15, 5))
        tk.Label(score_frame, text="ניקוד השאלה במבחן:", font=("Arial", 12), bg="#f7f7fa", fg="#222").pack(side='left')
        self.score_entry = tk.Entry(score_frame, width=5, font=("Arial", 12))
        self.score_entry.insert(0, str(self.question_score))
        self.score_entry.pack(side='left', padx=5)

    def enter_question_text(self):
        text = simpledialog.askstring("הקלד שאלה", "הזן את נוסח השאלה:")
        if text:
            self.question_text = text.strip()
            self.get_score_and_next()

    def upload_question_image(self):
        path = filedialog.askopenfilename(title='בחר תמונה של שאלה', filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif;*.webp')])
        if path:
            text = get_ocr_text(path)
            if not text:
                messagebox.showerror("שגיאה", "לא זוהה טקסט בתמונה.")
                return
            self.question_text = text
            self.get_score_and_next()

    def get_score_and_next(self):
        try:
            score = int(self.score_entry.get())
            if score <= 0:
                raise ValueError
            self.question_score = score
        except Exception:
            messagebox.showerror("שגיאה", "ניקוד השאלה חייב להיות מספר חיובי.")
            return
        self.next_step_students()

    def next_step_students(self):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.frame.configure(bg="#f7f7fa")
        self.step_label = tk.Label(self.frame, text="שלב 2: העלה תשובות סטודנטים (תמונות)", font=("Arial", 14, "bold"), bg="#f7f7fa", fg="#222")
        self.step_label.pack(pady=(0, 10))
        self.btn_add = tk.Button(self.frame, text="הוסף תשובת סטודנט", command=self.add_student, font=("Arial", 12), bg="#e0e7ff", fg="#222", relief="raised")
        self.btn_add.pack(pady=5, fill='x')
        self.students_listbox = tk.Listbox(self.frame, width=50, font=("Arial", 11))
        self.students_listbox.pack(pady=5)
        self.btn_run = tk.Button(self.frame, text="הרץ בדיקה", command=self.run_grading, font=("Arial", 12, "bold"), bg="#4f46e5", fg="#fff", relief="raised")
        self.btn_run.pack(pady=15, fill='x')

    def add_student(self):
        name = simpledialog.askstring("שם סטודנט", "הזן שם/מזהה לסטודנט:")
        if not name:
            return
        path = filedialog.askopenfilename(title='בחר תמונה של תשובת סטודנט', filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif;*.webp')])
        if not path:
            return
        self.students.append((name, path, None, None))
        self.students_listbox.insert(tk.END, f"{name} - {os.path.basename(path)}")

    def run_grading(self):
        if not self.students:
            messagebox.showerror("שגיאה", "לא הוספת אף סטודנט.")
            return
        self.step_label.config(text="מריץ Gemini... זה עשוי לקחת מספר שניות...")
        self.root.update()
        self.gemini_answer = get_gemini_answer(self.question_text)
        results = []
        for i, (name, path, _, _) in enumerate(self.students):
            ocr_text = get_ocr_text(path)
            scores = grade_student_answer(ocr_text, self.gemini_answer)
            # חישוב ניקוד סופי
            final_score = scores["Final Score"]
            exam_points = int(round((final_score / 100) * self.question_score))
            scores["Exam Points"] = exam_points
            results.append((name, ocr_text, scores))
        self.show_results(results)

    def show_results(self, results):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.frame.configure(bg="#f7f7fa")
        self.step_label = tk.Label(self.frame, text="תוצאות", font=("Arial", 16, "bold"), bg="#f7f7fa", fg="#222")
        self.step_label.pack(pady=(0, 10))
        # הצג שאלה
        qf = tk.Frame(self.frame, bg="#f7f7fa")
        qf.pack(pady=5, fill='x')
        tk.Label(qf, text="שאלה:", font=("Arial", 12, "bold"), bg="#f7f7fa", fg="#222").pack(anchor='w')
        tk.Message(qf, text=str(self.question_text or ""), width=700, font=("Arial", 11), bg="#f7f7fa", fg="#222").pack(anchor='w')

        def show_image_window(image_path, student_name):
            win = tk.Toplevel(self.root)
            win.title(f"תמונה מקורית - {student_name}")
            img = Image.open(image_path)
            img.thumbnail((700, 900))
            img_tk = ImageTk.PhotoImage(img, master=win)
            lbl = tk.Label(win, image=img_tk)
            lbl.image = img_tk
            lbl.pack(padx=10, pady=10)

        if len(results) == 1:
            name, ocr_text, scores = results[0]
            compare_frame = tk.Frame(self.frame, bg="#f7f7fa")
            compare_frame.pack(pady=10, fill='x')
            # Gemini
            gemini_frame = tk.Frame(compare_frame, bg="#fff7e6", bd=2, relief="groove", highlightbackground="#ff9800", highlightthickness=2)
            gemini_frame.pack(side='left', padx=10, fill='both', expand=True)
            tk.Label(gemini_frame, text="תשובת Gemini", font=("Arial", 12, "bold"), bg="#fff7e6", fg="#ff9800").pack(anchor='n', padx=8, pady=(4,0))
            gemini_text = scrolledtext.ScrolledText(gemini_frame, width=45, height=10, font=("Arial", 11), bg="#fff7e6", fg="#d2691e", wrap='word')
            gemini_text.insert(tk.END, str(self.gemini_answer or ""))
            gemini_text.config(state='disabled')
            gemini_text.pack(anchor='n', padx=8, pady=(0,8), fill='both', expand=True)
            # סטודנט
            student_frame = tk.Frame(compare_frame, bg="#e0f7fa", bd=2, relief="groove", highlightbackground="#4f46e5", highlightthickness=2)
            student_frame.pack(side='left', padx=10, fill='both', expand=True)
            top_row = tk.Frame(student_frame, bg="#e0f7fa")
            top_row.pack(anchor='n', fill='x')
            tk.Label(top_row, text=f"תשובת {name}", font=("Arial", 12, "bold"), bg="#e0f7fa", fg="#4f46e5").pack(side='left', padx=8, pady=(4,0))
            btn_img = tk.Button(top_row, text="הצג תמונה", font=("Arial", 10), bg="#e0e7ff", fg="#222", command=lambda: show_image_window(self.students[0][1], name))
            btn_img.pack(side='left', padx=8, pady=(4,0))
            student_text = scrolledtext.ScrolledText(student_frame, width=45, height=10, font=("Arial", 11), bg="#e0f7fa", fg="#222", wrap='word')
            student_text.insert(tk.END, ocr_text)
            student_text.config(state='disabled')
            student_text.pack(anchor='n', padx=8, pady=(0,8), fill='both', expand=True)
            # ציונים
            table = tk.Frame(student_frame, bg="#e0f7fa")
            table.pack(pady=5)
            for i, (param, _) in enumerate(PARAMETERS):
                tk.Label(table, text=param, borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=i)
            tk.Label(table, text="Final Score", borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS))
            tk.Label(table, text="Exam Points", borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS)+1)
            for i, (param, _) in enumerate(PARAMETERS):
                tk.Label(table, text=str(scores[param]), borderwidth=1, relief="solid", width=15, font=("Arial", 10), bg="#fff", fg="#222").grid(row=1, column=i)
            tk.Label(table, text=str(scores["Final Score"]), borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#fff", fg="#000").grid(row=1, column=len(PARAMETERS))
            tk.Label(table, text=str(scores["Exam Points"]), borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#fff", fg="#4f46e5").grid(row=1, column=len(PARAMETERS)+1)
        else:
            # תשובת Gemini בראש
            gemini_frame = tk.Frame(self.frame, bg="#fff7e6", bd=2, relief="groove", highlightbackground="#ff9800", highlightthickness=2)
            gemini_frame.pack(pady=10, fill='x')
            tk.Label(gemini_frame, text="תשובת Gemini", font=("Arial", 12, "bold"), bg="#fff7e6", fg="#ff9800").pack(anchor='w', padx=8, pady=(4,0))
            gemini_text = scrolledtext.ScrolledText(gemini_frame, width=90, height=8, font=("Arial", 11), bg="#fff7e6", fg="#d2691e", wrap='word')
            gemini_text.insert(tk.END, str(self.gemini_answer or ""))
            gemini_text.config(state='disabled')
            gemini_text.pack(anchor='w', padx=8, pady=(0,8), fill='both', expand=True)
            # לכל סטודנט
            for idx, (name, ocr_text, scores) in enumerate(results):
                sf = tk.LabelFrame(self.frame, text=f"סטודנט: {name}", padx=10, pady=10, font=("Arial", 12, "bold"), bg="#f7f7fa", fg="#222", relief="ridge")
                sf.pack(fill='x', pady=10)
                top_row = tk.Frame(sf, bg="#f7f7fa")
                top_row.pack(anchor='w', fill='x')
                tk.Label(top_row, text="תשובת סטודנט:", font=("Arial", 11, "bold"), bg="#f7f7fa", fg="#222").pack(side='left')
                btn_img = tk.Button(top_row, text="הצג תמונה", font=("Arial", 10), bg="#e0e7ff", fg="#222", command=lambda i=idx: show_image_window(self.students[i][1], name))
                btn_img.pack(side='left', padx=8)
                st = scrolledtext.ScrolledText(sf, width=90, height=6, font=("Consolas", 10), bg="#fff", fg="#222", wrap='word')
                st.insert(tk.END, ocr_text)
                st.config(state='disabled')
                st.pack(pady=(0,8), fill='both', expand=True)
                # טבלת ציונים
                table = tk.Frame(sf, bg="#f7f7fa")
                table.pack(pady=5)
                for i, (param, _) in enumerate(PARAMETERS):
                    tk.Label(table, text=param, borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=i)
                tk.Label(table, text="Final Score", borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS))
                tk.Label(table, text="Exam Points", borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS)+1)
                for i, (param, _) in enumerate(PARAMETERS):
                    tk.Label(table, text=str(scores[param]), borderwidth=1, relief="solid", width=15, font=("Arial", 10), bg="#fff", fg="#222").grid(row=1, column=i)
                tk.Label(table, text=str(scores["Final Score"]), borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#fff", fg="#000").grid(row=1, column=len(PARAMETERS))
                tk.Label(table, text=str(scores["Exam Points"]), borderwidth=1, relief="solid", width=15, font=("Arial", 10, "bold"), bg="#fff", fg="#4f46e5").grid(row=1, column=len(PARAMETERS)+1)
        tk.Button(self.frame, text="סיים", command=self.root.destroy, font=("Arial", 12), bg="#e0e7ff", fg="#222", relief="raised").pack(pady=15, fill='x')

if __name__ == "__main__":
    root = tk.Tk()
    app = ExamGraderApp(root)
    root.mainloop() 