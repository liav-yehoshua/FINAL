import sys
import subprocess
import os
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

# Auto-install required packages if missing
required = [
    ("PIL", "Pillow"),
    ("google.cloud", "google-cloud-vision")
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
    from PIL import Image, ImageTk
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

def run_google_vision_ocr(image_path):
    # Set the environment variable for authentication
    cred_path = os.path.join(os.getcwd(), 'google-credentials.json')
    if not os.path.exists(cred_path):
        tk.Tk().withdraw()
        messagebox.showerror(
            "Missing Credentials",
            f"Could not find google-credentials.json in {os.getcwd()}\nPlease make sure the file exists."
        )
        sys.exit(1)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_path
    client = vision.ImageAnnotatorClient()
    with io.open(image_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)  # type: ignore
    texts = response.text_annotations
    if texts:
        return texts[0].description
    return ''

def show_image_and_text(image_file, ocr_text, root):
    viewer = tk.Toplevel(root)
    viewer.title(f'Image and Google Vision OCR - {os.path.basename(image_file)}')

    # Load and display image
    img = Image.open(image_file)
    img.thumbnail((500, 700))
    img_tk = ImageTk.PhotoImage(img, master=viewer)
    img_label = tk.Label(viewer, image=img_tk)
    img_label.image = img_tk  # type: ignore
    img_label.grid(row=0, column=0, padx=10, pady=10)

    # Display OCR text (read-only)
    text_area = scrolledtext.ScrolledText(viewer, width=60, height=35, font=("Consolas", 10))
    text_area.insert(tk.END, ocr_text)
    text_area.config(state='disabled')
    text_area.grid(row=0, column=1, padx=10, pady=10)

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
        ocr_text = run_google_vision_ocr(image_file)
    except Exception as e:
        messagebox.showerror('OCR Error', f'An error occurred during OCR:\n{e}')
        root.destroy()
        sys.exit(1)
    show_image_and_text(image_file, ocr_text, root)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    main(root) 