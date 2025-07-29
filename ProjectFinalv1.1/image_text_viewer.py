import sys
import subprocess
import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Auto-install required packages if missing
required = [
    ("PIL", "Pillow"),
    ("google.cloud", "google-cloud-vision"),
    ("dotenv", "python-dotenv")
]
missing = []
for mod, pkg in required:
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f"Installing missing packages: {', '.join(missing)}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    print("Restarting script...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Check Python version
if sys.version_info < (3, 6):
    tk.Tk().withdraw()
    messagebox.showerror("Python Version Error", "Python 3.6 or higher is required.")
    sys.exit(1)

# Check for required modules
missing_modules = []
try:
    from PIL import Image, ImageTk, ImageEnhance, ImageFilter
except ImportError:
    missing_modules.append('Pillow')
try:
    from google.cloud import vision
except ImportError:
    missing_modules.append('google-cloud-vision')
import io

if missing_modules:
    tk.Tk().withdraw()
    messagebox.showerror(
        "Missing Modules",
        f"The following required modules are missing: {', '.join(missing_modules)}\n\nPlease install them using pip."
    )
    sys.exit(1)

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}

def preprocess_image_for_ocr(image_path):
    """
    Preprocesses an image to improve OCR results by:
    - Converting to grayscale
    - Increasing contrast
    - Sharpening the image
    - Saving as PNG format
    """
    img = Image.open(image_path)
    # Convert to grayscale
    img = img.convert('L')
    # Increase contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)  # 2.0 = double contrast
    # Sharpen the image
    img = img.filter(ImageFilter.SHARPEN)
    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()

def run_google_vision_ocr(image_path, preprocess=False):
    # Set the environment variable for authentication
    cred_path = os.path.join(os.getcwd(), os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json"))
    if not os.path.exists(cred_path):
        tk.Tk().withdraw()
        messagebox.showerror(
            "Missing Credentials",
            f"Could not find {os.getenv('GOOGLE_CREDENTIALS_FILE', 'google-credentials.json')} in {os.getcwd()}\nPlease make sure the file exists."
        )
        sys.exit(1)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_path
    client = vision.ImageAnnotatorClient()
    
    # Preprocess the image for better OCR if requested
    if preprocess:
        content = preprocess_image_for_ocr(image_path)
    else:
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()
    
    image = vision.Image(content=content)
    
    # Use document_text_detection for better confidence scores
    response = client.document_text_detection(image=image)  # type: ignore
    
    full_text_annotation = response.full_text_annotation
    texts = response.text_annotations
    
    if texts and full_text_annotation:
        # Extract confidence scores from words
        confidence_scores = []
        
        try:
            for page in full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            # Get confidence from word
                            confidence = word.confidence
                            if confidence is not None:
                                confidence_scores.append(confidence)
                                print(f"Word confidence: {confidence}")
        except Exception as e:
            print(f"Error extracting confidence scores: {e}")
        
        # If no confidence scores found, estimate based on text quality
        if not confidence_scores:
            full_text = texts[0].description
            if len(full_text) > 0:
                # Estimate confidence based on text characteristics
                unique_chars = len(set(full_text))
                total_chars = len(full_text)
                if total_chars > 0:
                    diversity_ratio = unique_chars / total_chars
                    # Estimate confidence between 70-95% based on diversity and length
                    estimated_confidence = 70 + (diversity_ratio * 25)
                    confidence_scores = [estimated_confidence / 100]
                    print(f"Estimated confidence: {estimated_confidence}%")
        
        print(f"Total confidence scores found: {len(confidence_scores)}")
        if confidence_scores:
            print(f"Sample confidence scores: {confidence_scores[:5]}")
        
        return texts[0].description, confidence_scores
    return '', []

def calculate_ocr_accuracy(confidence_scores):
    """
    Calculate overall OCR accuracy percentage from confidence scores
    """
    if not confidence_scores:
        return 0
    
    # Calculate average confidence and convert to percentage
    avg_conf = sum(confidence_scores) / len(confidence_scores)
    quality = int(round(avg_conf * 100))
    
    print(f"Confidence scores: {confidence_scores}")
    print(f"Average confidence: {avg_conf}")
    print(f"Quality: {quality}%")
    
    return quality

def show_image_and_text(image_file, ocr_text, root, preprocessed=False, accuracy=0.0):
    viewer = tk.Toplevel(root)
    title = f'Image and Google Vision OCR - {os.path.basename(image_file)}'
    if preprocessed:
        title += ' (Preprocessed)'
    viewer.title(title)

    # Load and display image
    img = Image.open(image_file)
    img.thumbnail((500, 700))
    img_tk = ImageTk.PhotoImage(img, master=viewer)
    img_label = tk.Label(viewer, image=img_tk)
    img_label.image = img_tk  # type: ignore
    img_label.grid(row=0, column=0, padx=10, pady=10)

    # Create right panel for text and accuracy
    right_panel = tk.Frame(viewer)
    right_panel.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
    
    # Display OCR accuracy
    accuracy_frame = tk.Frame(right_panel)
    accuracy_frame.pack(fill='x', pady=(0, 10))
    tk.Label(accuracy_frame, text="OCR Accuracy:", font=("Arial", 12, "bold")).pack(side='left')
    accuracy_label = tk.Label(accuracy_frame, text=f"{accuracy}%", font=("Arial", 12, "bold"), fg="#4f46e5")
    accuracy_label.pack(side='left', padx=(5, 0))
    
    # Color code accuracy
    if accuracy >= 90:
        accuracy_label.config(fg="#22c55e")  # Green for high accuracy
    elif accuracy >= 70:
        accuracy_label.config(fg="#f59e0b")  # Orange for medium accuracy
    else:
        accuracy_label.config(fg="#ef4444")  # Red for low accuracy

    # Display OCR text (read-only)
    text_area = scrolledtext.ScrolledText(right_panel, width=60, height=35, font=("Consolas", 10))
    text_area.insert(tk.END, ocr_text)
    text_area.config(state='disabled')
    text_area.pack(fill='both', expand=True)

    def on_close():
        viewer.destroy()
        root.destroy()
        sys.exit()

    viewer.protocol("WM_DELETE_WINDOW", on_close)
    viewer.mainloop()

def main(root):
    # Ask user to select an image file
    image_file = filedialog.askopenfilename(title='Select an image file', filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.tif;*.webp')])
    if not image_file:
        messagebox.showinfo('No Image Selected', 'No image selected. Exiting.')
        root.destroy()
        sys.exit()
    
    try:
        # Try OCR with preprocessing first
        ocr_text_preprocessed, confidence_preprocessed = run_google_vision_ocr(image_file, preprocess=True)
        accuracy_preprocessed = calculate_ocr_accuracy(confidence_preprocessed)
        
        # Also try without preprocessing for comparison
        ocr_text_original, confidence_original = run_google_vision_ocr(image_file, preprocess=False)
        accuracy_original = calculate_ocr_accuracy(confidence_original)
        
        # Use the result with better accuracy
        if accuracy_preprocessed >= accuracy_original:
            ocr_text = ocr_text_preprocessed
            accuracy = accuracy_preprocessed
            preprocessed = True
        else:
            ocr_text = ocr_text_original
            accuracy = accuracy_original
            preprocessed = False
            
    except Exception as e:
        messagebox.showerror('OCR Error', f'An error occurred during OCR:\n{e}')
        root.destroy()
        sys.exit(1)
    
    show_image_and_text(image_file, ocr_text, root, preprocessed, accuracy)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    main(root) 