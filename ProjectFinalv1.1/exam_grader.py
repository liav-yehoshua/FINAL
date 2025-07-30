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
import re
import random
import string
import builtins
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ====== CONFIG ======
API_KEY = os.getenv("GEMINI_API_KEY")  # Gemini API Key - must be set in .env file
GOOGLE_CREDENTIALS = os.path.join(os.getcwd(), os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json"))

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
    result = run_google_vision_ocr(image_path, preprocess=True)
    # Handle both old format (string) and new format (tuple)
    if isinstance(result, tuple):
        return result[0]  # Return only the text part
    return result

# ====== GEMINI FUNCTION ======
def get_gemini_answer(question_text, language=None):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY
    }
    if language:
        prompt = f"{question_text}\n\nכתוב את התשובה בקוד {language}."
    else:
        prompt = question_text
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        try:
            return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception:
            return "[שגיאה בפענוח תשובת Gemini]"
    else:
        return f"[שגיאה בחיבור ל-Gemini: {resp.status_code} {resp.text}]"

def repair_ocr_code(code):
    # Fix common OCR mistakes
    code = code.replace('del ', 'def ')
    code = re.sub(r'del([a-zA-Z_])', r'def \1', code)
    code = code.replace('—', '-')
    code = code.replace('“', '"').replace('”', '"').replace("’", "'")
    # Add colon to function definition if missing
    code = re.sub(r'(def .+\))\s*\n', r'\1:\n', code)
    # Remove unwanted characters
    code = re.sub(r'[\u200e\u200f]', '', code)
    return code

def extract_signature(code):
    # Try to find the first function definition
    match = re.search(r'def\s+(\w+)\s*\(([^)]*)\)', code)
    if not match:
        return None, []
    name = match.group(1)
    params = [p.strip().split('=')[0].strip() for p in match.group(2).split(',') if p.strip()]
    return name, params

def generate_sample_inputs(params, n=3):
    # Try to guess types by parameter names, fallback to int/string
    samples = []
    for _ in range(n):
        args = []
        for p in params:
            if 'str' in p or 'name' in p or 'text' in p:
                args.append(''.join(random.choices(string.ascii_letters, k=5)))
            elif 'list' in p:
                args.append([random.randint(1, 10) for _ in range(3)])
            elif 'dict' in p:
                args.append({str(i): i for i in range(3)})
            else:
                args.append(random.randint(1, 10))
        samples.append(tuple(args))
    return samples

def safe_run(code, func_name, args):
    # Run code in restricted namespace
    local_ns = {}
    try:
        exec(code, {'__builtins__': {k: getattr(builtins, k) for k in ('abs','min','max','sum','len','range','str','int','float','list','dict')}}, local_ns)
        func = local_ns.get(func_name)
        if not callable(func):
            return Exception('Function not found')
        return func(*args)
    except Exception as e:
        return e

def strip_boilerplate(code, language=None):
    # Remove import, using, class, and public class lines
    lines = code.splitlines()
    new_lines = []
    for line in lines:
        l = line.strip()
        if l.startswith('import ') or l.startswith('using ') or l.startswith('public class') or l.startswith('class '):
            continue
        # For Java/C#: skip main method wrapper
        if language in ("Java", "C#") and (l.startswith('public static void main') or l.startswith('static void main')):
            continue
        new_lines.append(line)
    return '\n'.join(new_lines)

# ====== TEST FUNCTION ======
def test_grading():
    """Test the grading function with sample data"""
    test_student_code = """
def add_numbers(a, b):
    return a + b
"""
    test_gemini_code = """
def add_numbers(a, b):
    return a + b
"""
    print("Testing grading function...")
    result = grade_student_answer(test_student_code, test_gemini_code, "Python")
    print(f"Test result: {result}")
    return result

# ====== GRADING FUNCTION ======
def grade_student_answer(student_code, gemini_code, language=None):
    # Use Gemini to evaluate the student's code
    language_info = f"PROGRAMMING LANGUAGE: {language}" if language else "PROGRAMMING LANGUAGE: Not specified"
    
    evaluation_prompt = f"""
    You are an expert programming instructor evaluating handwritten code that may contain OCR errors.

    {language_info}

    CORRECT SOLUTION:
    {gemini_code}

    STUDENT'S CODE (handwritten, may contain OCR errors):
    {student_code}

    CRITICAL GRADING GUIDELINES:
    1. The student code is scanned from handwritten text and may contain OCR errors such as:
       - Missing parentheses, brackets, or semicolons
       - Typos (e.g., "hum" instead of "num", "functon" instead of "function")
       - Misplaced punctuation or spacing issues
       - Small syntax mistakes due to handwriting recognition
    
    2. DO NOT deduct points for these OCR-related errors. Focus on the INTENT and LOGIC STRUCTURE.
    
    3. Ignore missing class/method declarations (public class, Main method) especially in C#/Java, as students often omit them when writing by hand.
    
    4. Grade based on whether the student's logic matches the required algorithm steps:
       - Reading input data correctly
       - Proper looping structures
       - Correct mathematical operations
       - Appropriate variable usage
       - Logical flow of the program
    
    5. If the student's logic is correct but has OCR/syntax errors, give HIGH scores (85-100).
    6. Only give low scores if the fundamental logic is wrong or missing key algorithm steps.

    Please provide:
    1. A correctness score (0-100) based on logical correctness, not syntax perfection
    2. A brief explanation of any logical issues found (ignore OCR errors)
    3. A corrected version of the student's code if needed

    Respond in this exact format:
    SCORE: [number]
    EXPLANATION: [text]
    CORRECTED: [corrected code or "NO CORRECTION NEEDED"]
    """
    
    try:
        evaluation_response = get_gemini_answer(evaluation_prompt)
        print(f"DEBUG: Gemini evaluation response: {evaluation_response}")
        
        # Parse the response - try multiple patterns
        score_match = re.search(r'SCORE:\s*(\d+)', evaluation_response, re.IGNORECASE)
        if not score_match:
            score_match = re.search(r'(\d+)\s*\/\s*100', evaluation_response)
        if not score_match:
            score_match = re.search(r'score[:\s]*(\d+)', evaluation_response, re.IGNORECASE)
        
        if score_match:
            correctness = int(score_match.group(1))
            print(f"DEBUG: Parsed correctness score: {correctness}")
        else:
            # Fallback to similarity if parsing fails
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, student_code, gemini_code).ratio()
            correctness = int(similarity * 100)
            print(f"DEBUG: Could not parse Gemini score, using similarity: {correctness}%")
            print(f"DEBUG: Raw response was: {evaluation_response}")
            
            # Be more lenient with similarity scoring for handwritten code
            if similarity > 0.6:  # Lowered threshold for OCR errors
                correctness = min(95, int(similarity * 100) + 25)  # Higher boost
                print(f"DEBUG: High similarity detected, boosting score to: {correctness}")
            elif similarity > 0.4:  # Medium similarity - likely correct with OCR errors
                correctness = min(85, int(similarity * 100) + 30)
                print(f"DEBUG: Medium similarity detected, boosting score to: {correctness}")
    except Exception as e:
        print(f"DEBUG: Error in Gemini evaluation: {e}")
        # Fallback to similarity
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, student_code, gemini_code).ratio()
        correctness = int(similarity * 100)
        print(f"DEBUG: Fallback to similarity: {correctness}%")
        
        # Additional check: be more lenient for handwritten code with OCR errors
        if similarity > 0.7:  # Lowered threshold
            correctness = 90
            print(f"DEBUG: Very high similarity, assuming correct: {correctness}")
        elif similarity > 0.5:  # Medium similarity - likely correct with OCR errors
            correctness = 80
            print(f"DEBUG: Medium similarity, likely correct with OCR errors: {correctness}")
    # Use Gemini for comprehensive evaluation
    comprehensive_prompt = f"""
    You are an expert programming instructor evaluating handwritten code that may contain OCR errors.

    PROGRAMMING LANGUAGE: {language if language else 'Not specified'}

    STUDENT'S CODE (handwritten, may contain OCR errors):
    {student_code}

    IMPORTANT: This is handwritten code that may have OCR errors. Focus on logical intent, not syntax perfection.

    Please evaluate each aspect and respond in this exact format:

    SYNTAX: [0-100] - Evaluate logical syntax understanding, ignore OCR typos. High scores for correct logic even with OCR errors.
    STRUCTURE: [0-100] - Evaluate logical code organization and flow, ignore missing class declarations or boilerplate.
    EFFICIENCY: [0-100] - Evaluate algorithm efficiency and appropriate data structure choices.
    EDGE_CASES: [0-100] - Evaluate logical handling of edge cases and error conditions.

    GRADING GUIDELINES:
    - Give high scores (80-100) if the logic is correct despite OCR errors
    - Ignore typos like "hum" vs "num", missing semicolons, misplaced brackets
    - Focus on algorithm logic, variable usage, and program flow
    - Don't penalize for missing class declarations or main methods

    Provide brief explanations for each score.
    """
    
    try:
        comprehensive_response = get_gemini_answer(comprehensive_prompt)
        print(f"DEBUG: Comprehensive evaluation: {comprehensive_response}")
        
        # Parse each score
        syntax_match = re.search(r'SYNTAX:\s*(\d+)', comprehensive_response)
        structure_match = re.search(r'STRUCTURE:\s*(\d+)', comprehensive_response)
        efficiency_match = re.search(r'EFFICIENCY:\s*(\d+)', comprehensive_response)
        edge_cases_match = re.search(r'EDGE_CASES:\s*(\d+)', comprehensive_response)
        
        syntax = int(syntax_match.group(1)) if syntax_match else 70
        structure = int(structure_match.group(1)) if structure_match else 70
        efficiency = int(efficiency_match.group(1)) if efficiency_match else 70
        edge_cases = int(edge_cases_match.group(1)) if edge_cases_match else 60
        
    except Exception as e:
        print(f"DEBUG: Error in comprehensive evaluation: {e}")
        # Fallback to simple rules
        syntax = 100 if ("error" not in student_code.lower() and "syntax" not in student_code.lower()) else 60
        structure = 100 if ("def " in student_code or "function" in student_code) else 70
        efficiency = 100 if ("for" in student_code or "while" in student_code) else 70
        edge_cases = 100 if ("if" in student_code or "try" in student_code) else 60
    
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
        self.selected_language = tk.StringVar(value="C#")
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
        # בחירת שפת קוד
        lang_frame = tk.Frame(self.frame, bg="#f7f7fa")
        lang_frame.pack(pady=(10, 5))
        tk.Label(lang_frame, text="בחר שפת קוד לתשובת Gemini:", font=("Arial", 12), bg="#f7f7fa", fg="#222").pack(side='left')
        lang_options = ["Python", "Java", "C", "C#", "C++"]
        lang_menu = tk.OptionMenu(lang_frame, self.selected_language, *lang_options)
        lang_menu.config(font=("Arial", 12), bg="#e0e7ff", fg="#222")
        lang_menu.pack(side='left', padx=8)
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
        selected_language = self.selected_language.get()
        self.gemini_answer = get_gemini_answer(self.question_text, selected_language)
        results = []
        for i, (name, path, _, _) in enumerate(self.students):
            ocr_text = get_ocr_text(path)
            scores = grade_student_answer(ocr_text, self.gemini_answer, selected_language)
            # חישוב ניקוד סופי
            final_score = scores["Final Score"]
            exam_points = int(round((final_score / 100) * self.question_score))
            scores["Exam Points"] = exam_points
            results.append((name, ocr_text, scores))
        self.show_results(results)

    def show_results(self, results):
        # Maximize the window for full screen display
        self.root.update_idletasks()
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Set window to full screen size
        self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Try to maximize as well
        try:
            self.root.wm_state('zoomed')
        except:
            try:
                self.root.state('zoomed')
            except:
                pass
        
        # Force update
        self.root.update()
        
        # Remove the current frame and create a new scrollable structure
        self.frame.destroy()
        
        # Create main frame with scrollbar
        self.main_frame = tk.Frame(self.root, bg="#f7f7fa")
        self.main_frame.pack(fill="both", expand=True)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.main_frame, bg="#f7f7fa", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.canvas.yview)
        self.frame = tk.Frame(self.canvas, bg="#f7f7fa")
        
        # Configure scrolling
        self.frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Configure frame padding
        self.frame.configure(bg="#f7f7fa")
        
        self.step_label = tk.Label(self.frame, text="תוצאות", font=("Arial", 16, "bold"), bg="#f7f7fa", fg="#222")
        self.step_label.pack(pady=(0, 10))
        # הצג שאלה
        qf = tk.Frame(self.frame, bg="#f7f7fa")
        qf.pack(pady=5, fill='x')
        tk.Label(qf, text="שאלה:", font=("Arial", 12, "bold"), bg="#f7f7fa", fg="#222").pack(anchor='center')
        tk.Message(qf, text=str(self.question_text or ""), width=700, font=("Arial", 11), bg="#f7f7fa", fg="#222", justify='right').pack(anchor='center')

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
            student_text = scrolledtext.ScrolledText(student_frame, width=45, height=10, font=("Consolas", 10), bg="#fff", fg="#222", wrap='word')
            student_text.insert(tk.END, ocr_text)
            student_text.config(state='disabled')
            student_text.pack(anchor='n', padx=8, pady=(0,8), fill='both', expand=True)
            # ציונים
            table = tk.Frame(student_frame, bg="#e0f7fa")
            table.pack(pady=5)
            for i, (param, _) in enumerate(PARAMETERS):
                tk.Label(table, text=param, borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=i)
            tk.Label(table, text="Final Score", borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS))
            tk.Label(table, text="Exam Points", borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS)+1)
            for i, (param, _) in enumerate(PARAMETERS):
                tk.Label(table, text=str(scores[param]), borderwidth=1, relief="solid", width=14, font=("Arial", 9), bg="#fff", fg="#222").grid(row=1, column=i)
            tk.Label(table, text=str(scores["Final Score"]), borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#fff", fg="#000").grid(row=1, column=len(PARAMETERS))
            tk.Label(table, text=str(scores["Exam Points"]), borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#fff", fg="#4f46e5").grid(row=1, column=len(PARAMETERS)+1)
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
                    tk.Label(table, text=param, borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=i)
                tk.Label(table, text="Final Score", borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS))
                tk.Label(table, text="Exam Points", borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#e0e7ff", fg="#222").grid(row=0, column=len(PARAMETERS)+1)
                for i, (param, _) in enumerate(PARAMETERS):
                    tk.Label(table, text=str(scores[param]), borderwidth=1, relief="solid", width=14, font=("Arial", 9), bg="#fff", fg="#222").grid(row=1, column=i)
                tk.Label(table, text=str(scores["Final Score"]), borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#fff", fg="#000").grid(row=1, column=len(PARAMETERS))
                tk.Label(table, text=str(scores["Exam Points"]), borderwidth=1, relief="solid", width=14, font=("Arial", 9, "bold"), bg="#fff", fg="#4f46e5").grid(row=1, column=len(PARAMETERS)+1)
        tk.Button(self.frame, text="סיים", command=self.root.destroy, font=("Arial", 12), bg="#e0e7ff", fg="#222", relief="raised").pack(pady=15, fill='x')

if __name__ == "__main__":
    # Uncomment the next line to test the grading function
    # test_grading()
    
    root = tk.Tk()
    app = ExamGraderApp(root)
    root.mainloop() 