from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import os
from PIL import Image
import zipfile
import easyocr
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize EasyOCR reader (English by default; add languages as needed)
reader = easyocr.Reader(['en'])

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/split', methods=['POST'])
def split_image():
    if 'file' not in request.files:
        flash('No file uploaded.')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Get rows and cols from form
        try:
            rows = int(request.form['rows'])
            cols = int(request.form['cols'])
            if rows <= 0 or cols <= 0:
                raise ValueError
        except ValueError:
            flash('Invalid rows/columns. Must be positive integers.')
            os.remove(filepath)
            return redirect(url_for('index'))
        
        # Open image and split
        with Image.open(filepath) as img:
            width, height = img.size
            cell_width = width // cols
            cell_height = height // rows
            
            # Create ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for r in range(rows):
                    for c in range(cols):
                        left = c * cell_width
                        top = r * cell_height
                        right = left + cell_width
                        bottom = top + cell_height
                        
                        split_img = img.crop((left, top, right, bottom))
                        split_filename = f"split_{r+1}_{c+1}.png"
                        
                        # Correct way: Save to BytesIO buffer and get the full PNG bytes
                        img_buffer = io.BytesIO()
                        split_img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        zipf.writestr(split_filename, img_buffer.getvalue())
            
            # Reset buffer for reading
            zip_buffer.seek(0)
            
            os.remove(filepath)  # Clean up
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='split_images.zip'
            )
    
    flash('Invalid file type. Only images allowed.')
    return redirect(url_for('index'))

@app.route('/ocr', methods=['POST'])
def ocr_image():
    if 'file' not in request.files:
        flash('No file uploaded.')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Run OCR
        try:
            results = reader.readtext(filepath)
            extracted_text = ' '.join([text for _, text, _ in results])
        except Exception as e:
            flash(f'OCR failed: {str(e)}')
            os.remove(filepath)
            return redirect(url_for('index'))
        
        os.remove(filepath)  # Clean up
        
        # Render result page with text
        return render_template('ocr_result.html', text=extracted_text)
    
    flash('Invalid file type. Only images allowed.')
    return redirect(url_for('index'))

@app.route('/download_text', methods=['POST'])
def download_text():
    text = request.form['text']
    txt_buffer = io.BytesIO()
    txt_buffer.write(text.encode('utf-8'))
    txt_buffer.seek(0)
    
    return send_file(
        txt_buffer,
        mimetype='text/plain',
        as_attachment=True,
        download_name='extracted_text.txt'
    )

if __name__ == '__main__':
    app.run(debug=True)